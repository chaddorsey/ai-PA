# Calendar Tools Troubleshooting

## Error: "OAuth authentication required. Calendar credentials not found"

This error occurs when the calendar tools can't find or load the credentials file, even if the file exists.

### Check 1: Verify File Exists in Container

```bash
docker exec ai-pa-letta-1 ls -la /root/.gmail-mcp/calendar.credentials.json
docker exec ai-pa-letta-1 test -f /root/.gmail-mcp/calendar.credentials.json && echo "✓ File exists" || echo "✗ File missing"
```

If the file doesn't exist:
1. Verify the mount is working: Check `docker-compose.yml` has `~/.gmail-mcp:/root/.gmail-mcp`
2. Verify file exists on host: `ls -la ~/.gmail-mcp/calendar.credentials.json`
3. Restart container: `docker-compose restart letta`

### Check 2: Verify Dependencies Are Installed

The calendar tools require Google API libraries. Letta should install them from `requirements.txt`, but you may need to restart the container:

```bash
docker-compose restart letta
```

Wait a few seconds, then check if dependencies are installed:

```bash
docker exec ai-pa-letta-1 bash -c "cd /app/tools/letta && source env/bin/activate && python3 -c 'import google.auth; import google_auth_oauthlib; print(\"✓ Dependencies installed\")'"
```

If dependencies are missing, check `letta/requirements.txt` includes:
- `google-auth>=2.0.0`
- `google-auth-oauthlib>=1.0.0`
- `google-api-python-client>=2.0.0`

### Check 3: Verify Credentials File Format

The credentials file should be valid JSON with these fields:
- `token`
- `refresh_token`
- `client_id`
- `client_secret`
- `token_uri`
- `scopes`

Check the file:

```bash
docker exec ai-pa-letta-1 cat /root/.gmail-mcp/calendar.credentials.json | python3 -m json.tool
```

### Check 4: Test Credential Loading Directly

Test if credentials can be loaded:

```bash
docker exec ai-pa-letta-1 bash -c "cd /app/tools/letta && source env/bin/activate && python3 << 'EOF'
from google.oauth2.credentials import Credentials
import os
creds = Credentials.from_authorized_user_file('/root/.gmail-mcp/calendar.credentials.json', ['https://www.googleapis.com/auth/calendar'])
print('✓ Credentials loaded')
print(f'Valid: {creds.valid}')
print(f'Expired: {creds.expired}')
EOF
"
```

### Check 5: Verify OAuth Key File Exists

The OAuth key file is also needed:

```bash
docker exec ai-pa-letta-1 ls -la /root/.gmail-mcp/gcp-oauth.calendar.desktop.json
```

If missing, ensure the file exists on the host and restart the container.

### Common Solutions

1. **Restart Container**: Often fixes mount or dependency issues
   ```bash
   docker-compose restart letta
   ```

2. **Re-authenticate**: If credentials are expired or invalid
   ```bash
   python3 letta/calendar_tools/authenticate_calendar.py
   docker-compose restart letta
   ```

3. **Check Container Logs**: Look for errors
   ```bash
   docker logs ai-pa-letta-1 | tail -50
   ```

4. **Verify Mount Path**: In `docker-compose.yml`, ensure:
   ```yaml
   volumes:
     - ~/.gmail-mcp:/root/.gmail-mcp
   ```
   Note: `~` should expand to your home directory. If it doesn't work, use absolute path:
   ```yaml
   volumes:
     - /Users/your-username/.gmail-mcp:/root/.gmail-mcp
   ```
