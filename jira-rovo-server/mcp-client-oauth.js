#!/usr/bin/env node
/**
 * Simple MCP Client to Trigger OAuth
 * 
 * This script acts as a minimal MCP client that connects to the Rovo MCP server
 * and triggers the OAuth flow, then captures the token.
 */

const https = require('https');
const http = require('http');
const { URL } = require('url');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

console.log('='.repeat(60));
console.log('MCP Client - Trigger OAuth for Atlassian Rovo');
console.log('='.repeat(60));
console.log();
console.log('This script acts as an MCP client to trigger OAuth.');
console.log('Based on: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/using-with-other-supported-mcp-clients/');
console.log();

// Step 1: Make MCP initialize request
console.log('Step 1: Connecting to MCP server as an MCP client...');
console.log(`URL: ${ROVO_SSE_URL}`);
console.log();

const url = new URL(ROVO_SSE_URL);

// Make request with proper MCP client headers
const options = {
  hostname: url.hostname,
  port: 443,
  path: url.pathname,
  method: 'GET',
  headers: {
    'Accept': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'User-Agent': 'MCP-Client/1.0',
    'X-MCP-Version': '2024-11-05'
  }
};

const req = https.request(options, (res) => {
  console.log(`Response status: ${res.statusCode}`);
  console.log(`Response headers:`, Object.keys(res.headers));
  
  // Check for redirect to OAuth
  if (res.statusCode >= 300 && res.statusCode < 400) {
    const location = res.headers.location;
    if (location) {
      console.log(`\n✓✓✓ OAUTH REDIRECT DETECTED! ✓✓✓`);
      console.log(`OAuth URL: ${location.substring(0, 150)}...`);
      console.log();
      console.log('Opening browser for OAuth...');
      
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
      console.log();
      console.log('Complete OAuth in the browser.');
      console.log('After authorization, check browser DevTools Network tab');
      console.log('for the token in Authorization headers or responses.');
      return;
    }
  }
  
  // Read response
  let body = '';
  res.on('data', (chunk) => {
    body += chunk;
  });
  
  res.on('end', () => {
    console.log(`Response: ${body.substring(0, 300)}`);
    
    if (res.statusCode === 401) {
      console.log();
      console.log('❌ Got 401 - OAuth not triggered automatically');
      console.log();
      console.log('The MCP server requires OAuth but didn\'t redirect.');
      console.log('This might mean:');
      console.log('1. The server needs a proper MCP protocol handshake');
      console.log('2. Or it needs to be accessed through Letta\'s interface');
      console.log();
      console.log('Try using Postman to make an MCP initialize request:');
      console.log();
      console.log('POST https://mcp.atlassian.com/v1/mcp');
      console.log('Headers:');
      console.log('  Content-Type: application/json');
      console.log('Body:');
      console.log(JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: '2024-11-05',
          capabilities: {},
          clientInfo: {
            name: 'postman-client',
            version: '1.0.0'
          }
        }
      }, null, 2));
    }
  });
});

req.on('error', (err) => {
  console.error(`Error: ${err.message}`);
});

req.end();

