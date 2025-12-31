#!/usr/bin/env node
/**
 * Get Fresh OAuth URL from Rovo MCP Server
 * 
 * The JWT tokens expire quickly, so we need to get a fresh one
 * by connecting to the MCP server.
 */

const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');

const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';

console.log('='.repeat(60));
console.log('Get Fresh OAuth URL from Rovo MCP');
console.log('='.repeat(60));
console.log();
console.log('The JWT in OAuth URLs expires after ~1 hour.');
console.log('We need to get a fresh one by connecting to the MCP server.');
console.log();
console.log('Opening MCP endpoint in browser...');
console.log('This should redirect you to a fresh OAuth consent page.');
console.log();

// Open the MCP endpoint in browser - this should trigger a fresh OAuth flow
const platform = process.platform;
let command;
if (platform === 'darwin') {
  command = 'open';
} else if (platform === 'win32') {
  command = 'start';
} else {
  command = 'xdg-open';
}

spawn(command, [ROVO_SSE_URL]);

console.log('✓ Browser opened');
console.log();
console.log('What to do:');
console.log('1. In the browser, you should see an OAuth consent page');
console.log('2. Complete the authorization quickly (before it expires)');
console.log('3. After authorization, the MCP server will receive the token');
console.log();
console.log('Note: The callback goes to the MCP server, not localhost.');
console.log('The MCP server will store your session.');
console.log();
console.log('After authorization, you can test the connection:');
console.log('  curl "https://mcp.atlassian.com/v1/sse" -H "Accept: text/event-stream"');
console.log();
console.log('Or configure Letta to use the MCP server - it should work');
console.log('once you\'ve completed the OAuth flow through the browser.');
console.log();

