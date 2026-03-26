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
import { execSync, spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = process.argv[2] ? parseInt(process.argv[2], 10) : 8889;
const LETTA_URL = process.env.LETTA_URL || 'http://localhost:8283';
const ROVER_AGENT_ID = process.env.ROVER_AGENT_ID || '';

const DEFAULT_PLUGIN_ID = 'omnifocus-mcp';
const DEFAULT_LIBRARY_ID = 'omnifocus-mcp';

// Widget queue SSH config (laptop)
const LAPTOP_SSH_HOST = process.env.LAPTOP_SSH_HOST || 'chaddorsey@100.95.213.46';
const LAPTOP_SSH_KEY = process.env.LAPTOP_SSH_KEY || path.join(os.homedir(), '.ssh', 'id_ed25519');
const WIDGET_QUEUE_SCRIPT = process.env.WIDGET_QUEUE_SCRIPT || '~/Dropbox/dev/omnifocus-timer/widget-queue.sh';

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
function fmtDuration(ms) {
  if (ms == null) return null;
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min < 60) return `${min}m ${sec < 10 ? '0' : ''}${sec}s`;
  const hrs = Math.floor(min / 60);
  const m = min % 60;
  return `${hrs}h ${m < 10 ? '0' : ''}${m}m ${sec < 10 ? '0' : ''}${sec}s`;
}

function formatTimerMessage(event) {
  const name = event.taskName || 'Unknown task';
  const project = event.projectName ? ` (${event.projectName})` : '';
  const estMin = event.originalEstimateMin;

  switch (event.event) {
    case 'timer.started':
      return estMin
        ? `Timer started on '${name}'${project}. Estimated duration: ${estMin} min.`
        : `Timer started on '${name}'${project}.`;

    case 'timer.switched': {
      const prev = event.switchedFrom || 'unknown task';
      const prevDur = fmtDuration(event.sessionMs);
      return prevDur
        ? `Timer switched from '${prev}' to '${name}'${project}. Previous session: ${prevDur}.`
        : `Timer switched from '${prev}' to '${name}'${project}.`;
    }

    case 'timer.stopped': {
      const session = fmtDuration(event.sessionMs);
      const total = fmtDuration(event.totalMs);
      const parts = [`Timer stopped on '${name}'.`];
      if (session) parts.push(`Session: ${session}.`);
      if (total) parts.push(`Total: ${total}.`);
      if (estMin != null) parts.push(`Original estimate: ${estMin} min.`);
      return parts.join(' ');
    }

    case 'timer.paused': {
      const elapsed = fmtDuration(event.elapsedMs);
      return elapsed
        ? `Timer paused on '${name}'. Elapsed: ${elapsed}.`
        : `Timer paused on '${name}'.`;
    }

    case 'timer.resumed':
      return `Timer resumed on '${name}'.`;

    case 'timer.auto-stopped': {
      const final_ = fmtDuration(event.totalMs);
      const est = estMin != null ? ` (estimate was ${estMin} min)` : '';
      return `Timer auto-stopped: '${name}' was marked complete.${final_ ? ` Final time: ${final_}.` : ''}${est}`;
    }

    default:
      return `Timer event '${event.event}' on '${name}'.`;
  }
}

// ---------------------------------------------------------------------------
// Timer event logging and completion relay
// ---------------------------------------------------------------------------

// Log directory — all timer events go to a JSONL file.
// Completion events additionally get relayed to MC for thinking.
const TIMER_LOG_DIR = process.env.TIMER_LOG_DIR || '/tmp/omnifocus-timer-logs';
const MC_AGENT_ID = process.env.MC_AGENT_ID || ROVER_AGENT_ID;

// Ensure log directory exists
try { fs.mkdirSync(TIMER_LOG_DIR, { recursive: true }); } catch (_) {}

/**
 * Append a timer event to the local JSONL log file.
 * File: TIMER_LOG_DIR/timer-events.jsonl
 */
function logTimerEvent(event) {
  const logFile = path.join(TIMER_LOG_DIR, 'timer-events.jsonl');
  const line = JSON.stringify({ ...event, _logged: new Date().toISOString() }) + '\n';
  fs.appendFileSync(logFile, line, 'utf8');
}

/**
 * Append to the unified task-lifecycle.jsonl log.
 */
function logLifecycle(eventName, fields) {
  const logFile = path.join(TIMER_LOG_DIR, 'task-lifecycle.jsonl');
  const entry = { event: eventName, timestamp: new Date().toISOString(), ...fields };
  try { fs.appendFileSync(logFile, JSON.stringify(entry) + '\n', 'utf8'); } catch (_) {}
}

/**
 * Append a completion record to the completions log.
 * File: TIMER_LOG_DIR/completions.jsonl
 * This is the file MC reads for batch status updates.
 */
function logCompletion(event) {
  const logFile = path.join(TIMER_LOG_DIR, 'completions.jsonl');
  const record = {
    taskId: event.taskId,
    taskName: event.taskName,
    projectName: event.projectName,
    refId: event.refId || null,
    sessionMs: event.sessionMs,
    totalMs: event.totalMs,
    originalEstimateMin: event.originalEstimateMin,
    agentEstimateMin: event.agentEstimateMin,
    completedAt: new Date().toISOString(),
  };
  const line = JSON.stringify(record) + '\n';
  fs.appendFileSync(logFile, line, 'utf8');
}

/**
 * Fire-and-forget POST to Letta agent messages API.
 * Used ONLY for completion events → MC (thinking tier).
 */
function relayCompletionToMC(message) {
  const agentId = MC_AGENT_ID;
  if (!agentId) {
    console.log('[timer-event] No MC_AGENT_ID set, skipping completion relay');
    return;
  }

  const payload = JSON.stringify({
    messages: [{ role: 'user', content: message }],
  });

  const url = new URL(`${LETTA_URL}/v1/agents/${agentId}/messages`);

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
        console.log(`[timer-event] MC completion relay success (${resp.statusCode})`);
      } else {
        console.error(`[timer-event] MC completion relay failed: ${resp.statusCode} ${body.substring(0, 200)}`);
      }
    });
  });

  req.on('error', (err) => {
    console.error(`[timer-event] MC completion relay error: ${err.message}`);
  });

  req.write(payload);
  req.end();
}

/**
 * Handle POST /timer-event requests from the OmniFocus timer plugin.
 *
 * ALL events → local JSONL log (no LLM cost).
 * COMPLETION events only → also relay to MC (thinking tier).
 * Everything else (start, pause, resume, heartbeat) → log only.
 */
function handleTimerEvent(body, res) {
  try {
    const event = JSON.parse(body);
    console.log(`[timer-event] ${event.event} — ${event.taskName || 'n/a'}`);

    // Log ALL events to file (zero LLM cost)
    logTimerEvent(event);

    // Log to unified lifecycle log for key events
    if (event.event === 'timer.started') {
      logLifecycle('timer_started', {
        ref_id: event.refId, omnifocus_id: event.taskId,
        task: event.taskName, project: event.projectName,
        estimate_min: event.originalEstimateMin,
      });
    }

    // Completion events additionally get relayed to MC and logged separately
    const isCompletion = event.event === 'timer.stopped' || event.event === 'timer.auto-stopped';
    if (isCompletion) {
      logCompletion(event);
      logLifecycle('timer_completed', {
        ref_id: event.refId, omnifocus_id: event.taskId,
        task: event.taskName, project: event.projectName,
        session_ms: event.sessionMs, total_ms: event.totalMs,
        estimate_min: event.originalEstimateMin,
        agent_estimate_min: event.agentEstimateMin,
      });
      const message = formatTimerMessage(event);
      console.log(`[timer-event] Completion → MC: ${message}`);
      relayCompletionToMC(message);

      // Prepare follow-up and time tracking (async, zero LLM cost)
      const followUpScript = path.resolve(__dirname, '../scripts/prepare_follow_up.py');
      // Load SLACK_BOT_TOKEN from .env if not in process env
      if (!process.env.SLACK_BOT_TOKEN) {
        try {
          const envFile = fs.readFileSync(path.resolve(__dirname, '../.env'), 'utf8');
          const match = envFile.match(/^SLACK_BOT_TOKEN=(.+)$/m);
          if (match) process.env.SLACK_BOT_TOKEN = match[1].trim();
        } catch (_) {}
      }

      const child = spawn('python3', [followUpScript], {
        env: {
          ...process.env,
          LETTA_URL: LETTA_URL,
          MC_AGENT_ID: MC_AGENT_ID,
          TIMER_LOG_DIR: TIMER_LOG_DIR,
          FOLLOWUP_QUEUE: path.join(TIMER_LOG_DIR, 'pending-followups.jsonl'),
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      child.stdin.write(JSON.stringify(event));
      child.stdin.end();
      child.stdout.on('data', (data) => console.log(data.toString().trim()));
      child.stderr.on('data', (data) => console.error(data.toString().trim()));
      child.on('close', (code) => {
        if (code !== 0) console.error(`[follow-up] Script exited with code ${code}`);
      });
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ logged: true, relayed: isCompletion }));
  } catch (err) {
    console.error('[timer-event] Parse error:', err.message);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ logged: false, error: err.message }));
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
    if (req.url === '/omnifocus-snapshot') {
      req.on('end', () => {
        const script = path.resolve(__dirname, '../scripts/omnifocus_snapshot.py');
        const child = spawn('python3', [script], {
          env: { ...process.env, SNAPSHOT_DIR: TIMER_LOG_DIR },
          stdio: ['pipe', 'pipe', 'pipe'],
        });
        let stdout = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stdout += d.toString(); });
        child.on('close', (code) => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: code === 0 ? 'ok' : 'error', output: stdout.trim() }));
        });
      });
      return;
    }
    if (req.url === '/widget-queue') {
      req.on('end', () => {
        try {
          const { action, taskId, position } = JSON.parse(body);
          if (!action) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'action required' }));
            return;
          }

          // Build remote command
          const parts = [WIDGET_QUEUE_SCRIPT, action];
          if (action === 'next' && taskId) {
            parts.push(taskId);
          } else if (action === 'push' && taskId) {
            parts.push(...taskId.split(',').map(s => s.trim()).filter(Boolean));
          } else if (action === 'insert' && position !== undefined && taskId) {
            parts.push(String(position), taskId);
          } else if (action === 'remove' && taskId) {
            parts.push(taskId);
          }
          // 'list' and 'clear' need no extra args

          const remoteCmd = parts.join(' ');
          const result = execSync(
            `ssh -i "${LAPTOP_SSH_KEY}" -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${LAPTOP_SSH_HOST} '${remoteCmd}'`,
            { timeout: 20000, encoding: 'utf-8' }
          );

          let parsed;
          try { parsed = JSON.parse(result); } catch { parsed = { raw: result.trim() }; }

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(parsed));
        } catch (err) {
          console.error('🟥 widget-queue error:', err.message);
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message }));
        }
      });
      return;
    }
  }

  // Fallback — not found
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`OmniFocus Host Bridge Service listening on port ${PORT}`);
  console.log(`   /execute      — OmniFocus plugin commands`);
  console.log(`   /timer-event  — timer event logging`);
  console.log(`   /widget-queue — laptop timer widget queue (SSH → ${LAPTOP_SSH_HOST})`);
  console.log(`   Timer log:    ${TIMER_LOG_DIR}/timer-events.jsonl`);
  console.log(`   Completions:  ${TIMER_LOG_DIR}/completions.jsonl`);
  if (MC_AGENT_ID) {
    console.log(`   MC relay:     ${LETTA_URL} → ${MC_AGENT_ID} (completions only)`);
  } else {
    console.log(`   MC relay:     disabled (no MC_AGENT_ID)`);
  }
});

