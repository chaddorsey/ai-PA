#!/usr/bin/env node
/**
 * Simple MCP Proxy for Atlassian Rovo
 * 
 * This script acts as a proxy to the Rovo MCP server and captures
 * the OAuth token from the authentication flow.
 */

const http = require('http');
const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');

const PROXY_PORT = 5598;
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/sse';
const CALLBACK_PATH = '/oauth/callback';

// Store captured token
let capturedToken = null;
let capturedCode = null;

console.log('='.repeat(60));
console.log('MCP Proxy for Atlassian Rovo');
console.log('='.repeat(60));
console.log();
console.log(`Proxy listening on: http://localhost:${PROXY_PORT}`);
console.log(`Target: ${ROVO_MCP_URL}`);
console.log();

// Create proxy server
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PROXY_PORT}`);
  
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  
  // Handle OAuth callback
  if (url.pathname === CALLBACK_PATH) {
    const params = url.searchParams;
    
    console.log('\n[OAuth Callback] Received callback');
    console.log(`Query params: ${url.search}`);
    
    // Check for access_token
    if (params.has('access_token')) {
      capturedToken = params.get('access_token');
      console.log(`\n✓ Access token captured!`);
      console.log(`Token: ${capturedToken.substring(0, 50)}...`);
      
      // Save token to file
      const fs = require('fs');
      const path = require('path');
      const tokenFile = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
      fs.writeFileSync(tokenFile, capturedToken);
      console.log(`✓ Token saved to: ${tokenFile}`);
      
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`
        <html>
          <body>
            <h1>Token Captured!</h1>
            <p>Token has been saved. You can close this window.</p>
            <p>Check the terminal for the token location.</p>
          </body>
        </html>
      `);
      return;
    }
    
    // Check for authorization code
    if (params.has('code')) {
      capturedCode = params.get('code');
      console.log(`\n✓ Authorization code captured!`);
      console.log(`Code: ${capturedCode.substring(0, 30)}...`);
      console.log(`\n⚠️  This is an authorization code, not an access token.`);
      console.log(`   It needs to be exchanged for a token.`);
      
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`
        <html>
          <body>
            <h1>Code Captured!</h1>
            <p>Authorization code received. Check terminal for details.</p>
          </body>
        </html>
      `);
      return;
    }
    
    // Check for error
    if (params.has('error')) {
      const error = params.get('error');
      const errorDesc = params.get('error_description') || '';
      console.log(`\n❌ OAuth Error: ${error}`);
      console.log(`   Description: ${errorDesc}`);
      
      res.writeHead(400, { 'Content-Type': 'text/html' });
      res.end(`
        <html>
          <body>
            <h1>OAuth Error</h1>
            <p>${error}: ${errorDesc}</p>
          </body>
        </html>
      `);
      return;
    }
    
    // Default callback response
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`
      <html>
        <body>
          <h1>Waiting for OAuth callback...</h1>
          <p>Complete the authentication in the browser.</p>
        </body>
      </html>
    `);
    return;
  }
  
  // Proxy requests to Rovo MCP server
  const targetUrl = new URL(ROVO_MCP_URL);
  const options = {
    hostname: targetUrl.hostname,
    port: targetUrl.port || 443,
    path: targetUrl.pathname + url.search,
    method: req.method,
    headers: {
      ...req.headers,
      host: targetUrl.hostname
    }
  };
  
  // Remove headers that shouldn't be forwarded
  delete options.headers['host'];
  delete options.headers['connection'];
  
  const proxyReq = https.request(options, (proxyRes) => {
    // Check for redirects to OAuth
    if (proxyRes.statusCode >= 300 && proxyRes.statusCode < 400) {
      const location = proxyRes.headers.location;
      if (location && location.includes('auth.atlassian.com')) {
        console.log(`\n[Redirect] OAuth URL detected: ${location.substring(0, 100)}...`);
        console.log(`\nOpening browser for OAuth...`);
        
        // Open browser
        const platform = process.platform;
        let command;
        
        if (platform === 'darwin') {
          command = 'open';
        } else if (platform === 'win32') {
          command = 'start';
        } else {
          command = 'xdg-open';
        }
        
        spawn(command, [location]);
        
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(`
          <html>
            <body>
              <h1>Redirecting to OAuth...</h1>
              <p>If browser doesn't open, <a href="${location}">click here</a></p>
              <script>window.location.href = "${location}";</script>
            </body>
          </html>
        `);
        return;
      }
    }
    
    // Forward response
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  
  proxyReq.on('error', (err) => {
    console.error(`[Proxy Error] ${err.message}`);
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end(`Proxy error: ${err.message}`);
  });
  
  req.pipe(proxyReq);
});

server.listen(PROXY_PORT, () => {
  console.log(`✓ Proxy server started on port ${PROXY_PORT}`);
  console.log();
  console.log('To connect to Rovo MCP through this proxy:');
  console.log(`  http://localhost:${PROXY_PORT}/v1/sse`);
  console.log();
  console.log('The proxy will:');
  console.log('  1. Forward requests to Rovo MCP server');
  console.log('  2. Detect OAuth redirects');
  console.log('  3. Open browser for authentication');
  console.log('  4. Capture token from callback');
  console.log();
  console.log('Press Ctrl+C to stop');
  console.log();
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\nShutting down proxy...');
  if (capturedToken) {
    console.log(`\n✓ Token was captured: ${capturedToken.substring(0, 50)}...`);
  } else if (capturedCode) {
    console.log(`\n⚠️  Authorization code captured (needs exchange): ${capturedCode.substring(0, 30)}...`);
  } else {
    console.log('\n⚠️  No token or code captured');
  }
  process.exit(0);
});

