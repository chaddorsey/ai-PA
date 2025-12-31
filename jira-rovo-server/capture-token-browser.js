#!/usr/bin/env node
/**
 * Capture Token Using Browser Automation
 * 
 * Uses Puppeteer to automate the OAuth flow and capture the token
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';

async function captureToken() {
  console.log('='.repeat(60));
  console.log('Capture OAuth Token with Browser Automation');
  console.log('='.repeat(60));
  console.log();
  
  // Check if puppeteer is available
  try {
    require('puppeteer');
  } catch (e) {
    console.log('❌ Puppeteer not installed.');
    console.log('Install it with: npm install puppeteer');
    console.log();
    console.log('Alternatively, use the manual method:');
    console.log('1. Open browser DevTools (F12)');
    console.log('2. Go to Network tab');
    console.log('3. Complete OAuth at: https://mcp.atlassian.com/v1/sse');
    console.log('4. Look for requests with Authorization headers or tokens');
    process.exit(1);
  }
  
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: false, // Show browser so user can complete login
    defaultViewport: null
  });
  
  const page = await browser.newPage();
  let capturedToken = null;
  
  // Listen for network requests to capture token
  page.on('request', (request) => {
    const headers = request.headers();
    const url = request.url();
    
    // Check for Authorization header
    if (headers['authorization']) {
      const authHeader = headers['authorization'];
      if (authHeader.startsWith('Bearer ')) {
        const token = authHeader.substring(7);
        if (token.length > 50) { // Likely a real token
          console.log(`\n✓✓✓ TOKEN FOUND IN REQUEST! ✓✓✓`);
          console.log(`URL: ${url.substring(0, 100)}...`);
          console.log(`Token: ${token.substring(0, 50)}...`);
          capturedToken = token;
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      }
    }
  });
  
  // Listen for responses to capture token
  page.on('response', async (response) => {
    const url = response.url();
    
    // Check callback URL
    if (url.includes('mcp.atlassian.com/v1/callback')) {
      console.log(`\n✓ Callback received: ${url.substring(0, 150)}...`);
      
      // Try to get token from URL
      try {
        const urlObj = new URL(url);
        if (urlObj.searchParams.has('access_token')) {
          const token = urlObj.searchParams.get('access_token');
          console.log(`\n✓✓✓ TOKEN FOUND IN CALLBACK URL! ✓✓✓`);
          console.log(`Token: ${token.substring(0, 50)}...`);
          capturedToken = token;
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      } catch (e) {
        // URL parsing failed
      }
      
      // Try to get response body
      try {
        const body = await response.text();
        const tokenMatch = body.match(/"access_token"\s*:\s*"([^"]+)"/);
        if (tokenMatch) {
          const token = tokenMatch[1];
          console.log(`\n✓✓✓ TOKEN FOUND IN RESPONSE BODY! ✓✓✓`);
          console.log(`Token: ${token.substring(0, 50)}...`);
          capturedToken = token;
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      } catch (e) {
        // Can't read response
      }
    }
  });
  
  console.log('Navigating to MCP server...');
  console.log('Complete the OAuth flow in the browser window.');
  console.log('The script will automatically capture the token.');
  console.log();
  
  await page.goto(ROVO_SSE_URL, { waitUntil: 'networkidle2' });
  
  console.log('Waiting for OAuth completion...');
  console.log('(Complete the login and authorization in the browser)');
  console.log();
  
  // Wait up to 5 minutes for token
  const startTime = Date.now();
  const timeout = 5 * 60 * 1000; // 5 minutes
  
  while (!capturedToken && (Date.now() - startTime) < timeout) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check page URL for token
    const currentUrl = page.url();
    if (currentUrl.includes('access_token=')) {
      const urlObj = new URL(currentUrl);
      const token = urlObj.searchParams.get('access_token');
      if (token) {
        console.log(`\n✓✓✓ TOKEN FOUND IN PAGE URL! ✓✓✓`);
        console.log(`Token: ${token.substring(0, 50)}...`);
        capturedToken = token;
        fs.writeFileSync(TOKEN_FILE, token);
        console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        break;
      }
    }
  }
  
  if (capturedToken) {
    console.log('\n' + '='.repeat(60));
    console.log('SUCCESS!');
    console.log('='.repeat(60));
    console.log(`Token saved to: ${TOKEN_FILE}`);
    console.log(`\nUse it with: export ATLASSIAN_ROVO_TOKEN=$(cat ${TOKEN_FILE})`);
  } else {
    console.log('\n⚠️  Token not captured automatically.');
    console.log('Check the browser for any token information.');
    console.log('Or use browser DevTools Network tab to find it.');
  }
  
  // Keep browser open for a moment
  await new Promise(resolve => setTimeout(resolve, 2000));
  await browser.close();
}

captureToken().catch(console.error);

