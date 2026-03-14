#!/usr/bin/env node
/**
 * Host-side bridge service for OmniFocus MCP
 * 
 * This service runs on the macOS host and executes osascript commands
 * that the Docker container cannot execute directly.
 * 
 * Usage: node host-bridge-service.js [port]
 */

import http from 'http';
import { execSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const PORT = process.argv[2] ? parseInt(process.argv[2], 10) : 8889;
const LETTA_URL = process.env.LETTA_URL || 'http://localhost:8283';
const ROVER_AGENT_ID = process.env.ROVER_AGENT_ID || '';

const DEFAULT_PLUGIN_ID = 'omnifocus-mcp';
const DEFAULT_LIBRARY_ID = 'omnifocus-mcp';

// Inline base64 decoder safe for embedding in AppleScript strings.
const B64_DECODE_JS =
  "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'," +
  "s='{B64}',r='';" +
  "for(var i=0;i<s.length;)" +
  "{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++])," +
  "c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);" +
  "r+=String.fromCharCode((a<<2)|(b>>4));" +
  "if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));" +
  "if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}";

/**
 * Return true when plugin/library are absent or match the defaults.
 */
function isDefaultPlugin(plugin, library) {
  return (
    (!plugin || plugin === DEFAULT_PLUGIN_ID) &&
    (!library || library === DEFAULT_LIBRARY_ID)
  );
}

/**
 * Handle a POST /execute request.
 */
function handleExecute(body, res) {
  try {
    const { command, args, plugin, library } = JSON.parse(body);

    let jsBody;

    if (isDefaultPlugin(plugin, library)) {
      // --- Legacy MCP request() path (unchanged behaviour) ---
      const payload = JSON.stringify({ method: command, params: args || {} });
      const b64 = Buffer.from(payload).toString('base64');
      jsBody = B64_DECODE_JS.replace('{B64}', b64);
      jsBody +=
        `var p=PlugIn.find('${DEFAULT_PLUGIN_ID}');` +
        "if(!p)throw new Error('Plugin not found');" +
        `var lib=p.library('${DEFAULT_LIBRARY_ID}');` +
        "JSON.stringify(lib.request(r))";
    } else {
      // --- Direct library call path ---
      const plugId = plugin || DEFAULT_PLUGIN_ID;
      const libId = library || DEFAULT_LIBRARY_ID;
      const paramsJson = JSON.stringify(args || {});
      const b64 = Buffer.from(paramsJson).toString('base64');
      jsBody = B64_DECODE_JS.replace('{B64}', b64);
      jsBody +=
        `var p=PlugIn.find('${plugId}');` +
        `if(!p)throw new Error('Plugin ${plugId} not found');` +
        `var lib=p.library('${libId}');` +
        "var params=JSON.parse(r);" +
        "var keys=Object.keys(params);" +
        "var out;" +
        `if(keys.length===0)out=lib.${command}();` +
        `else if(keys.length===1)out=lib.${command}(params[keys[0]]);` +
        `else out=lib.${command}(params);` +
        "JSON.stringify(out)";
    }

    const script = `
tell application "OmniFocus"
  set _res to evaluate javascript "${jsBody}"
end tell
return _res
`;

    const tmpApple = path.join(
      os.tmpdir(),
      `omnifocus-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.applescript`,
    );

    fs.writeFileSync(tmpApple, script, 'utf8');

    try {
      const raw = execSync(`/usr/bin/osascript "${tmpApple}"`, { encoding: 'utf8' });
      const result = JSON.parse(raw);

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: true, result }));
    } catch (err) {
      console.error('OmniFocus call failed:', err);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        success: false,
        error: 'Bridge call failed',
        details: err.message,
      }));
    } finally {
      try {
        fs.unlinkSync(tmpApple);
      } catch (_) {
        // Ignore cleanup errors
      }
    }
  } catch (err) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid request', details: err.message }));
  }
}

// ---------------------------------------------------------------------------
// Timer event relay
// ---------------------------------------------------------------------------

/**
 * Format a timer event into a natural-language message for Letta.
 */
function formatTimerMessage(event) {
  const name = event.taskName || 'Unknown task';
  const project = event.projectName ? ` (${event.projectName})` : '';
  const estMin = event.originalEstimateMin;
  const agentMin = event.agentEstimateMin;

  switch (event.event) {
    case 'timer.started':
      return estMin
        ? `Timer started on '${name}'${project}. Estimated duration: ${estMin} min.`
        : `Timer started on '${name}'${project}.`;

    case 'timer.switched': {
      const prev = event.switchedFrom || 'unknown task';
      const prevDur = event.previousSessionMin;
      return prevDur != null
        ? `Timer switched from '${prev}' to '${name}'${project}. Previous session: ${prevDur} min.`
        : `Timer switched from '${prev}' to '${name}'${project}.`;
    }

    case 'timer.stopped': {
      const session = event.sessionMin != null ? ` Session: ${event.sessionMin} min.` : '';
      const total = event.totalMin != null ? ` Total: ${event.totalMin} min.` : '';
      const orig = estMin != null ? ` Original estimate: ${estMin} min.` : '';
      return `Timer stopped on '${name}'.${session}${total}${orig}`;
    }

    case 'timer.paused': {
      const elapsed = event.elapsedMin != null ? ` Elapsed: ${event.elapsedMin} min.` : '';
      return `Timer paused on '${name}'.${elapsed}`;
    }

    case 'timer.resumed':
      return `Timer resumed on '${name}'.`;

    case 'timer.auto-stopped': {
      const final_ = event.totalMin != null ? ` Final time: ${event.totalMin} min.` : '';
      const est = estMin != null ? ` (estimate was ${estMin} min)` : '';
      return `Timer auto-stopped: '${name}' was marked complete.${final_}${est}`;
    }

    default:
      return `Timer event '${event.event}' on '${name}'.`;
  }
}

/**
 * Fire-and-forget POST to Letta agent messages API.
 */
function relayToLetta(message) {
  if (!ROVER_AGENT_ID) {
    console.log('[timer-event] ROVER_AGENT_ID not set, skipping Letta relay');
    return;
  }

  const payload = JSON.stringify({
    messages: [{ role: 'user', content: message }],
  });

  const url = new URL(`${LETTA_URL}/v1/agents/${ROVER_AGENT_ID}/messages`);

  const options = {
    hostname: url.hostname,
    port: url.port || 80,
    path: url.pathname,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
  };

  const req = http.request(options, (resp) => {
    let body = '';
    resp.on('data', (chunk) => { body += chunk; });
    resp.on('end', () => {
      if (resp.statusCode >= 200 && resp.statusCode < 300) {
        console.log(`[timer-event] Letta relay success (${resp.statusCode})`);
      } else {
        console.error(`[timer-event] Letta relay failed: ${resp.statusCode} ${body.substring(0, 200)}`);
      }
    });
  });

  req.on('error', (err) => {
    console.error(`[timer-event] Letta relay error: ${err.message}`);
  });

  req.write(payload);
  req.end();
}

/**
 * Handle POST /timer-event requests from the OmniFocus timer plugin.
 */
function handleTimerEvent(body, res) {
  try {
    const event = JSON.parse(body);
    console.log(`[timer-event] Received: ${event.event} — ${event.taskName || 'n/a'}`);

    // Skip heartbeat events
    if (event.event === 'timer.heartbeat') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ forwarded: false }));
      return;
    }

    const message = formatTimerMessage(event);
    console.log(`[timer-event] Formatted: ${message}`);

    // Fire-and-forget relay to Letta
    relayToLetta(message);

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ forwarded: true }));
  } catch (err) {
    console.error('[timer-event] Parse error:', err.message);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ forwarded: false, error: err.message }));
  }
}

const server = http.createServer((req, res) => {
  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk.toString(); });

    if (req.url === '/execute') {
      req.on('end', () => handleExecute(body, res));
      return;
    }
    if (req.url === '/timer-event') {
      req.on('end', () => handleTimerEvent(body, res));
      return;
    }
  }

  // Fallback — not found
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 OmniFocus Host Bridge Service listening on port ${PORT}`);
  console.log(`   Endpoint: http://0.0.0.0:${PORT}/execute`);
  console.log(`   Timer:    http://0.0.0.0:${PORT}/timer-event`);
  if (ROVER_AGENT_ID) {
    console.log(`   Letta relay: ${LETTA_URL} → agent ${ROVER_AGENT_ID}`);
  } else {
    console.log(`   Letta relay: disabled (ROVER_AGENT_ID not set)`);
  }
});

