#!/usr/bin/env node
/**
 * Extract token from mcp-remote after OAuth
 * 
 * This script tries to extract the access token from mcp-remote
 * after OAuth has been completed.
 */

const https = require('https');
const { URL } = require('url');
const fs = require('fs');
const path = require('path');

// Try to make a request through mcp-remote to see if it has a token
// Or check if mcp-remote stores tokens in a known location

const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

console.log('='.repeat(60));
console.log('Extract Token from mcp-remote');
console.log('='.repeat(60));
console.log();

// Check common token storage locations
const possibleLocations = [
  path.join(process.env.HOME, '.mcp-remote'),
  path.join(process.env.HOME, '.config', 'mcp-remote'),
  path.join(process.env.HOME, '.cache', 'mcp-remote'),
  '/tmp/mcp-remote',
];

console.log('Checking for mcp-remote token storage...');
for (const location of possibleLocations) {
  if (fs.existsSync(location)) {
    console.log(`✓ Found: ${location}`);
    try {
      const stats = fs.statSync(location);
      if (stats.isDirectory()) {
        const files = fs.readdirSync(location);
        console.log(`  Files: ${files.join(', ')}`);
        
        // Look for token files
        for (const file of files) {
          if (file.includes('token') || file.includes('auth') || file.includes('credential')) {
            const filePath = path.join(location, file);
            const content = fs.readFileSync(filePath, 'utf8');
            console.log(`\n  Content of ${file}:`);
            console.log(`  ${content.substring(0, 200)}...`);
            
            // Try to extract token
            const tokenMatch = content.match(/"access_token"\s*:\s*"([^"]+)"/);
            if (tokenMatch) {
              const token = tokenMatch[1];
              console.log(`\n✓✓✓ TOKEN FOUND! ✓✓✓`);
              fs.writeFileSync(TOKEN_FILE, token);
              console.log(`✓ Token saved to: ${TOKEN_FILE}`);
              process.exit(0);
            }
          }
        }
      } else {
        // It's a file
        const content = fs.readFileSync(location, 'utf8');
        console.log(`  Content: ${content.substring(0, 200)}...`);
        
        const tokenMatch = content.match(/"access_token"\s*:\s*"([^"]+)"/);
        if (tokenMatch) {
          const token = tokenMatch[1];
          console.log(`\n✓✓✓ TOKEN FOUND! ✓✓✓`);
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
          process.exit(0);
        }
      }
    } catch (e) {
      console.log(`  Error reading: ${e.message}`);
    }
  }
}

console.log('\n⚠️  Token not found in common locations.');
console.log('\nAlternative: Test mcp-remote connection');
console.log('Run: mcp-remote https://mcp.atlassian.com/v1/mcp');
console.log('Then make a test request to see if it works.');
console.log('\nOr check browser DevTools Network tab for the token');
console.log('after mcp-remote completes OAuth.');

