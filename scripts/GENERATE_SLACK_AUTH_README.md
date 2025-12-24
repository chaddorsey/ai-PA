# Generate Slack Authentication File

This script helps you create a valid authentication file for the Slack analytics export tool.

## Why This Is Needed

The Slack analytics export scripts run in headless mode and need a saved authentication state file to access Slack's admin pages. The authentication file contains cookies and browser storage that maintain your login session.

## How to Use

### Option 1: Run on Host Machine (Recommended)

Since the script opens a browser window, it's easiest to run it on your host machine:

```bash
cd /Volumes/main-drive/ai-PA
python3 scripts/generate_slack_auth.py
```

The script will:
1. Open a browser window
2. Navigate to Slack analytics
3. Allow you to log in (you'll see the Slack sign-in page)
4. Wait for you to complete login
5. Automatically save the authentication state to `./slack_auth_state.json`

The file will be saved in the project root, which is mounted as a volume in the Docker container, so it will be immediately available to the export service.

### Option 2: Custom Auth File Path

To save the auth file to a different location:

```bash
python3 scripts/generate_slack_auth.py --auth-file /path/to/custom_auth.json
```

Then update the `docker-compose.yml` volume mount to point to your custom location.

## Requirements

- Python 3 with Playwright installed
- If running in Docker container, you'll need X11 forwarding or similar for the browser window

To install Playwright dependencies:
```bash
pip install playwright
playwright install chromium
```

## Troubleshooting

- **Browser doesn't open**: Make sure you're running this on a machine with a display (not in a headless SSH session without X11 forwarding)
- **Login timeout**: The script waits up to 5 minutes for you to log in
- **Auth file is empty**: This shouldn't happen, but if it does, try running the script again
- **Still getting sign-in errors**: The auth file might have expired. Generate a new one.

## After Generating

Once you have a valid auth file:
1. The file is automatically available in the Docker container (via volume mount)
2. The Slack analytics export tool will use it automatically
3. You should see "✓ Already authenticated" instead of sign-in errors

The auth file typically remains valid for the duration of your Slack session (often several days to weeks).
