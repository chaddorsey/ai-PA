#!/usr/bin/env node
/**
 * Try Direct Atlassian OAuth
 * 
 * Since the MCP server callback goes to itself, let's try to
 * use Atlassian's OAuth directly with the authorized app.
 */

const http = require('http');
const https = require('https');
const { URL, URLSearchParams } = require('url');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CLIENT_ID = 'pVrZtjGOkBraHr0ge4iVlstqGVRJfi3'; // From the JWT
const REDIRECT_URI = 'http://localhost:5598/oauth/callback';
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

// Scopes
const SCOPES = [
  'offline_access',
  'read:comment:confluence',
  'read:confluence-user',
  'read:hierarchical-content:confluence',
  'read:jira-work',
  'read:me',
  'read:page:confluence',
  'read:space:confluence',
  'search:confluence',
  'write:comment:confluence',
  'write:jira-work',
  'write:page:confluence'
];

console.log('='.repeat(60));
console.log('Direct Atlassian OAuth (Alternative Approach)');
console.log('='.repeat(60));
console.log();
console.log('Since the MCP server callback goes to itself,');
console.log('we\'ll try using Atlassian OAuth directly.');
console.log();
console.log('⚠️  Note: This may not work if the app requires');
console.log('   the callback to go through the MCP server.');
console.log();

// Generate state
const state = crypto.randomBytes(32).toString('base64url');

// Build OAuth URL - try with the MCP server's callback
// But also set up our own callback server
const authParams = new URLSearchParams({
  audience: 'api.atlassian.com',
  client_id: CLIENT_ID,
  scope: SCOPES.join(' '),
  redirect_uri: 'https://mcp.atlassian.com/v1/callback', // MCP server's callback
  state: state,
  response_type: 'code',
  prompt: 'consent'
});

const authUrl = `https://auth.atlassian.com/authorize?${authParams.toString()}`;

console.log('OAuth URL:');
console.log(authUrl.substring(0, 200) + '...');
console.log();

// Start callback server
console.log('Starting callback server on port 5598...');
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:5598`);
  console.log(`\n[Callback] ${url.pathname}${url.search}`);
  
  // The callback will actually go to mcp.atlassian.com, not here
  // But we can show instructions
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(`
    <html>
      <body>
        <h1>OAuth Callback</h1>
        <p>Note: The actual callback goes to mcp.atlassian.com</p>
        <p>Check the browser URL after OAuth for the authorization code.</p>
      </body>
    </html>
  `);
});

server.listen(5598, () => {
  console.log('✓ Callback server ready');
  console.log();
  console.log('Opening OAuth URL in browser...');
  console.log();
  console.log('⚠️  IMPORTANT:');
  console.log('   The callback will go to: https://mcp.atlassian.com/v1/callback');
  console.log('   After OAuth, check the browser URL for the authorization code.');
  console.log('   Or use DevTools Network tab to capture the token.');
  console.log();
  
  const platform = process.platform;
  let command;
  if (platform === 'darwin') {
    command = 'open';
  } else if (platform === 'win32') {
    command = 'start';
  } else {
    command = 'xdg-open';
  }
  
  spawn(command, [authUrl]);
  
  console.log('Complete OAuth in the browser.');
  console.log('After authorization, the MCP server will receive the token.');
  console.log('You may need to extract it from browser DevTools.');
  console.log();
  console.log('Press Ctrl+C to stop');
});

process.on('SIGINT', () => {
  console.log('\n\nShutting down...');
  server.close();
  process.exit(0);
});

