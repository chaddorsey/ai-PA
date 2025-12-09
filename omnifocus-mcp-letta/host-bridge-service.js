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
      
      // Create temporary files
      const tmpJson = path.join(os.tmpdir(), `omnifocus-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.json`);
      const tmpApple = path.join(os.tmpdir(), `omnifocus-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.applescript`);
      
      const payload = JSON.stringify({
        method: command,
        params: args || {},
      });

      fs.writeFileSync(tmpJson, payload, 'utf8');

      // Build AppleScript wrapper
      const script = `
set jsonPath to POSIX path of "${tmpJson}"
set jsonData to read POSIX file jsonPath as «class utf8»
set js to "const p = PlugIn.find(\\\"omnifocus-mcp\\\");\
 if(!p) throw new Error('Plugin not found');\
 const lib = p.library(\\\"omnifocus-mcp\\\");\
 JSON.stringify(lib.request(" & quoted form of jsonData & "))"

tell application "OmniFocus"
  set _res to evaluate javascript js
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
          fs.unlinkSync(tmpJson);
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

