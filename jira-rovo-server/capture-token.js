#!/usr/bin/env node
/**
 * Capture OAuth Token from Atlassian Rovo MCP
 * 
 * This script starts a local server to capture the OAuth callback
 * and opens your browser to complete the authentication.
 */

const http = require('http');
const { URL } = require('url');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const PORT = 5598;
const CALLBACK_PATH = '/oauth/callback';
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

let capturedToken = null;
let capturedCode = null;

console.log('='.repeat(60));
console.log('Atlassian Rovo OAuth Token Capture');
console.log('='.repeat(60));
console.log();
console.log(`Listening on: http://localhost:${PORT}${CALLBACK_PATH}`);
console.log();

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  
  console.log(`[${new Date().toISOString()}] ${req.method} ${url.pathname}`);
  
  if (url.pathname === CALLBACK_PATH) {
    const params = url.searchParams;
    
    console.log('\n[OAuth Callback]');
    console.log(`Full URL: ${url.href}`);
    console.log(`Query: ${url.search}`);
    
    // Check for access_token
    if (params.has('access_token')) {
      capturedToken = params.get('access_token');
      console.log(`\n✓✓✓ ACCESS TOKEN CAPTURED! ✓✓✓`);
      console.log(`Token: ${capturedToken.substring(0, 50)}...`);
      
      fs.writeFileSync(TOKEN_FILE, capturedToken);
      console.log(`✓ Token saved to: ${TOKEN_FILE}`);
      
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`
        <html>
          <head><title>Token Captured</title></head>
          <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1 style="color: green;">✓ Token Captured!</h1>
            <p>Your access token has been saved.</p>
            <p>You can close this window.</p>
            <p style="margin-top: 30px; color: #666;">Check the terminal for details.</p>
          </body>
        </html>
      `);
      
      setTimeout(() => {
        console.log('\n' + '='.repeat(60));
        console.log('SUCCESS!');
        console.log('='.repeat(60));
        console.log(`Token saved to: ${TOKEN_FILE}`);
        console.log(`\nUse it with: export ATLASSIAN_ROVO_TOKEN=$(cat ${TOKEN_FILE})`);
        process.exit(0);
      }, 1000);
      return;
    }
    
    // Check for authorization code
    if (params.has('code')) {
      capturedCode = params.get('code');
      console.log(`\n✓ Authorization code captured!`);
      console.log(`Code: ${capturedCode}`);
      console.log(`\n⚠️  This is an authorization code, not an access token.`);
      console.log(`   It needs to be exchanged for a token.`);
      
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`
        <html>
          <head><title>Code Captured</title></head>
          <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1>Authorization Code Received</h1>
            <p>Check the terminal for next steps.</p>
            <p style="margin-top: 20px; color: #666;">Code: ${capturedCode.substring(0, 30)}...</p>
          </body>
        </html>
      `);
      
      // Save code for reference
      const codeFile = path.join(process.env.HOME, '.atlassian-rovo-code.txt');
      fs.writeFileSync(codeFile, capturedCode);
      console.log(`Code saved to: ${codeFile}`);
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
          <head><title>OAuth Error</title></head>
          <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">OAuth Error</h1>
            <p><strong>${error}</strong></p>
            <p>${errorDesc}</p>
          </body>
        </html>
      `);
      return;
    }
    
    // Default - waiting
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`
      <html>
        <head><title>Waiting...</title></head>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
          <h1>Waiting for OAuth callback...</h1>
          <p>Complete the authentication in the browser.</p>
        </body>
      </html>
    `);
    return;
  }
  
  // Root or other paths
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(`
    <html>
      <head><title>OAuth Callback Server</title></head>
      <body style="font-family: Arial; padding: 40px; text-align: center;">
        <h1>OAuth Callback Server</h1>
        <p>Waiting for OAuth callback...</p>
        <p style="margin-top: 30px; color: #666;">Callback URL: <code>http://localhost:${PORT}${CALLBACK_PATH}</code></p>
      </body>
    </html>
  `);
});

server.listen(PORT, () => {
  console.log(`✓ Server started on port ${PORT}`);
  console.log();
  console.log('Now, complete the OAuth flow:');
  console.log('1. Go back to the authorization page you saw earlier');
  console.log('2. Click "Approve" or "Authorize"');
  console.log('3. Complete the Atlassian login');
  console.log('4. The callback will be captured here');
  console.log();
  console.log('Or, if you have the OAuth URL, open it in your browser.');
  console.log();
  console.log('Waiting for OAuth callback...');
  console.log('(Press Ctrl+C to stop)');
  console.log();
});

process.on('SIGINT', () => {
  console.log('\n\nShutting down...');
  if (capturedToken) {
    console.log(`\n✓ Token was captured: ${capturedToken.substring(0, 50)}...`);
  } else if (capturedCode) {
    console.log(`\n⚠️  Authorization code captured: ${capturedCode.substring(0, 30)}...`);
  } else {
    console.log('\n⚠️  No token or code captured');
  }
  process.exit(0);
});

