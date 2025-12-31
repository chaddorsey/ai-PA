#!/usr/bin/env node
/**
 * Extract OAuth Token from Atlassian Rovo MCP
 * 
 * This script helps extract the token by:
 * 1. Setting up a proxy to intercept the OAuth callback
 * 2. Or providing instructions to extract from browser
 */

const http = require('http');
const https = require('https');
const { URL } = require('url');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const PROXY_PORT = 8888;
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');

console.log('='.repeat(60));
console.log('Extract OAuth Token from Atlassian Rovo MCP');
console.log('='.repeat(60));
console.log();

// Since the callback goes to mcp.atlassian.com, we can't intercept it directly.
// But we can:
// 1. Use browser DevTools to capture the token
// 2. Or modify the OAuth flow to use our callback

console.log('Method 1: Browser DevTools (Recommended)');
console.log('='.repeat(60));
console.log();
console.log('1. Open browser DevTools (F12 or Cmd+Option+I)');
console.log('2. Go to Network tab');
console.log('3. Complete the OAuth flow at: https://mcp.atlassian.com/v1/sse');
console.log('4. After authorization, look for:');
console.log('   - Request to mcp.atlassian.com/v1/callback');
console.log('   - Check Response tab for token');
console.log('   - Or check subsequent requests for Authorization header');
console.log('   - Or check Cookies for mcp.atlassian.com');
console.log();
console.log('5. Look for these patterns:');
console.log('   - "access_token": "..."');
console.log('   - "Authorization: Bearer ..."');
console.log('   - Cookie values containing tokens');
console.log();

// Create a proxy that can help intercept
console.log('Method 2: Proxy Interception');
console.log('='.repeat(60));
console.log();
console.log('Starting proxy server to help capture token...');
console.log(`Proxy listening on: http://localhost:${PROXY_PORT}`);
console.log();

// Create a simple proxy that logs all requests
const proxy = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PROXY_PORT}`);
  
  console.log(`[${new Date().toISOString()}] ${req.method} ${url.pathname}`);
  
  // Check if this is a callback with token
  if (url.searchParams.has('access_token')) {
    const token = url.searchParams.get('access_token');
    console.log(`\n✓✓✓ TOKEN FOUND IN CALLBACK! ✓✓✓`);
    console.log(`Token: ${token.substring(0, 50)}...`);
    
    fs.writeFileSync(TOKEN_FILE, token);
    console.log(`✓ Token saved to: ${TOKEN_FILE}`);
    
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('<html><body><h1>Token Captured!</h1></body></html>');
    return;
  }
  
  // Proxy request to MCP server
  const targetUrl = 'https://mcp.atlassian.com' + url.pathname + url.search;
  const target = new URL(targetUrl);
  
  const options = {
    hostname: target.hostname,
    port: 443,
    path: target.pathname + target.search,
    method: req.method,
    headers: {
      ...req.headers,
      host: target.hostname
    }
  };
  
  delete options.headers['host'];
  delete options.headers['connection'];
  
  const proxyReq = https.request(options, (proxyRes) => {
    // Log response
    console.log(`  → ${proxyRes.statusCode} ${proxyRes.statusMessage}`);
    
    // Check for redirects
    if (proxyRes.statusCode >= 300 && proxyRes.statusCode < 400) {
      const location = proxyRes.headers.location;
      if (location) {
        console.log(`  → Redirect: ${location.substring(0, 100)}...`);
      }
    }
    
    // Check response for token
    let body = '';
    proxyRes.on('data', (chunk) => {
      body += chunk;
    });
    
    proxyRes.on('end', () => {
      // Look for token in response
      const tokenMatch = body.match(/"access_token"\s*:\s*"([^"]+)"/);
      if (tokenMatch) {
        const token = tokenMatch[1];
        console.log(`\n✓✓✓ TOKEN FOUND IN RESPONSE! ✓✓✓`);
        console.log(`Token: ${token.substring(0, 50)}...`);
        fs.writeFileSync(TOKEN_FILE, token);
        console.log(`✓ Token saved to: ${TOKEN_FILE}`);
      }
      
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      res.end(body);
    });
  });
  
  proxyReq.on('error', (err) => {
    console.error(`Proxy error: ${err.message}`);
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end(`Proxy error: ${err.message}`);
  });
  
  req.pipe(proxyReq);
});

proxy.listen(PROXY_PORT, () => {
  console.log(`✓ Proxy server started`);
  console.log();
  console.log('To use the proxy:');
  console.log(`1. Configure your browser to use proxy: http://localhost:${PROXY_PORT}`);
  console.log('   (Or use a browser extension like Proxy SwitchOmega)');
  console.log('2. Or use curl through the proxy:');
  console.log(`   curl -x http://localhost:${PROXY_PORT} "https://mcp.atlassian.com/v1/sse"`);
  console.log();
  console.log('Method 3: Manual Extraction Script');
  console.log('='.repeat(60));
  console.log();
  console.log('Run this in browser console after completing OAuth:');
  console.log();
  console.log(`
// Get token from cookies
document.cookie.split(';').forEach(cookie => {
  if (cookie.includes('token') || cookie.includes('access') || cookie.includes('auth')) {
    console.log('Cookie:', cookie);
  }
});

// Get token from localStorage
Object.keys(localStorage).forEach(key => {
  if (key.includes('token') || key.includes('access') || key.includes('auth')) {
    console.log('LocalStorage:', key, localStorage.getItem(key));
  }
});

// Get token from sessionStorage
Object.keys(sessionStorage).forEach(key => {
  if (key.includes('token') || key.includes('access') || key.includes('auth')) {
    console.log('SessionStorage:', key, sessionStorage.getItem(key));
  }
});
  `);
  console.log();
  console.log('Press Ctrl+C to stop the proxy');
  console.log();
});

process.on('SIGINT', () => {
  console.log('\n\nShutting down proxy...');
  if (fs.existsSync(TOKEN_FILE)) {
    const token = fs.readFileSync(TOKEN_FILE, 'utf8');
    console.log(`\n✓ Token was saved: ${token.substring(0, 50)}...`);
  }
  process.exit(0);
});

