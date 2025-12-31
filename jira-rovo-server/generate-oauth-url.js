#!/usr/bin/env node
/**
 * Generate OAuth URL for Atlassian Rovo MCP
 */

const { URL, URLSearchParams } = require('url');
const crypto = require('crypto');

// Configuration
const CLIENT_ID = 'pVrZtjGOkBraHr0ge4iVlstqGVRJfi3'; // From the JWT we saw earlier
const REDIRECT_URI = 'http://localhost:5598/oauth/callback';
const AUDIENCE = 'api.atlassian.com';

// Scopes for Rovo MCP
const SCOPES = [
  'offline_access',
  'read:comment:confluence',
  'read:confluence-user',
  'read:hierarchical-content:confluence',
  'read:jira-work',
  'read:me',
  'read:page:confluence',
  'read:space:confluence',
  'search:confluence',
  'write:comment:confluence',
  'write:jira-work',
  'write:page:confluence'
];

// Generate state for CSRF protection
const state = crypto.randomBytes(32).toString('base64url');

// Build OAuth URL
const authUrl = new URL('https://auth.atlassian.com/authorize');
authUrl.searchParams.set('audience', AUDIENCE);
authUrl.searchParams.set('client_id', CLIENT_ID);
authUrl.searchParams.set('scope', SCOPES.join(' '));
authUrl.searchParams.set('redirect_uri', REDIRECT_URI);
authUrl.searchParams.set('state', state);
authUrl.searchParams.set('response_type', 'code');
authUrl.searchParams.set('prompt', 'consent');

console.log('='.repeat(60));
console.log('Atlassian Rovo OAuth URL');
console.log('='.repeat(60));
console.log();
console.log('Generated OAuth URL:');
console.log();
console.log(authUrl.toString());
console.log();
console.log('='.repeat(60));
console.log();
console.log('Instructions:');
console.log('1. Make sure the callback server is running:');
console.log('   node capture-token.js');
console.log();
console.log('2. Open this URL in your browser:');
console.log();
console.log(authUrl.toString());
console.log();
console.log('3. Complete the OAuth flow');
console.log('4. The token will be captured automatically');
console.log();
console.log('State parameter (for verification):', state);
console.log();

// Also try the alternative endpoint
const altUrl = new URL('https://api.atlassian.com/oauth2/authorize/server/consent');
console.log('Alternative: Try this URL if the above doesn\'t work:');
console.log('(This requires getting the context from the MCP server first)');
console.log();

