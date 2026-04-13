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

// mcp-remote derives the cache filename from md5(server URL).
// We MUST target the Atlassian hash specifically — the cache may also hold
// tokens for other MCP servers (Granola, etc.), and a naive "pick any
// _tokens.json" scan can happily hand Letta a wrong-issuer token.
const serverUrlHash = crypto.createHash('md5').update(ROVO_MCP_URL).digest('hex');
const tokenFileName = `${serverUrlHash}_tokens.json`;

// Find the mcp-remote versioned subdir that contains the target file.
const subdirs = fs.readdirSync(MCP_AUTH_DIR).filter(f => {
  const fullPath = path.join(MCP_AUTH_DIR, f);
  return fs.statSync(fullPath).isDirectory() && f.startsWith('mcp-remote-');
});

let targetFilePath = null;
for (const subdir of subdirs) {
  const candidate = path.join(MCP_AUTH_DIR, subdir, tokenFileName);
  if (fs.existsSync(candidate)) {
    targetFilePath = candidate;
    break;
  }
}
// Legacy fallback: root of .mcp-auth (very old mcp-remote versions)
if (!targetFilePath) {
  const candidate = path.join(MCP_AUTH_DIR, tokenFileName);
  if (fs.existsSync(candidate)) {
    targetFilePath = candidate;
  }
}

if (!targetFilePath) {
  console.log(`❌ No token file found for ${ROVO_MCP_URL}`);
  console.log(`   Expected: */${tokenFileName}`);
  console.log('\nMake sure you\'ve completed OAuth for the Atlassian MCP server.');
  console.log('Run: npx mcp-remote "' + ROVO_MCP_URL + '" interactively.');
  process.exit(1);
}

console.log(`✓ Found Atlassian token file: ${targetFilePath}`);

let foundToken = null;
try {
  const tokens = JSON.parse(fs.readFileSync(targetFilePath, 'utf8'));
  if (tokens.access_token) {
    console.log(`  Token: ${tokens.access_token.substring(0, 20)}... (${tokens.access_token.length} chars)`);
    console.log(`  Token type: ${tokens.token_type || 'Bearer'}`);
    console.log(`  Expires in: ${tokens.expires_in || 'unknown'} seconds`);
    console.log(`  Refresh token present: ${tokens.refresh_token ? 'yes' : 'no'}`);
    foundToken = tokens.access_token;
  }
} catch (e) {
  console.log(`⚠️  Error reading ${targetFilePath}: ${e.message}`);
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

