// Browser Console Script - Extract Cookies After OAuth
// 
// Instructions:
// 1. Complete OAuth at: https://mcp.atlassian.com/v1/sse
// 2. Stay on the mcp.atlassian.com page
// 3. Open DevTools Console (F12 → Console)
// 4. Paste this entire script and press Enter
// 5. Copy the output and save it

console.log('='.repeat(60));
console.log('Extracting Cookies from mcp.atlassian.com');
console.log('='.repeat(60));
console.log();

// Get all cookies
const allCookies = document.cookie;
console.log('All cookies:', allCookies);
console.log();

// Format for use in requests
const cookieArray = document.cookie.split(';').map(c => c.trim()).filter(c => c);
const cookieString = cookieArray.join('; ');

console.log('Cookie string for requests:');
console.log(cookieString);
console.log();

// Also check if we can access cookies from different domains
console.log('To save these cookies, run in terminal:');
console.log(`echo "${cookieString}" > ~/.atlassian-mcp-cookies.txt`);
console.log();

// Check localStorage and sessionStorage too
console.log('Checking localStorage...');
Object.keys(localStorage).forEach(key => {
  if (key.includes('mcp') || key.includes('atlassian') || key.includes('token') || key.includes('auth')) {
    console.log(`LocalStorage[${key}]:`, localStorage.getItem(key).substring(0, 50) + '...');
  }
});

console.log();
console.log('Checking sessionStorage...');
Object.keys(sessionStorage).forEach(key => {
  if (key.includes('mcp') || key.includes('atlassian') || key.includes('token') || key.includes('auth')) {
    console.log(`SessionStorage[${key}]:`, sessionStorage.getItem(key).substring(0, 50) + '...');
  }
});

console.log();
console.log('='.repeat(60));
console.log('Next: Save cookies and test connection');
console.log('='.repeat(60));

