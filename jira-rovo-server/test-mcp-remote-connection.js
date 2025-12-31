#!/usr/bin/env node
/**
 * Test mcp-remote connection and try to extract token
 * 
 * Since mcp-remote uses stdio, we need to communicate with it
 * via the MCP protocol to see if it's authenticated.
 */

const { spawn } = require('child_process');
const readline = require('readline');

console.log('='.repeat(60));
console.log('Test mcp-remote Connection');
console.log('='.repeat(60));
console.log();

// Start mcp-remote
console.log('Starting mcp-remote...');
const mcpRemote = spawn('mcp-remote', ['https://mcp.atlassian.com/v1/mcp'], {
  stdio: ['pipe', 'pipe', 'pipe']
});

let output = '';
let errorOutput = '';

mcpRemote.stdout.on('data', (data) => {
  const text = data.toString();
  output += text;
  process.stdout.write(text);
  
  // Check for token indicators
  if (text.includes('token') || text.includes('Token') || text.includes('TOKEN')) {
    console.log('\n⚠️  Token-related output detected above');
  }
  
  // Check for authentication success
  if (text.includes('authenticated') || text.includes('success') || text.includes('ready')) {
    console.log('\n✓✓✓ Authentication appears successful! ✓✓✓');
  }
});

mcpRemote.stderr.on('data', (data) => {
  const text = data.toString();
  errorOutput += text;
  process.stderr.write(text);
});

// Send MCP initialize request after a delay
setTimeout(() => {
  console.log('\n\nSending MCP initialize request...');
  const initRequest = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'test-client',
        version: '1.0.0'
      }
    }
  };
  
  mcpRemote.stdin.write(JSON.stringify(initRequest) + '\n');
  
  // Wait a bit, then try to list tools
  setTimeout(() => {
    console.log('\nSending tools/list request...');
    const toolsRequest = {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/list',
      params: {}
    };
    
    mcpRemote.stdin.write(JSON.stringify(toolsRequest) + '\n');
    
    // Give it time to respond, then exit
    setTimeout(() => {
      console.log('\n\nStopping mcp-remote...');
      mcpRemote.kill();
      
      console.log('\n' + '='.repeat(60));
      console.log('Summary');
      console.log('='.repeat(60));
      console.log('\nIf you saw successful responses above, mcp-remote is working.');
      console.log('The token is stored internally by mcp-remote.');
      console.log('\nTo use with Letta, you have two options:');
      console.log('  1. Keep mcp-remote running and configure Letta to use it as a proxy');
      console.log('  2. Extract the token (if possible) and use it directly');
      process.exit(0);
    }, 3000);
  }, 2000);
}, 5000);

// Handle errors
mcpRemote.on('error', (err) => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});

mcpRemote.on('exit', (code) => {
  if (code !== 0 && code !== null) {
    console.log(`\nmcp-remote exited with code ${code}`);
  }
});

