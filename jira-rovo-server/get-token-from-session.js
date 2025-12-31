#!/usr/bin/env node
/**
 * Get Token from MCP Server Session
 * 
 * After completing OAuth, the MCP server stores your session.
 * This script tries to extract the token or use the session.
 */

const https = require('https');
const { URL } = require('url');
const fs = require('fs');
const path = require('path');

const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

console.log('='.repeat(60));
console.log('Get Token from MCP Server Session');
console.log('='.repeat(60));
console.log();
console.log('Since the OAuth callback goes to the MCP server,');
console.log('the session is stored server-side. We need to:');
console.log('1. Complete OAuth in browser');
console.log('2. Get cookies from browser session');
console.log('3. Use those cookies to access MCP server');
console.log();

// Check if user has cookies
const cookiesFile = path.join(process.env.HOME, '.atlassian-mcp-cookies.txt');
if (fs.existsSync(cookiesFile)) {
  const cookies = fs.readFileSync(cookiesFile, 'utf8').trim();
  console.log('✓ Found cookies file');
  console.log('Testing connection with cookies...');
  console.log();
  
  testWithCookies(cookies);
} else {
  console.log('No cookies file found.');
  console.log();
  console.log('To get cookies from browser:');
  console.log('1. Complete OAuth at: https://mcp.atlassian.com/v1/sse');
  console.log('2. Open DevTools (F12) → Application/Storage tab');
  console.log('3. Go to Cookies → mcp.atlassian.com');
  console.log('4. Copy all cookie values');
  console.log('5. Save to: ~/.atlassian-mcp-cookies.txt');
  console.log('   Format: Cookie: name1=value1; name2=value2');
  console.log();
  console.log('Or use this browser console script:');
  console.log();
  console.log(`
// Run in browser console after OAuth
const cookies = document.cookie;
console.log('Cookies:', cookies);
console.log('Save with: echo "' + cookies + '" > ~/.atlassian-mcp-cookies.txt');
  `);
  console.log();
  
  // Try without cookies first to see what happens
  console.log('Testing connection without cookies...');
  testConnection();
}

function testConnection() {
  const url = new URL(ROVO_SSE_URL);
  const options = {
    hostname: url.hostname,
    port: 443,
    path: url.pathname,
    method: 'GET',
    headers: {
      'Accept': 'text/event-stream',
      'User-Agent': 'MCP-Client/1.0'
    }
  };
  
  const req = https.request(options, (res) => {
    console.log(`Status: ${res.statusCode}`);
    
    if (res.statusCode === 401) {
      console.log('❌ Still getting 401 - need to complete OAuth');
      console.log();
      console.log('The MCP server requires OAuth authentication.');
      console.log('Complete these steps:');
      console.log('1. Open: https://mcp.atlassian.com/v1/sse');
      console.log('2. Complete OAuth authorization');
      console.log('3. Get cookies from browser');
      console.log('4. Run this script again with cookies');
    } else if (res.statusCode === 200) {
      console.log('✓ Connection successful!');
      let body = '';
      res.on('data', (chunk) => {
        body += chunk;
        // Look for token in SSE stream
        const tokenMatch = body.match(/access_token["\s:=]+([^\s"}\n]+)/);
        if (tokenMatch) {
          const token = tokenMatch[1];
          console.log(`\n✓ Token found in response: ${token.substring(0, 50)}...`);
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      });
      res.on('end', () => {
        console.log('Response received');
      });
    }
  });
  
  req.on('error', (err) => {
    console.error(`Error: ${err.message}`);
  });
  
  req.end();
}

function testWithCookies(cookies) {
  const url = new URL(ROVO_SSE_URL);
  const options = {
    hostname: url.hostname,
    port: 443,
    path: url.pathname,
    method: 'GET',
    headers: {
      'Accept': 'text/event-stream',
      'Cookie': cookies,
      'User-Agent': 'MCP-Client/1.0'
    }
  };
  
  const req = https.request(options, (res) => {
    console.log(`Status: ${res.statusCode}`);
    
    if (res.statusCode === 200) {
      console.log('✓ Connection successful with cookies!');
      let body = '';
      res.on('data', (chunk) => {
        body += chunk;
        console.log('Received:', chunk.toString().substring(0, 100));
        
        // Look for token in response
        const tokenMatch = body.match(/access_token["\s:=]+([^\s"}\n]+)/);
        if (tokenMatch) {
          const token = tokenMatch[1];
          console.log(`\n✓ Token found: ${token.substring(0, 50)}...`);
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      });
    } else {
      console.log(`❌ Got ${res.statusCode} - cookies might be invalid or expired`);
      let body = '';
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        console.log('Response:', body);
      });
    }
  });
  
  req.on('error', (err) => {
    console.error(`Error: ${err.message}`);
  });
  
  req.end();
}

