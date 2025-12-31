#!/usr/bin/env node
/**
 * Test MCP Server Authentication Methods
 * 
 * Tries different ways to authenticate with the MCP server
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');

const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

console.log('='.repeat(60));
console.log('Testing MCP Server Authentication');
console.log('='.repeat(60));
console.log();

// Test 1: Try with proper MCP initialize request
console.log('Test 1: MCP Initialize Request');
console.log('='.repeat(60));

const mcpRequest = {
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: {
      tools: {}
    },
    clientInfo: {
      name: 'letta-client',
      version: '1.0.0'
    }
  }
};

const mcpUrl = new URL(ROVO_MCP_URL);
const mcpOptions = {
  hostname: mcpUrl.hostname,
  port: 443,
  path: mcpUrl.pathname,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
};

const mcpReq = https.request(mcpOptions, (res) => {
  console.log(`Status: ${res.statusCode}`);
  console.log(`Headers:`, res.headers);
  
  let body = '';
  res.on('data', (chunk) => {
    body += chunk;
  });
  
  res.on('end', () => {
    console.log(`Response: ${body}`);
    console.log();
    
    if (res.statusCode === 401) {
      console.log('❌ Still requires authentication');
      console.log();
      console.log('The MCP server requires OAuth to be completed first.');
      console.log();
      console.log('SOLUTION:');
      console.log('1. Complete OAuth in browser: https://mcp.atlassian.com/v1/sse');
      console.log('2. After OAuth, the MCP server stores your session');
      console.log('3. The session is tied to your browser/IP');
      console.log();
      console.log('Since the session is server-side, you have two options:');
      console.log();
      console.log('Option A: Use Letta to connect - it should trigger OAuth');
      console.log('Option B: Extract cookies from browser after OAuth');
      console.log('   - Open DevTools → Application → Cookies');
      console.log('   - Copy cookies for mcp.atlassian.com');
      console.log('   - Use them in requests');
      console.log();
      
      // Try to get OAuth URL
      try {
        const json = JSON.parse(body);
        if (json.error && json.error.description) {
          console.log('Error details:', json.error.description);
        }
      } catch (e) {
        // Not JSON
      }
    }
  });
});

mcpReq.on('error', (err) => {
  console.error(`Error: ${err.message}`);
});

mcpReq.write(JSON.stringify(mcpRequest));
mcpReq.end();

// Wait a moment, then provide instructions
setTimeout(() => {
  console.log();
  console.log('='.repeat(60));
  console.log('Next Steps');
  console.log('='.repeat(60));
  console.log();
  console.log('The MCP server uses server-side sessions.');
  console.log('To get it working:');
  console.log();
  console.log('1. Open browser: https://mcp.atlassian.com/v1/sse');
  console.log('2. Complete OAuth (login, approve, select apps)');
  console.log('3. After OAuth, get cookies from browser:');
  console.log('   - DevTools (F12) → Application → Cookies → mcp.atlassian.com');
  console.log('   - Copy all cookie values');
  console.log('4. Save cookies:');
  console.log('   echo "cookie1=value1; cookie2=value2" > ~/.atlassian-mcp-cookies.txt');
  console.log('5. Test with cookies:');
  console.log('   node get-token-from-session.js');
  console.log();
  console.log('OR configure Letta to connect - it should handle OAuth automatically.');
  console.log();
}, 2000);

