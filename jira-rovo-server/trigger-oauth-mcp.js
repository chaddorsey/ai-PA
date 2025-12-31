#!/usr/bin/env node
/**
 * Trigger OAuth by Making Proper MCP Client Request
 * 
 * The MCP server requires OAuth to be initiated through an MCP client.
 * This script makes a proper MCP initialize request that should trigger OAuth.
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');
const http = require('http');

const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';
const CALLBACK_PORT = 5598;

console.log('='.repeat(60));
console.log('Trigger OAuth via MCP Client Request');
console.log('='.repeat(60));
console.log();

// Start a callback server first
console.log('Step 1: Starting callback server...');
const callbackServer = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${CALLBACK_PORT}`);
  console.log(`\n[Callback] Received: ${url.pathname}${url.search}`);
  
  // Check for token
  if (url.searchParams.has('access_token')) {
    const token = url.searchParams.get('access_token');
    console.log(`\n✓✓✓ TOKEN RECEIVED! ✓✓✓`);
    console.log(`Token: ${token.substring(0, 50)}...`);
    
    const fs = require('fs');
    const path = require('path');
    const tokenFile = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
    fs.writeFileSync(tokenFile, token);
    console.log(`✓ Token saved to: ${tokenFile}`);
    
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('<html><body><h1>Token Captured!</h1></body></html>');
    
    setTimeout(() => {
      callbackServer.close();
      process.exit(0);
    }, 1000);
    return;
  }
  
  // Check for code
  if (url.searchParams.has('code')) {
    const code = url.searchParams.get('code');
    console.log(`\n✓ Authorization code received: ${code.substring(0, 30)}...`);
    console.log('⚠️  This needs to be exchanged for a token');
  }
  
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end('<html><body><h1>Waiting...</h1></body></html>');
});

callbackServer.listen(CALLBACK_PORT, () => {
  console.log(`✓ Callback server listening on port ${CALLBACK_PORT}`);
  console.log();
  
  // Now make MCP initialize request
  console.log('Step 2: Making MCP initialize request...');
  console.log(`URL: ${ROVO_MCP_URL}`);
  console.log();
  
  const mcpUrl = new URL(ROVO_MCP_URL);
  
  // Make request with proper MCP client headers
  const mcpRequest = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {
        tools: {},
        prompts: {}
      },
      clientInfo: {
        name: 'letta-mcp-client',
        version: '1.0.0'
      }
    }
  };
  
  const options = {
    hostname: mcpUrl.hostname,
    port: 443,
    path: mcpUrl.pathname,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'MCP-Client/1.0',
      // Try adding callback header
      'X-Callback-URI': `http://localhost:${CALLBACK_PORT}/oauth/callback`
    },
    // Don't follow redirects automatically
    maxRedirects: 0
  };
  
  const req = https.request(options, (res) => {
    console.log(`Response status: ${res.statusCode}`);
    console.log(`Response headers:`, Object.keys(res.headers));
    
    // Check for redirect to OAuth
    if (res.statusCode >= 300 && res.statusCode < 400) {
      const location = res.headers.location;
      if (location) {
        console.log(`\n✓✓✓ OAUTH REDIRECT FOUND! ✓✓✓`);
        console.log(`OAuth URL: ${location.substring(0, 150)}...`);
        console.log();
        console.log('Opening in browser...');
        
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
        console.log('Complete OAuth in the browser window.');
        console.log('The callback server will capture the token.');
        return;
      }
    }
    
    // Read response
    let body = '';
    res.on('data', (chunk) => {
      body += chunk;
    });
    
    res.on('end', () => {
      console.log(`Response body: ${body.substring(0, 300)}`);
      
      // Try to parse JSON
      try {
        const json = JSON.parse(body);
        console.log('\nParsed response:');
        console.log(JSON.stringify(json, null, 2));
        
        // Check for OAuth URL in error or response
        if (json.error) {
          console.log(`\nError: ${json.error.message || json.error}`);
          
          // Some servers return OAuth URL in error data
          if (json.error.data && json.error.data.oauth_url) {
            const oauthUrl = json.error.data.oauth_url;
            console.log(`\n✓ Found OAuth URL in error: ${oauthUrl}`);
            spawn('open', [oauthUrl]);
          }
        }
      } catch (e) {
        // Not JSON
      }
      
      if (res.statusCode === 401) {
        console.log('\n❌ Got 401 - OAuth not triggered');
        console.log('The MCP server may require:');
        console.log('1. A proper MCP client (like Letta)');
        console.log('2. Or specific headers/parameters');
        console.log('3. Or the OAuth flow to be initiated differently');
      }
    });
  });
  
  req.on('error', (err) => {
    console.error(`Request error: ${err.message}`);
    callbackServer.close();
    process.exit(1);
  });
  
  req.write(JSON.stringify(mcpRequest));
  req.end();
  
  console.log('Waiting for OAuth callback...');
  console.log('(Press Ctrl+C to stop)');
});

process.on('SIGINT', () => {
  console.log('\n\nShutting down...');
  callbackServer.close();
  process.exit(0);
});

