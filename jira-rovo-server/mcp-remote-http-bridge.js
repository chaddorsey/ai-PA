#!/usr/bin/env node
/**
 * HTTP Bridge for mcp-remote
 * 
 * This creates an HTTP server that bridges Letta's HTTP-based MCP requests
 * to mcp-remote's stdio-based interface.
 */

const http = require('http');
const { spawn } = require('child_process');
const readline = require('readline');

const HTTP_PORT = process.env.MCP_REMOTE_HTTP_PORT || 8889;
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

let mcpRemoteProcess = null;
let requestId = 0;
const pendingRequests = new Map();

function startMCPRemote() {
  console.log(`[${new Date().toISOString()}] Starting mcp-remote...`);
  
  mcpRemoteProcess = spawn('mcp-remote', [ROVO_MCP_URL], {
    stdio: ['pipe', 'pipe', 'inherit']
  });

  const rl = readline.createInterface({
    input: mcpRemoteProcess.stdout,
    crlfDelay: Infinity
  });

  rl.on('line', (line) => {
    try {
      const response = JSON.parse(line);
      const id = response.id;
      
      if (pendingRequests.has(id)) {
        const { res, timeout } = pendingRequests.get(id);
        clearTimeout(timeout);
        pendingRequests.delete(id);
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(response));
      }
    } catch (e) {
      // Not JSON, might be log output
      if (line.includes('error') || line.includes('Error')) {
        console.error(`[mcp-remote] ${line}`);
      }
    }
  });

  mcpRemoteProcess.on('error', (err) => {
    console.error(`[mcp-remote] Error: ${err.message}`);
    setTimeout(startMCPRemote, 2000);
  });

  mcpRemoteProcess.on('exit', (code) => {
    console.log(`[mcp-remote] Exited with code ${code}`);
    mcpRemoteProcess = null;
    if (code !== 0) {
      setTimeout(startMCPRemote, 2000);
    }
  });

  console.log(`[${new Date().toISOString()}] mcp-remote started`);
}

const server = http.createServer((req, res) => {
  // Handle CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.method !== 'POST' || req.url !== '/mcp') {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
    return;
  }

  if (!mcpRemoteProcess || !mcpRemoteProcess.stdin) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'mcp-remote not ready' }));
    return;
  }

  let body = '';
  req.on('data', (chunk) => {
    body += chunk.toString();
  });

  req.on('end', () => {
    try {
      const request = JSON.parse(body);
      const id = request.id || ++requestId;
      request.id = id;

      // Set timeout
      const timeout = setTimeout(() => {
        if (pendingRequests.has(id)) {
          pendingRequests.delete(id);
          res.writeHead(504, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ 
            jsonrpc: '2.0',
            id,
            error: { code: -32000, message: 'Request timeout' }
          }));
        }
      }, 30000); // 30 second timeout

      pendingRequests.set(id, { res, timeout });

      // Send to mcp-remote
      mcpRemoteProcess.stdin.write(JSON.stringify(request) + '\n');
    } catch (e) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Invalid JSON' }));
    }
  });
});

// Start mcp-remote
startMCPRemote();

// Start HTTP server
server.listen(HTTP_PORT, () => {
  console.log(`[${new Date().toISOString()}] HTTP bridge listening on port ${HTTP_PORT}`);
  console.log(`[${new Date().toISOString()}] Connect Letta to: http://localhost:${HTTP_PORT}/mcp`);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  if (mcpRemoteProcess) {
    mcpRemoteProcess.kill();
  }
  server.close();
  process.exit(0);
});

