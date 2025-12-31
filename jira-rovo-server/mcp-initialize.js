#!/usr/bin/env node
/**
 * MCP Initialize Request
 * 
 * Makes a proper MCP protocol initialize request to trigger OAuth
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');

const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

console.log('='.repeat(60));
console.log('MCP Initialize Request');
console.log('='.repeat(60));
console.log();

const initializeRequest = {
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: {
      name: 'node-mcp-client',
      version: '1.0.0'
    }
  }
};

const url = new URL(ROVO_MCP_URL);
const postData = JSON.stringify(initializeRequest);

const options = {
  hostname: url.hostname,
  port: 443,
  path: url.pathname,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Content-Length': Buffer.byteLength(postData),
    'User-Agent': 'MCP-Client/1.0'
  }
};

console.log('Making MCP initialize request...');
console.log(`URL: ${ROVO_MCP_URL}`);
console.log(`Request:`, JSON.stringify(initializeRequest, null, 2));
console.log();

const req = https.request(options, (res) => {
  console.log(`Status: ${res.statusCode}`);
  console.log(`Headers:`, res.headers);
  console.log();
  
  // Check for redirect
  if (res.statusCode >= 300 && res.statusCode < 400) {
    const location = res.headers.location;
    if (location) {
      console.log('✓✓✓ REDIRECT TO OAUTH! ✓✓✓');
      console.log(`Location: ${location}`);
      console.log();
      console.log('Opening browser...');
      
      const platform = process.platform;
      const command = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';
      spawn(command, [location]);
      return;
    }
  }
  
  let body = '';
  res.on('data', (chunk) => {
    body += chunk;
  });
  
  res.on('end', () => {
    console.log('Response body:');
    try {
      const json = JSON.parse(body);
      console.log(JSON.stringify(json, null, 2));
      
      // Check for OAuth URL in response
      if (json.error && json.error.data && json.error.data.oauth_url) {
        console.log();
        console.log('✓✓✓ OAUTH URL IN RESPONSE! ✓✓✓');
        console.log(`OAuth URL: ${json.error.data.oauth_url}`);
        console.log();
        console.log('Opening browser...');
        
        const platform = process.platform;
        const command = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';
        spawn(command, [json.error.data.oauth_url]);
      } else if (json.result && json.result.oauth_url) {
        console.log();
        console.log('✓✓✓ OAUTH URL IN RESULT! ✓✓✓');
        console.log(`OAuth URL: ${json.result.oauth_url}`);
        console.log();
        console.log('Opening browser...');
        
        const platform = process.platform;
        const command = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';
        spawn(command, [json.result.oauth_url]);
      }
    } catch (e) {
      console.log(body);
    }
  });
});

req.on('error', (err) => {
  console.error(`Error: ${err.message}`);
});

req.write(postData);
req.end();

