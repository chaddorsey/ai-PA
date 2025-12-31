#!/usr/bin/env node
/**
 * Get OAuth URL from Rovo MCP Server
 * 
 * Connects to the MCP server and captures the OAuth redirect URL
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');

const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

console.log('='.repeat(60));
console.log('Getting OAuth URL from Rovo MCP Server');
console.log('='.repeat(60));
console.log();

// Try SSE endpoint first
console.log('Step 1: Connecting to SSE endpoint...');
console.log(`URL: ${ROVO_SSE_URL}`);
console.log();

const sseUrl = new URL(ROVO_SSE_URL);
const sseOptions = {
  hostname: sseUrl.hostname,
  port: 443,
  path: sseUrl.pathname,
  method: 'GET',
  headers: {
    'Accept': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'User-Agent': 'MCP-Client/1.0'
  }
};

const sseReq = https.request(sseOptions, (res) => {
  console.log(`Response status: ${res.statusCode}`);
  console.log(`Response headers:`, res.headers);
  
  // Check for redirect
  if (res.statusCode >= 300 && res.statusCode < 400) {
    const location = res.headers.location;
    if (location) {
      console.log(`\n✓✓✓ REDIRECT TO OAUTH FOUND! ✓✓✓`);
      console.log(`\nOAuth URL: ${location}`);
      console.log();
      console.log('Opening in browser...');
      
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
      
      console.log('\n✓ Browser should have opened with the OAuth URL');
      console.log('Complete the authentication there.');
      process.exit(0);
    }
  }
  
  // Check for 401 - might have OAuth info in headers
  if (res.statusCode === 401) {
    const wwwAuth = res.headers['www-authenticate'];
    const location = res.headers.location;
    
    if (location) {
      console.log(`\n✓ Found OAuth URL in Location header: ${location}`);
      console.log('\nOpening in browser...');
      
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
      process.exit(0);
    }
    
    if (wwwAuth) {
      console.log(`WWW-Authenticate: ${wwwAuth}`);
    }
  }
  
  // Read response body
  let body = '';
  res.on('data', (chunk) => {
    body += chunk;
  });
  
  res.on('end', () => {
    console.log(`\nResponse body: ${body.substring(0, 500)}`);
    
    // Try to extract OAuth URL from response
    const oauthMatch = body.match(/https?:\/\/[^\s"']*auth\.atlassian\.com[^\s"']*/);
    if (oauthMatch) {
      console.log(`\n✓ Found OAuth URL in response: ${oauthMatch[0]}`);
      console.log('\nOpening in browser...');
      
      const platform = process.platform;
      let command;
      if (platform === 'darwin') {
        command = 'open';
      } else if (platform === 'win32') {
        command = 'start';
      } else {
        command = 'xdg-open';
      }
      
      spawn(command, [oauthMatch[0]]);
      process.exit(0);
    }
    
    // If SSE didn't work, try MCP endpoint
    console.log('\nSSE endpoint didn\'t provide OAuth URL. Trying MCP endpoint...');
    tryMCPEndpoint();
  });
});

sseReq.on('error', (err) => {
  console.error(`SSE request error: ${err.message}`);
  console.log('\nTrying MCP endpoint...');
  tryMCPEndpoint();
});

sseReq.end();

function tryMCPEndpoint() {
  console.log('\nStep 2: Trying MCP endpoint...');
  console.log(`URL: ${ROVO_MCP_URL}`);
  console.log();
  
  const mcpUrl = new URL(ROVO_MCP_URL);
  const mcpRequest = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'oauth-helper',
        version: '1.0.0'
      }
    }
  };
  
  const mcpOptions = {
    hostname: mcpUrl.hostname,
    port: 443,
    path: mcpUrl.pathname,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'MCP-Client/1.0'
    }
  };
  
  const mcpReq = https.request(mcpOptions, (res) => {
    console.log(`Response status: ${res.statusCode}`);
    console.log(`Response headers:`, res.headers);
    
    // Check for redirect
    if (res.statusCode >= 300 && res.statusCode < 400) {
      const location = res.headers.location;
      if (location) {
        console.log(`\n✓✓✓ REDIRECT TO OAUTH FOUND! ✓✓✓`);
        console.log(`\nOAuth URL: ${location}`);
        console.log('\nOpening in browser...');
        
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
        process.exit(0);
      }
    }
    
    let body = '';
    res.on('data', (chunk) => {
      body += chunk;
    });
    
    res.on('end', () => {
      console.log(`\nResponse body: ${body.substring(0, 500)}`);
      
      try {
        const json = JSON.parse(body);
        console.log('\nParsed JSON response:');
        console.log(JSON.stringify(json, null, 2));
        
        // Look for OAuth URL in response
        const findOAuthUrl = (obj) => {
          if (typeof obj === 'string' && obj.includes('auth.atlassian.com')) {
            return obj;
          }
          if (typeof obj === 'object' && obj !== null) {
            for (const value of Object.values(obj)) {
              const found = findOAuthUrl(value);
              if (found) return found;
            }
          }
          return null;
        };
        
        const oauthUrl = findOAuthUrl(json);
        if (oauthUrl) {
          console.log(`\n✓ Found OAuth URL: ${oauthUrl}`);
          console.log('\nOpening in browser...');
          
          const platform = process.platform;
          let command;
          if (platform === 'darwin') {
            command = 'open';
          } else if (platform === 'win32') {
            command = 'start';
          } else {
            command = 'xdg-open';
          }
          
          spawn(command, [oauthUrl]);
          process.exit(0);
        }
      } catch (e) {
        // Not JSON
      }
      
      // Try regex search
      const oauthMatch = body.match(/https?:\/\/[^\s"']*auth\.atlassian\.com[^\s"']*/);
      if (oauthMatch) {
        console.log(`\n✓ Found OAuth URL: ${oauthMatch[0]}`);
        console.log('\nOpening in browser...');
        
        const platform = process.platform;
        let command;
        if (platform === 'darwin') {
          command = 'open';
        } else if (platform === 'win32') {
          command = 'start';
        } else {
          command = 'xdg-open';
        }
        
        spawn(command, [oauthMatch[0]]);
        process.exit(0);
      }
      
      console.log('\n❌ Could not find OAuth URL in response');
      console.log('\nThe MCP server may require a different connection method.');
      console.log('Try accessing it through a browser or MCP client.');
      process.exit(1);
    });
  });
  
  mcpReq.on('error', (err) => {
    console.error(`MCP request error: ${err.message}`);
    console.log('\n❌ Could not connect to MCP server');
    process.exit(1);
  });
  
  mcpReq.write(JSON.stringify(mcpRequest));
  mcpReq.end();
}

