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

app.listen(PORT, '0.0.0.0', () => {
  console.log(`gws-bridge listening on :${PORT}`);
});
