#!/usr/bin/env node
/**
 * Intercept token from mcp-remote by monitoring its HTTP requests
 * 
 * This uses a local proxy to intercept HTTP requests from mcp-remote
 * and extract the Authorization token.
 */

const http = require('http');
const https = require('https');
const { spawn } = require('child_process');
const { URL } = require('url');
const fs = require('fs');
const path = require('path');

const PROXY_PORT = 8888;
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

let capturedToken = null;

// Create proxy server to intercept requests
const proxy = http.createServer((req, res) => {
  const targetUrl = new URL(req.url, `http://localhost:${PROXY_PORT}`);
  
  // Only intercept requests to mcp.atlassian.com
  if (!targetUrl.pathname.includes('mcp.atlassian.com')) {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  // Check for Authorization header
  const authHeader = req.headers['authorization'];
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.substring(7);
    if (token.length > 50 && !capturedToken) {
      capturedToken = token;
      console.log('\n✓✓✓ TOKEN CAPTURED! ✓✓✓');
      console.log(`Token: ${token.substring(0, 50)}...`);
      fs.writeFileSync(TOKEN_FILE, token);
      console.log(`✓ Token saved to: ${TOKEN_FILE}`);
    }
  }

  // Forward request
  const options = {
    hostname: 'mcp.atlassian.com',
    port: 443,
    path: targetUrl.pathname + targetUrl.search,
    method: req.method,
    headers: req.headers
  };

  const proxyReq = https.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  req.pipe(proxyReq);
});

proxy.listen(PROXY_PORT, () => {
  console.log(`Proxy listening on port ${PROXY_PORT}`);
  console.log('This won\'t work directly - mcp-remote doesn\'t use HTTP proxy');
  console.log('Trying alternative approach...');
});

// Alternative: Check mcp-remote's process environment or files
console.log('Checking for token in mcp-remote storage...');

// Common locations where mcp-remote might store tokens
const possibleLocations = [
  path.join(process.env.HOME, '.mcp-remote'),
  path.join(process.env.HOME, '.config', 'mcp-remote'),
  path.join(process.env.HOME, '.cache', 'mcp-remote'),
  path.join(process.env.HOME, 'Library', 'Application Support', 'mcp-remote'),
];

for (const location of possibleLocations) {
  if (fs.existsSync(location)) {
    console.log(`Found: ${location}`);
    try {
      if (fs.statSync(location).isDirectory()) {
        const files = fs.readdirSync(location);
        for (const file of files) {
          const filePath = path.join(location, file);
          const content = fs.readFileSync(filePath, 'utf8');
          
          // Look for token patterns
          const tokenMatch = content.match(/"access_token"\s*:\s*"([^"]+)"/);
          if (tokenMatch) {
            const token = tokenMatch[1];
            console.log(`\n✓✓✓ TOKEN FOUND IN FILE! ✓✓✓`);
            console.log(`File: ${filePath}`);
            console.log(`Token: ${token.substring(0, 50)}...`);
            fs.writeFileSync(TOKEN_FILE, token);
            console.log(`✓ Token saved to: ${TOKEN_FILE}`);
            process.exit(0);
          }
        }
      }
    } catch (e) {
      // Ignore errors
    }
  }
}

console.log('\n⚠️  Token not found in common locations.');
console.log('\nAlternative: Use browser to capture token');
console.log('1. Run: mcp-remote https://mcp.atlassian.com/v1/mcp');
console.log('2. In Chrome/Edge (not Safari), open DevTools');
console.log('3. Network tab → Filter: mcp.atlassian.com');
console.log('4. Look for Authorization header');

