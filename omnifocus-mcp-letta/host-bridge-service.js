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

  if (req.method !== 'POST' || req.url !== '/execute') {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
    return;
  }

  let body = '';
  req.on('data', chunk => {
    body += chunk.toString();
  });

  req.on('end', () => {
    try {
      const { command, args } = JSON.parse(body);
      
      const payload = JSON.stringify({
        method: command,
        params: args || {},
      });

      // Base64-encode the JSON to avoid escaping issues.
      // The old approach used AppleScript's `quoted form` to embed JSON
      // in a JavaScript string literal, but that breaks on backslash
      // escapes (\n, \t, \\) and single quotes — characters that are
      // common in task notes. Base64 uses only A-Za-z0-9+/= which are
      // safe in both AppleScript and JavaScript strings.
      const b64 = Buffer.from(payload).toString('base64');
      const tmpApple = path.join(os.tmpdir(), `omnifocus-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.applescript`);

      const script = `
tell application "OmniFocus"
  set _res to evaluate javascript "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='${b64}',r='';for(var i=0;i<s.length;){var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}var p=PlugIn.find('omnifocus-mcp');if(!p)throw new Error('Plugin not found');var lib=p.library('omnifocus-mcp');JSON.stringify(lib.request(r))"
end tell
return _res
`;

      fs.writeFileSync(tmpApple, script, 'utf8');

      try {
        const raw = execSync(`/usr/bin/osascript "${tmpApple}"`, { encoding: 'utf8' });
        const result = JSON.parse(raw);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, result }));
      } catch (err) {
        console.error('🟥 OmniFocus call failed:', err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          success: false,
          error: 'Bridge call failed',
          details: err.message
        }));
      } finally {
        // Cleanup
        try {
          fs.unlinkSync(tmpApple);
        } catch (e) {
          // Ignore cleanup errors
        }
      }
    } catch (err) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Invalid request', details: err.message }));
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 OmniFocus Host Bridge Service listening on port ${PORT}`);
  console.log(`   Endpoint: http://0.0.0.0:${PORT}/execute`);
});

