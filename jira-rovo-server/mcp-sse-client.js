#!/usr/bin/env node
/**
 * MCP SSE Client
 * 
 * Connects to the SSE endpoint and handles MCP protocol events
 * to trigger OAuth flow
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');
const readline = require('readline');

const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';

console.log('='.repeat(60));
console.log('MCP SSE Client - OAuth Trigger');
console.log('='.repeat(60));
console.log();
console.log('Connecting to SSE endpoint...');
console.log(`URL: ${ROVO_SSE_URL}`);
console.log();
console.log('This will:');
console.log('1. Connect as an MCP client');
console.log('2. Listen for OAuth redirects in the event stream');
console.log('3. Open browser if OAuth URL is detected');
console.log();

const url = new URL(ROVO_SSE_URL);

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
  console.log(`Status: ${res.statusCode}`);
  console.log(`Headers:`, Object.keys(res.headers));
  console.log();
  
  // Check for redirect
  if (res.statusCode >= 300 && res.statusCode < 400) {
    const location = res.headers.location;
    if (location) {
      console.log('✓✓✓ REDIRECT TO OAUTH! ✓✓✓');
      console.log(`Location: ${location.substring(0, 200)}...`);
      openBrowser(location);
      return;
    }
  }
  
  // Check Content-Type
  const contentType = res.headers['content-type'] || '';
  if (!contentType.includes('text/event-stream') && res.statusCode !== 200) {
    // Not an event stream, read as regular response
    let body = '';
    res.on('data', (chunk) => {
      body += chunk;
    });
    res.on('end', () => {
      console.log('Response:');
      console.log(body);
      
      // Try to extract OAuth URL from JSON response
      try {
        const json = JSON.parse(body);
        if (json.error && json.error.data && json.error.data.oauth_url) {
          openBrowser(json.error.data.oauth_url);
        } else if (json.oauth_url) {
          openBrowser(json.oauth_url);
        }
      } catch (e) {
        // Not JSON, check for URL in text
        const urlMatch = body.match(/https?:\/\/[^\s"<>]+oauth[^\s"<>]+/i);
        if (urlMatch) {
          console.log('\n✓ Found OAuth URL in response!');
          openBrowser(urlMatch[0]);
        }
      }
    });
    return;
  }
  
  // Handle event stream
  console.log('Reading event stream...');
  console.log('(Press Ctrl+C to stop)');
  console.log();
  
  let buffer = '';
  
  res.on('data', (chunk) => {
    buffer += chunk.toString();
    
    // Process complete events
    const lines = buffer.split('\n');
    buffer = lines.pop() || ''; // Keep incomplete line in buffer
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.substring(6);
        try {
          const json = JSON.parse(data);
          console.log('Event:', JSON.stringify(json, null, 2));
          
          // Check for OAuth URL in event data
          if (json.error && json.error.data && json.error.data.oauth_url) {
            console.log('\n✓✓✓ OAUTH URL IN EVENT! ✓✓✓');
            openBrowser(json.error.data.oauth_url);
          } else if (json.result && json.result.oauth_url) {
            console.log('\n✓✓✓ OAUTH URL IN RESULT! ✓✓✓');
            openBrowser(json.result.oauth_url);
          } else if (json.params && json.params.oauth_url) {
            console.log('\n✓✓✓ OAUTH URL IN PARAMS! ✓✓✓');
            openBrowser(json.params.oauth_url);
          }
        } catch (e) {
          // Not JSON, check for URL
          const urlMatch = data.match(/https?:\/\/[^\s"<>]+oauth[^\s"<>]+/i);
          if (urlMatch) {
            console.log('\n✓ Found OAuth URL in event!');
            openBrowser(urlMatch[0]);
          }
        }
      } else if (line.startsWith('event: ')) {
        console.log(`Event type: ${line.substring(7)}`);
      } else if (line.trim()) {
        console.log(`Raw: ${line}`);
      }
    }
  });
  
  res.on('end', () => {
    console.log('\nConnection closed.');
  });
});

req.on('error', (err) => {
  console.error(`Error: ${err.message}`);
});

function openBrowser(url) {
  console.log(`\nOpening browser: ${url.substring(0, 150)}...`);
  console.log();
  console.log('Complete OAuth in the browser.');
  console.log('After authorization, check DevTools Network tab for token.');
  console.log();
  
  const platform = process.platform;
  const command = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';
  spawn(command, [url]);
}

req.end();

// Keep process alive
process.on('SIGINT', () => {
  console.log('\n\nStopping...');
  req.destroy();
  process.exit(0);
});

