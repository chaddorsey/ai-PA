#!/usr/bin/env node
/**
 * Extract authorization code from callback URL and attempt to exchange for token
 * 
 * Note: This requires the client secret, which we may not have.
 * mcp-remote should have already done this exchange automatically.
 */

const https = require('https');
const { URL } = require('url');
const fs = require('fs');
const path = require('path');

// The callback URL from the user
const CALLBACK_URL = process.argv[2] || 'http://localhost:3736/oauth/callback?code=70121-cecc6a6e-e07f-440f-bcef-0e1b8d0fe274%3AU8FC4Qob90wGeZIi%3AeHBg3I43tfMCYR3jRS6sVNP7FQ4tLHFX&state=f8d0dae3-76c6-4c9d-8269-1b50444f7b49';

console.log('='.repeat(60));
console.log('Extract Authorization Code and Exchange for Token');
console.log('='.repeat(60));
console.log();

const url = new URL(CALLBACK_URL);
const code = url.searchParams.get('code');
const state = url.searchParams.get('state');

if (!code) {
  console.log('❌ No authorization code found in URL');
  process.exit(1);
}

console.log('✓ Authorization code found');
console.log(`Code: ${code.substring(0, 50)}...`);
console.log(`State: ${state}`);
console.log();

// Decode the code (it's URL encoded)
const decodedCode = decodeURIComponent(code);
console.log('Decoded code:', decodedCode.substring(0, 80) + '...');
console.log();

console.log('⚠️  This is an AUTHORIZATION CODE, not an ACCESS TOKEN.');
console.log('   It needs to be exchanged for an access token.');
console.log();
console.log('mcp-remote should have already done this exchange automatically.');
console.log('The access token would be in:');
console.log('  1. Subsequent browser requests to mcp.atlassian.com');
console.log('  2. mcp-remote\'s internal storage (if it stores tokens)');
console.log();
console.log('To exchange manually, you would need:');
console.log('  - Client ID: qR8qvnqMVPbJdfQn (from mcp-remote output)');
console.log('  - Client Secret: (we don\'t have this)');
console.log('  - Redirect URI: http://localhost:3736/oauth/callback');
console.log();
console.log('Better approach: Check browser DevTools for the actual token');
console.log('in subsequent requests to mcp.atlassian.com');
console.log();

// Save the code for reference
const codeFile = path.join(process.env.HOME, '.atlassian-rovo-auth-code.txt');
fs.writeFileSync(codeFile, code);
console.log(`✓ Authorization code saved to: ${codeFile}`);
console.log();
console.log('Next steps:');
console.log('  1. Check Safari DevTools Network tab');
console.log('  2. Look for requests to mcp.atlassian.com');
console.log('  3. Find Authorization: Bearer <token> header');
console.log('  4. Or check if mcp-remote is still running and made the exchange');

