# Calendar OAuth Troubleshooting Guide

## Error: "Some requested scopes cannot be shown: [https://www.googleapis.com/auth/keep]"

This error occurs when your OAuth consent screen is configured with scopes that aren't available or properly enabled.

### Solution

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** > **OAuth consent screen**
3. Click **Edit App**
4. Go to the **Scopes** section
5. Click **Add or Remove Scopes**
6. **Remove** the `https://www.googleapis.com/auth/keep` scope if it's present
7. **Add** only the scopes you need:
   - `https://www.googleapis.com/auth/calendar` (required for calendar tools)
8. Click **Update**
9. Click **Save and Continue**

### Why This Happens

The OAuth consent screen configuration determines which scopes can be requested. If the consent screen includes scopes that:
- Aren't enabled for your project
- Don't exist
- Are restricted

You'll get this error even if your code only requests valid scopes.

### Alternative: Create a Separate OAuth Client

If you're sharing an OAuth consent screen with other applications (like n8n), consider creating a separate Google Cloud project just for the calendar tools to avoid scope conflicts.
