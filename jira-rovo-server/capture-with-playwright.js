#!/usr/bin/env node
/**
 * Capture OAuth Token Using Playwright
 * 
 * Uses browser automation to complete OAuth and capture the token
 * from network requests.
 */

let puppeteer;
try {
  puppeteer = require('puppeteer');
} catch (e) {
  console.log('='.repeat(60));
  console.log('Playwright/Puppeteer Not Installed');
  console.log('='.repeat(60));
  console.log();
  console.log('To use browser automation, install Puppeteer:');
  console.log('  npm install puppeteer');
  console.log();
  console.log('Or use the manual method:');
  console.log('1. Open browser DevTools (F12)');
  console.log('2. Go to Network tab');
  console.log('3. Complete OAuth');
  console.log('4. Look for Authorization headers or token in responses');
  console.log();
  process.exit(1);
}

const fs = require('fs');
const path = require('path');
const TOKEN_FILE = path.join(process.env.HOME, '.atlassian-rovo-token.txt');
const ROVO_SSE_URL = 'https://mcp.atlassian.com/v1/sse';

async function captureToken() {
  console.log('='.repeat(60));
  console.log('Capture Token with Browser Automation');
  console.log('='.repeat(60));
  console.log();
  
  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null
  });
  
  const page = await browser.newPage();
  let capturedToken = null;
  
  // Intercept network requests to capture token
  page.on('request', (request) => {
    const headers = request.headers();
    if (headers['authorization'] && headers['authorization'].startsWith('Bearer ')) {
      const token = headers['authorization'].substring(7);
      if (token.length > 50) {
        console.log(`\n✓ Token found in request: ${token.substring(0, 50)}...`);
        capturedToken = token;
        fs.writeFileSync(TOKEN_FILE, token);
        console.log(`✓ Token saved to: ${TOKEN_FILE}`);
      }
    }
  });
  
  page.on('response', async (response) => {
    const url = response.url();
    
    // Check callback URL
    if (url.includes('mcp.atlassian.com/v1/callback')) {
      console.log(`\n✓ Callback received: ${url.substring(0, 100)}...`);
      
      // Check URL for token
      try {
        const urlObj = new URL(url);
        if (urlObj.searchParams.has('access_token')) {
          const token = urlObj.searchParams.get('access_token');
          console.log(`\n✓✓✓ TOKEN IN CALLBACK URL! ✓✓✓`);
          capturedToken = token;
          fs.writeFileSync(TOKEN_FILE, token);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      } catch (e) {}
      
      // Check response body
      try {
        const body = await response.text();
        const tokenMatch = body.match(/"access_token"\s*:\s*"([^"]+)"/);
        if (tokenMatch) {
          console.log(`\n✓✓✓ TOKEN IN RESPONSE! ✓✓✓`);
          capturedToken = tokenMatch[1];
          fs.writeFileSync(TOKEN_FILE, capturedToken);
          console.log(`✓ Token saved to: ${TOKEN_FILE}`);
        }
      } catch (e) {}
    }
    
    // Check for token in any response
    if (url.includes('mcp.atlassian.com')) {
      try {
        const body = await response.text();
        if (body.includes('access_token')) {
          const tokenMatch = body.match(/"access_token"\s*:\s*"([^"]+)"/);
          if (tokenMatch && !capturedToken) {
            console.log(`\n✓ Token found in response from ${url.substring(0, 80)}...`);
            capturedToken = tokenMatch[1];
            fs.writeFileSync(TOKEN_FILE, capturedToken);
            console.log(`✓ Token saved to: ${TOKEN_FILE}`);
          }
        }
      } catch (e) {}
    }
  });
  
  console.log('Navigating to MCP server...');
  console.log('Complete OAuth in the browser window.');
  console.log();
  
  await page.goto(ROVO_SSE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
  
  console.log('Waiting for OAuth completion...');
  console.log('(This may take a few minutes)');
  console.log();
  
  // Wait for token or timeout
  const startTime = Date.now();
  const timeout = 5 * 60 * 1000; // 5 minutes
  
  while (!capturedToken && (Date.now() - startTime) < timeout) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check current URL
    const currentUrl = page.url();
    if (currentUrl.includes('access_token=')) {
      const urlObj = new URL(currentUrl);
      const token = urlObj.searchParams.get('access_token');
      if (token) {
        console.log(`\n✓✓✓ TOKEN IN PAGE URL! ✓✓✓`);
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
  } else {
    console.log('\n⚠️  Token not captured automatically.');
    console.log('Check browser DevTools Network tab manually.');
  }
  
  await new Promise(resolve => setTimeout(resolve, 2000));
  await browser.close();
}

captureToken().catch(console.error);

