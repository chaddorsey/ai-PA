# Calendar OAuth Client Setup Guide

This guide walks you through creating a Desktop app OAuth client for the Google Calendar tools.

## Step 1: Access Google Cloud Console

1. Navigate to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account (e.g., cdorsey@concord.org)
3. Select your project (or create a new one if needed)

## Step 2: Enable Google Calendar API

1. In the left menu, go to **APIs & Services** > **Library**
2. Search for "Google Calendar API"
3. Click on **Google Calendar API**
4. Click **Enable** (if not already enabled)

## Step 3: Configure OAuth Consent Screen (if not already done)

1. In the left menu, go to **APIs & Services** > **OAuth consent screen**
2. If this is your first time:
   - Choose **External** (unless you're in a Google Workspace organization)
   - Fill in required fields:
     - **App name**: "Letta Calendar Tools" (or your preferred name)
     - **User support email**: Your email address
     - **Developer contact information**: Your email address
   - Click **Save and Continue**
   - Skip the Scopes step for now (we'll add them during OAuth flow)
   - Skip Test users if not needed
   - Click **Back to Dashboard**

## Step 4: Create Desktop App OAuth Client

1. In the left menu, go to **APIs & Services** > **Credentials**
2. Click **+ Create Credentials** > **OAuth client ID**
3. If prompted, select **Desktop app** as the application type
4. **Name**: "Letta Calendar Desktop Client" (or your preferred name)
5. Click **Create**

## Step 5: Download the Credentials

1. A dialog will appear showing your Client ID and Client Secret
2. Click the **Download JSON** button (or the download icon next to the client in the list)
3. **IMPORTANT**: Save this file as `gcp-oauth.calendar.desktop.json` in your `~/.gmail-mcp/` directory:

```bash
# Make sure the directory exists
mkdir -p ~/.gmail-mcp

# Move the downloaded file to the correct location
mv ~/Downloads/client_secret_*.json ~/.gmail-mcp/gcp-oauth.calendar.desktop.json
```

## Step 6: Verify the File Structure

The downloaded JSON file should look like this:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
```

Notice it has an `"installed"` key (not `"web"`) - this is correct for Desktop app clients.

## Step 7: Update Environment Variable (Optional)

If you want to use a different path or filename, you can set the `CALENDAR_OAUTH_PATH` environment variable:

```bash
export CALENDAR_OAUTH_PATH=~/.gmail-mcp/gcp-oauth.calendar.desktop.json
```

The calendar tools will use this path, falling back to `GMAIL_OAUTH_PATH` if not set.

## Step 8: Run Authentication

Now run the authentication script:

```bash
python3 letta/calendar_tools/authenticate_calendar.py
```

With a Desktop app client, you should NOT see the duplicate `access_type` error!

## Troubleshooting

- **File not found**: Make sure the file is at `~/.gmail-mcp/gcp-oauth.calendar.desktop.json` or set `CALENDAR_OAUTH_PATH`
- **Still seeing duplicate access_type error**: Verify the JSON file has an `"installed"` key (not `"web"`)
- **Permission denied**: Check file permissions: `chmod 600 ~/.gmail-mcp/gcp-oauth.calendar.desktop.json`
