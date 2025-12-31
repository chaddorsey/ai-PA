// Browser Console Script to Extract OAuth Token
// Copy and paste this into your browser console after completing OAuth

console.log('='.repeat(60));
console.log('Extracting OAuth Token...');
console.log('='.repeat(60));

let foundToken = null;

// Method 1: Check URL parameters
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has('access_token')) {
  foundToken = urlParams.get('access_token');
  console.log('✓ Token found in URL:', foundToken.substring(0, 50) + '...');
}

// Method 2: Check URL hash (fragment)
if (window.location.hash) {
  const hashParams = new URLSearchParams(window.location.hash.substring(1));
  if (hashParams.has('access_token')) {
    foundToken = hashParams.get('access_token');
    console.log('✓ Token found in URL hash:', foundToken.substring(0, 50) + '...');
  }
}

// Method 3: Check cookies
document.cookie.split(';').forEach(cookie => {
  const [name, value] = cookie.trim().split('=');
  if (name && (name.toLowerCase().includes('token') || 
               name.toLowerCase().includes('access') || 
               name.toLowerCase().includes('auth') ||
               name.toLowerCase().includes('oauth'))) {
    console.log('Cookie found:', name, '=', value.substring(0, 50) + '...');
    if (value.length > 50 && !foundToken) {
      foundToken = value;
    }
  }
});

// Method 4: Check localStorage
Object.keys(localStorage).forEach(key => {
  if (key.toLowerCase().includes('token') || 
      key.toLowerCase().includes('access') || 
      key.toLowerCase().includes('auth') ||
      key.toLowerCase().includes('oauth')) {
    const value = localStorage.getItem(key);
    console.log('LocalStorage:', key, '=', value.substring(0, 50) + '...');
    if (value && value.length > 50 && !foundToken) {
      foundToken = value;
    }
  }
});

// Method 5: Check sessionStorage
Object.keys(sessionStorage).forEach(key => {
  if (key.toLowerCase().includes('token') || 
      key.toLowerCase().includes('access') || 
      key.toLowerCase().includes('auth') ||
      key.toLowerCase().includes('oauth')) {
    const value = sessionStorage.getItem(key);
    console.log('SessionStorage:', key, '=', value.substring(0, 50) + '...');
    if (value && value.length > 50 && !foundToken) {
      foundToken = value;
    }
  }
});

// Method 6: Check Network requests (if DevTools Network tab is open)
console.log('\nTo check Network requests:');
console.log('1. Open DevTools (F12)');
console.log('2. Go to Network tab');
console.log('3. Look for requests to mcp.atlassian.com');
console.log('4. Check Request Headers for "Authorization: Bearer ..."');
console.log('5. Check Response for "access_token"');

if (foundToken) {
  console.log('\n' + '='.repeat(60));
  console.log('TOKEN FOUND!');
  console.log('='.repeat(60));
  console.log('Token:', foundToken);
  console.log('\nCopy this token and save it to ~/.atlassian-rovo-token.txt');
  console.log('Or run: echo "' + foundToken + '" > ~/.atlassian-rovo-token.txt');
} else {
  console.log('\n⚠️  Token not found in current page.');
  console.log('Try:');
  console.log('1. Check Network tab in DevTools');
  console.log('2. Look for requests after OAuth completion');
  console.log('3. Check the callback URL response');
}

// Also try to intercept fetch/XHR
const originalFetch = window.fetch;
window.fetch = function(...args) {
  return originalFetch.apply(this, args).then(response => {
    // Check response for token
    response.clone().text().then(text => {
      const tokenMatch = text.match(/"access_token"\s*:\s*"([^"]+)"/);
      if (tokenMatch) {
        console.log('✓ Token found in fetch response:', tokenMatch[1].substring(0, 50) + '...');
        foundToken = tokenMatch[1];
      }
    });
    return response;
  });
};

console.log('\n✓ Fetch interceptor installed - will capture tokens from API responses');

