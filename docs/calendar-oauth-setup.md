# Calendar OAuth Client Setup Guide

This guide walks you through creating a Desktop app OAuth client for the Google Calendar tools.

**Recommended: Create a New Project**

To avoid conflicts with existing OAuth configurations (like n8n), we recommend creating a new Google Cloud project specifically for the calendar tools.

## Step 1: Create a New Google Cloud Project

1. Navigate to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account (e.g., cdorsey@concord.org)
3. Click the project dropdown at the top of the page (next to "Google Cloud")
4. Click **NEW PROJECT**
5. Enter project details:
   - **Project name**: "Letta Calendar Tools" (or your preferred name)
   - **Project ID**: Will be auto-generated (or customize it)
   - **Organization**: Select your organization if applicable
6. Click **CREATE**
7. Wait for the project to be created, then select it from the project dropdown

## Step 2: Enable Google Calendar API

1. In the left menu, go to **APIs & Services** > **Library**
2. Search for "Google Calendar API"
3. Click on **Google Calendar API**
4. Click **Enable**

   (If you see a billing prompt, you can enable billing or skip - the Calendar API has a free tier that should be sufficient)

## Step 3: Configure OAuth Consent Screen

Since this is a new project, you'll need to set up the OAuth consent screen:

1. In the left menu, go to **APIs & Services** > **OAuth consent screen**
2. Choose **External** (unless you're in a Google Workspace organization and want to restrict to your organization)
3. Fill in the required fields:
   - **App name**: "Letta Calendar Tools" (or your preferred name)
   - **User support email**: Your email address
   - **App logo** (optional): You can skip this
   - **App domain** (optional): You can skip this
   - **Developer contact information**: Your email address
4. Click **Save and Continue**
5. On the **Scopes** step:
   - Click **Add or Remove Scopes**
   - In the filter/search box, type: `calendar`
   - Find and check: `https://www.googleapis.com/auth/calendar`
   - Click **Update** (at the bottom)
   - Click **Save and Continue**
6. On the **Test users** step (if shown):
   - You can skip this for now, or add your email if you want to test
   - Click **Save and Continue**
7. Review the summary and click **Back to Dashboard**

**Important**: Only the calendar scope should be added. Do not add any other scopes.

## Step 4: Create Desktop App OAuth Client

1. In the left menu, go to **APIs & Services** > **Credentials**
2. Click **+ Create Credentials** > **OAuth client ID**
3. If prompted, select **Desktop app** as the application type
4. **Name**: "Letta Calendar Desktop Client" (or your preferred name)
5. Click **Create**

## Step 5: Download the Credentials

1. A dialog will appear showing your Client ID and Client Secret
2. Click the **Download JSON** button (download icon in the top-right of the dialog, or use the download icon next to the client in the credentials list)
3. **IMPORTANT**: Save this file as `gcp-oauth.calendar.desktop.json` in your `~/.gmail-mcp/` directory:

```bash
# Make sure the directory exists
mkdir -p ~/.gmail-mcp

# Move the downloaded file to the correct location
# (Adjust the path if your downloads are in a different location)
mv ~/Downloads/client_secret_*.json ~/.gmail-mcp/gcp-oauth.calendar.desktop.json

# Verify the file exists and has the correct structure
ls -la ~/.gmail-mcp/gcp-oauth.calendar.desktop.json
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
