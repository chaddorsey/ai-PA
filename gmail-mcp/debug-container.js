const fs = require('fs');
const CREDENTIALS_PATH = '/gmail-server/credentials.json';
console.log('=== Container Credential Debug ===');
console.log('File exists:', fs.existsSync(CREDENTIALS_PATH));
if (fs.existsSync(CREDENTIALS_PATH)) {
  try {
    const content = fs.readFileSync(CREDENTIALS_PATH, 'utf8');
    const tokens = JSON.parse(content);
    console.log('✅ Credentials parsed successfully');
    console.log('Access token present:', !!tokens.access_token);
    console.log('Refresh token present:', !!tokens.refresh_token);
  } catch (e) {
    console.error('❌ Parse error:', e.message);
  }
} else {
  console.error('❌ Credentials file not found');
}
