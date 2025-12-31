#!/usr/bin/env node
/**
 * Extract access token from mcp-remote's token storage
 * 
 * mcp-remote stores tokens in ~/.mcp-auth/{serverUrlHash}_tokens.json
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MCP_AUTH_DIR = path.join(process.env.HOME, '.mcp-auth');
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
const ROVO_MCP_URL = 'https://mcp.atlassian.com/v1/mcp';

console.log('='.repeat(60));
console.log('Extract Token from mcp-remote Storage');
console.log('='.repeat(60));
console.log();

// Check if .mcp-auth directory exists
if (!fs.existsSync(MCP_AUTH_DIR)) {
  console.log(`❌ mcp-remote config directory not found: ${MCP_AUTH_DIR}`);
  console.log('\nThis means mcp-remote hasn\'t stored tokens yet.');
  console.log('Make sure you\'ve completed OAuth with mcp-remote.');
  process.exit(1);
}

console.log(`✓ Found mcp-remote config directory: ${MCP_AUTH_DIR}`);
console.log();

// Check for versioned subdirectories (e.g., mcp-remote-0.1.36)
const subdirs = fs.readdirSync(MCP_AUTH_DIR).filter(f => {
  const fullPath = path.join(MCP_AUTH_DIR, f);
  return fs.statSync(fullPath).isDirectory() && f.startsWith('mcp-remote-');
});

let tokenFiles = [];

// Search in versioned subdirectories
for (const subdir of subdirs) {
  const subdirPath = path.join(MCP_AUTH_DIR, subdir);
  const files = fs.readdirSync(subdirPath);
  const subdirTokenFiles = files
    .filter(f => f.endsWith('_tokens.json'))
    .map(f => path.join(subdir, f));
  tokenFiles.push(...subdirTokenFiles);
}

// Also check root directory
const rootFiles = fs.readdirSync(MCP_AUTH_DIR);
const rootTokenFiles = rootFiles.filter(f => f.endsWith('_tokens.json'));
tokenFiles.push(...rootTokenFiles);

if (tokenFiles.length === 0) {
  console.log('❌ No token files found');
  console.log('\nMake sure you\'ve completed OAuth with mcp-remote.');
  process.exit(1);
}

console.log(`Found ${tokenFiles.length} token file(s):`);
tokenFiles.forEach(f => console.log(`  - ${f}`));
console.log();

// Try to find the one for Rovo MCP
// The serverUrlHash is calculated from the server URL
// Let's check all token files and find the one that works

let foundToken = null;

for (const tokenFile of tokenFiles) {
  const filePath = path.join(MCP_AUTH_DIR, tokenFile);
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const tokens = JSON.parse(content);
    
    if (tokens.access_token) {
      console.log(`✓ Found token in: ${tokenFile}`);
      console.log(`  Token: ${tokens.access_token.substring(0, 50)}...`);
      console.log(`  Token type: ${tokens.token_type || 'Bearer'}`);
      console.log(`  Expires in: ${tokens.expires_in || 'unknown'} seconds`);
      
      if (!foundToken) {
        foundToken = tokens.access_token;
      }
    }
  } catch (e) {
    console.log(`⚠️  Error reading ${tokenFile}: ${e.message}`);
  }
}

if (foundToken) {
  console.log();
  console.log('✓✓✓ TOKEN EXTRACTED! ✓✓✓');
  fs.writeFileSync(TOKEN_FILE, foundToken);
  console.log(`✓ Token saved to: ${TOKEN_FILE}`);
  console.log();
  console.log('Next steps:');
  console.log('  1. Set environment variable:');
  console.log(`     export ATLASSIAN_ROVO_TOKEN="${foundToken}"`);
  console.log('  2. Or add to .env file:');
  console.log(`     ATLASSIAN_ROVO_TOKEN=${foundToken}`);
  console.log('  3. Update Letta configuration');
  console.log('  4. Restart Letta');
} else {
  console.log('\n❌ No valid access token found');
  console.log('\nMake sure you\'ve completed OAuth with mcp-remote.');
  process.exit(1);
}

