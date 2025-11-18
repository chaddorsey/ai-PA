# Drive Analytics - Shared Drive Access Fix

## Problem

Files were being incorrectly marked as "Deleted" even though they existed and were accessible in Google Drive.

## Root Cause

Files in **Shared Drives** (formerly Team Drives) require special parameters when accessing them via the Drive API:

- `supportsAllDrives=True` - Required for `files().get()` and `files().list()` operations
- `includeItemsFromAllDrives=True` - Required for `files().list()` operations to include Shared Drive files

Without these parameters, the Drive API returns **404 (Not Found)** even though the files exist and are accessible.

## Example

**Before fix:**
```python
file = service.files().get(
    fileId=doc_id,
    fields="id, name, webViewLink"
).execute()
# Returns 404 for Shared Drive files
```

**After fix:**
```python
file = service.files().get(
    fileId=doc_id,
    fields="id, name, webViewLink",
    supportsAllDrives=True  # Required for Shared Drives
).execute()
# Now works correctly
```

## Files Updated

1. **`collect_daily_workspace_activity()`**:
   - Added `supportsAllDrives=True` to `files().get()` calls
   - Added `supportsAllDrives=True` and `includeItemsFromAllDrives=True` to `files().list()` calls

2. **`collect_daily_personal_activity()`**:
   - Added `supportsAllDrives=True` to `files().get()` calls

3. **`collect_daily_mentions()`**:
   - Added `supportsAllDrives=True` and `includeItemsFromAllDrives=True` to `files().list()` calls

4. **`_query_drive_api()`**:
   - Added `supportsAllDrives=True` and `includeItemsFromAllDrives=True` to `files().list()` calls

## Verification

Tested with files that were previously marked as "Deleted":
- ✅ "SeismicML Virtual Kickoff | November 17, 2025" - Now accessible with link
- ✅ "S35 - Year 3 Session 4 (student not picked up by audio-transcrib) [SH][NW]" - Now accessible with link

## Google Drive API Documentation

For reference:
- [Files: get](https://developers.google.com/drive/api/v3/reference/files/get) - Requires `supportsAllDrives=True` for Shared Drive files
- [Files: list](https://developers.google.com/drive/api/v3/reference/files/list) - Requires both `supportsAllDrives=True` and `includeItemsFromAllDrives=True` for Shared Drive files

