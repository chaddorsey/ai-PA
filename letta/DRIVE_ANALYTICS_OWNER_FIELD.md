# Drive Analytics - Owner Field Behavior

## Question: Why are some documents listed with owners that appear to be folder or drive names?

## Answer

This is **expected behavior** from Google's Admin Reports API, not a bug or deceptive reporting.

### How Owner Information Works

When the `collect_daily_workspace_activity()` tool queries the Admin Reports API, it extracts the `owner` parameter from each activity event. The value of this parameter depends on where the document is stored:

1. **Personal Drive files**: The `owner` field contains the user's email address (e.g., `cdorsey@concord.org`)

2. **Shared Drive files**: The `owner` field contains the **shared drive name** (e.g., `Proposals`, `Concord Strategic Development`)

3. **Files in "My Drive" but shared**: Still shows the user's email address

### Examples from Your Data

- `jchao@concord.org` → Personal Drive file owned by that user
- `Proposals` → File in a Shared Drive named "Proposals"
- `Concord Strategic Development` → File in a Shared Drive with that name

### Why This Happens

Google's Admin Reports API reports ownership at the drive level for Shared Drives. Since Shared Drives are collaborative spaces where multiple users can have different permission levels, Google reports the drive name rather than a single "owner" email.

### Is This Accurate?

Yes, this is accurate reporting from Google's API. The document is indeed "owned" by (or located in) that Shared Drive. If you need to know the specific user who created or last modified a file in a Shared Drive, you would need to query the Drive API directly for that file's metadata, which includes more detailed ownership information.

### Potential Enhancements

If you want more detailed ownership information, we could:

1. **Query Drive API for Shared Drive files**: After collecting activity, query the Drive API for files in Shared Drives to get the actual creator/owner email
2. **Add a field to distinguish**: Add a field like `"location": "shared_drive"` or `"location": "personal_drive"` to make it clearer
3. **Show both**: Show both the drive name and the file creator if available

Would you like me to implement any of these enhancements?

