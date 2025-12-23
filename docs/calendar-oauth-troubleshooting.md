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

### If You Can't See the Keep Scope in the Consent Screen

If you don't see the Keep scope in your OAuth consent screen but still get this error, try:

1. **Explicitly Add Calendar Scope**:
   - Go to **OAuth consent screen** > **Scopes**
   - Click **Add or Remove Scopes**
   - Manually add: `https://www.googleapis.com/auth/calendar`
   - Click **Update**
   - **Save and Continue**

2. **Check if Scopes Need to be Removed**:
   - Even if you don't see scopes listed, try clicking **Add or Remove Scopes**
   - Look for any scopes that mention "keep" or anything other than calendar
   - Remove all non-calendar scopes
   - Click **Update**

3. **Clear OAuth Consent Screen Cache**:
   - Try removing all scopes
   - Save
   - Then add back only the calendar scope
   - Save again

4. **Check Test Users**:
   - If you have test users configured, they might have cached permissions
   - Try removing test users temporarily and re-adding them after fixing scopes

### Alternative: Create a Separate OAuth Client

If you're sharing an OAuth consent screen with other applications (like n8n), consider creating a separate Google Cloud project just for the calendar tools to avoid scope conflicts.
