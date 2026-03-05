const express = require('express');
const { execFileSync } = require('child_process');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 8098;
const GWS = 'gws';

function runGws(args, timeoutMs = 15000) {
  const result = execFileSync(GWS, args, {
    encoding: 'utf-8',
    timeout: timeoutMs,
    env: { ...process.env },
  });
  return JSON.parse(result);
}

// Health check
app.get('/health', (_req, res) => {
  try {
    const status = runGws(['auth', 'status']);
    const healthy = status.credential_source && status.credential_source !== 'none';
    res.json({
      status: healthy ? 'healthy' : 'unhealthy',
      gws_version: '0.3.4',
      auth: status,
    });
  } catch (err) {
    res.status(503).json({
      status: 'unhealthy',
      error: err.message,
    });
  }
});

// List drafts, optionally filtered by Gmail query
app.get('/gmail/drafts', (req, res) => {
  try {
    const q = req.query.q || '';
    const maxResults = parseInt(req.query.maxResults) || 20;
    const params = { userId: 'me', maxResults };
    if (q) params.q = q;

    const data = runGws([
      'gmail', 'users.drafts', 'list',
      '--params', JSON.stringify(params),
      '--format', 'json',
    ]);

    // gws returns raw Gmail API response: { drafts: [...], resultSizeEstimate: N }
    // Each draft has { id, message: { id, threadId } }
    // We need to fetch metadata for each draft to get subject/to/labels
    const drafts = data.drafts || [];
    const enriched = drafts.map(draft => {
      try {
        const full = runGws([
          'gmail', 'users.drafts', 'get',
          '--params', JSON.stringify({ userId: 'me', id: draft.id, format: 'metadata' }),
          '--format', 'json',
        ], 10000);

        const headers = full.message?.payload?.headers || [];
        const headerMap = {};
        headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

        return {
          id: draft.id,
          messageId: full.message?.id || '',
          threadId: full.message?.threadId || '',
          subject: headerMap['subject'] || '(no subject)',
          to: headerMap['to'] || '',
          cc: headerMap['cc'] || '',
          from: headerMap['from'] || '',
          date: headerMap['date'] || '',
          snippet: full.message?.snippet || '',
          labelIds: full.message?.labelIds || [],
          internalDate: full.message?.internalDate || '',
        };
      } catch {
        return { id: draft.id, subject: '(failed to load)', error: true };
      }
    });

    res.json({ drafts: enriched, count: enriched.length });
  } catch (err) {
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});

// Get single draft with full body
app.get('/gmail/drafts/:id', (req, res) => {
  try {
    const data = runGws([
      'gmail', 'users.drafts', 'get',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id, format: 'full' }),
      '--format', 'json',
    ]);

    const headers = data.message?.payload?.headers || [];
    const headerMap = {};
    headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

    // Extract body text — prefer text/plain, fall back to text/html
    let bodyText = '';
    const payload = data.message?.payload || {};

    function findBody(part) {
      if (part.mimeType === 'text/plain' && part.body?.data) {
        return Buffer.from(part.body.data, 'base64url').toString('utf-8');
      }
      if (part.parts) {
        for (const sub of part.parts) {
          const found = findBody(sub);
          if (found) return found;
        }
      }
      // Fall back to text/html
      if (part.mimeType === 'text/html' && part.body?.data) {
        return Buffer.from(part.body.data, 'base64url').toString('utf-8');
      }
      return null;
    }

    bodyText = findBody(payload) || '';

    res.json({
      id: data.id,
      messageId: data.message?.id || '',
      threadId: data.message?.threadId || '',
      subject: headerMap['subject'] || '',
      to: headerMap['to'] || '',
      cc: headerMap['cc'] || '',
      from: headerMap['from'] || '',
      body: bodyText,
      labelIds: data.message?.labelIds || [],
    });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});

// Update draft (to, cc, subject, body)
app.put('/gmail/drafts/:id', (req, res) => {
  try {
    const { to, cc, subject, body } = req.body;

    // Build RFC 2822 message
    const lines = [];
    if (to) lines.push(`To: ${to}`);
    if (cc) lines.push(`Cc: ${cc}`);
    if (subject) lines.push(`Subject: ${subject}`);
    lines.push('Content-Type: text/plain; charset=utf-8');
    lines.push('');
    lines.push(body || '');
    const raw = Buffer.from(lines.join('\r\n')).toString('base64url');

    const data = runGws([
      'gmail', 'users.drafts', 'update',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
      '--json', JSON.stringify({ message: { raw } }),
      '--format', 'json',
    ], 20000);

    res.json({ status: 'ok', id: data.id || req.params.id });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});

// Send a draft
app.post('/gmail/drafts/:id/send', (req, res) => {
  try {
    const data = runGws([
      'gmail', 'users.drafts', 'send',
      '--json', JSON.stringify({ id: req.params.id }),
      '--params', JSON.stringify({ userId: 'me' }),
      '--format', 'json',
    ], 20000);

    res.json({ status: 'ok', messageId: data.id || '' });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found (may already be sent)' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});

// Delete (discard) a draft
app.delete('/gmail/drafts/:id', (req, res) => {
  try {
    runGws([
      'gmail', 'users.drafts', 'delete',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
      '--format', 'json',
    ]);
    res.json({ status: 'ok' });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`gws-bridge listening on :${PORT}`);
});
