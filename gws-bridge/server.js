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
    const healthy = status.token_valid === true || (status.storage && status.storage !== 'none');
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

// Build a label ID → name map (cached per request)
function getLabelMap() {
  const labelsData = runGws([
    'gmail', 'users', 'labels', 'list',
    '--params', JSON.stringify({ userId: 'me' }),
    '--format', 'json',
  ]);
  const map = {};
  (labelsData.labels || []).forEach(l => { map[l.id] = l.name; });
  return map;
}

// List drafts, optionally filtered by Gmail query
app.get('/gmail/drafts', (req, res) => {
  try {
    const q = req.query.q || '';
    const maxResults = parseInt(req.query.maxResults) || 20;
    const params = { userId: 'me', maxResults };
    if (q) params.q = q;

    const data = runGws([
      'gmail', 'users', 'drafts', 'list',
      '--params', JSON.stringify(params),
      '--format', 'json',
    ]);

    // Resolve label IDs to names once for the whole response
    let labelMap = {};
    try { labelMap = getLabelMap(); } catch { /* proceed without names */ }

    // gws returns raw Gmail API response: { drafts: [...], resultSizeEstimate: N }
    // Each draft has { id, message: { id, threadId } }
    // We need to fetch metadata for each draft to get subject/to/labels
    const drafts = data.drafts || [];
    const enriched = drafts.map(draft => {
      try {
        const full = runGws([
          'gmail', 'users', 'drafts', 'get',
          '--params', JSON.stringify({ userId: 'me', id: draft.id, format: 'metadata' }),
          '--format', 'json',
        ], 10000);

        const headers = full.message?.payload?.headers || [];
        const headerMap = {};
        headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

        const labelIds = full.message?.labelIds || [];
        const labelNames = labelIds.map(id => labelMap[id] || id);

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
          labelIds,
          labelNames,
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
      'gmail', 'users', 'drafts', 'get',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id, format: 'full' }),
      '--format', 'json',
    ]);

    const headers = data.message?.payload?.headers || [];
    const headerMap = {};
    headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

    // Extract body — prefer text/html (for rich text editor), fall back to text/plain
    let bodyText = '';
    const payload = data.message?.payload || {};

    function findBody(part, preferred) {
      if (part.mimeType === preferred && part.body?.data) {
        return Buffer.from(part.body.data, 'base64url').toString('utf-8');
      }
      if (part.parts) {
        for (const sub of part.parts) {
          const found = findBody(sub, preferred);
          if (found) return found;
        }
      }
      return null;
    }

    bodyText = findBody(payload, 'text/html') || findBody(payload, 'text/plain') || '';

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

// Update draft (to, cc, subject, body) — preserves labels across the message replacement
app.put('/gmail/drafts/:id', (req, res) => {
  try {
    const { to, cc, subject, body } = req.body;

    // Read current draft to capture labels before the update replaces the message
    const current = runGws([
      'gmail', 'users', 'drafts', 'get',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id, format: 'minimal' }),
      '--format', 'json',
    ], 10000);
    const oldLabelIds = (current.message?.labelIds || []).filter(l => l !== 'DRAFT');

    // Build RFC 2822 message
    const lines = [];
    if (to) lines.push(`To: ${to}`);
    if (cc) lines.push(`Cc: ${cc}`);
    if (subject) lines.push(`Subject: ${subject}`);
    const isHtml = /<[a-z][\s\S]*>/i.test(body || '');
    lines.push(isHtml ? 'Content-Type: text/html; charset=utf-8' : 'Content-Type: text/plain; charset=utf-8');
    lines.push('');
    lines.push(body || '');
    const raw = Buffer.from(lines.join('\r\n')).toString('base64url');

    const data = runGws([
      'gmail', 'users', 'drafts', 'update',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
      '--json', JSON.stringify({ message: { raw } }),
      '--format', 'json',
    ], 20000);

    // Re-apply labels to the new message
    const newMessageId = data.message?.id;
    if (newMessageId && oldLabelIds.length > 0) {
      try {
        runGws([
          'gmail', 'users', 'messages', 'modify',
          '--params', JSON.stringify({ userId: 'me', id: newMessageId }),
          '--json', JSON.stringify({ addLabelIds: oldLabelIds }),
          '--format', 'json',
        ], 10000);
      } catch { /* label restore is best-effort */ }
    }

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
      'gmail', 'users', 'drafts', 'send',
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
    execFileSync(GWS, [
      'gmail', 'users', 'drafts', 'delete',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
    ], { encoding: 'utf-8', timeout: 15000, env: { ...process.env } });
    res.json({ status: 'ok' });
  } catch (err) {
    const stderr = err.stderr || err.message || '';
    if (stderr.includes('404') || stderr.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${stderr.slice(0, 300)}` });
  }
});

// Get a Gmail message by ID (for reply headers)
app.get('/gmail/messages/:id', (req, res) => {
  try {
    const params = { userId: 'me', id: req.params.id };
    if (req.query.format) params.format = req.query.format;
    const data = runGws([
      'gmail', 'users', 'messages', 'get',
      '--params', JSON.stringify(params),
      '--format', 'json',
    ]);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: `gws error: ${(err.stderr || err.message || '').slice(0, 300)}` });
  }
});

// Create a Gmail draft (for reply drafts from follow-up pipeline)
app.post('/gmail/drafts', (req, res) => {
  try {
    const data = runGws([
      'gmail', 'users', 'drafts', 'create',
      '--params', JSON.stringify({ userId: 'me' }),
      '--json', JSON.stringify(req.body),
      '--format', 'json',
    ]);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: `gws error: ${(err.stderr || err.message || '').slice(0, 300)}` });
  }
});

// Reply to a Google Docs/Drive comment
app.post('/drive/replies/create', (req, res) => {
  try {
    const { fileId, commentId, content } = req.body;
    if (!fileId || !commentId || !content) {
      return res.status(400).json({ error: 'fileId, commentId, and content required' });
    }
    const data = runGws([
      'drive', 'replies', 'create',
      '--params', JSON.stringify({ fileId, commentId }),
      '--json', JSON.stringify({ content }),
      '--format', 'json',
    ]);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: `gws error: ${(err.stderr || err.message || '').slice(0, 300)}` });
  }
});

// Resolve/unresolve a Google Docs/Drive comment
app.patch('/drive/comments/update', (req, res) => {
  try {
    const { fileId, commentId, resolved } = req.body;
    if (!fileId || !commentId) {
      return res.status(400).json({ error: 'fileId and commentId required' });
    }
    const data = runGws([
      'drive', 'comments', 'update',
      '--params', JSON.stringify({ fileId, commentId }),
      '--json', JSON.stringify({ resolved: !!resolved }),
      '--format', 'json',
    ]);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: `gws error: ${(err.stderr || err.message || '').slice(0, 300)}` });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`gws-bridge listening on :${PORT}`);
});
