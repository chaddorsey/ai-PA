const fs = require('fs');
const { OAuth2Client } = require('google-auth-library');

console.log('=== Post-Restart Credential Debug ===');

// Check credentials file
const CREDENTIALS_PATH = '/gmail-server/credentials.json';
const OAUTH_PATH = '/root/.gmail-mcp/gcp-oauth.keys.json';

try {
  console.log('Credentials file exists:', fs.existsSync(CREDENTIALS_PATH));
  console.log('OAuth file exists:', fs.existsSync(OAUTH_PATH));
  
  if (fs.existsSync(CREDENTIALS_PATH)) {
    const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
    console.log('Access token present:', !!creds.access_token);
    console.log('Refresh token present:', !!creds.refresh_token);
    console.log('Token expiry:', new Date(creds.expiry_date || 0).toISOString());
    console.log('Is expired:', new Date() > new Date(creds.expiry_date || 0));
  }
  
  if (fs.existsSync(OAUTH_PATH)) {
    const keys = JSON.parse(fs.readFileSync(OAUTH_PATH, 'utf8'));
    const clientKeys = keys.web || keys.installed;
    
    // Test OAuth client creation
    const oauth2Client = new OAuth2Client(
      clientKeys.client_id,
      clientKeys.client_secret,
      'http://localhost:3000/oauth2callback'
    );
    
    if (fs.existsSync(CREDENTIALS_PATH)) {
      const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
      oauth2Client.setCredentials(creds);
      console.log('OAuth client configured successfully');
    }
  }
} catch (e) {
  console.error('Error:', e.message);
}
