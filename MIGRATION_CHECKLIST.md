# Migration Checklist: Moving ai-PA to External Drive

## Overview
This checklist covers:
1. Moving the entire ai-PA project folder to external "main-filestore" drive
2. Moving ai-PA-backups from "T7 Shield" to "main-filestore"
3. Renaming "T7 Shield" to "working-drive"
4. Updating all symlinks and path references

## Prerequisites
- [ ] External "main-filestore" drive is formatted as APFS (unencrypted) and mounted
- [ ] Docker Desktop is stopped (no containers running)
- [ ] Backup of current docker-compose.yml and critical config files
- [ ] Note current paths:
  - Project: `/Users/dorseyhomeserver/ai-PA`
  - Backups symlink: `/Users/dorseyhomeserver/ai-PA/deployment/backups -> /Volumes/T7 Shield/ai-PA-backups`
  - Docker volumes location (check with: `docker volume ls`)

---

## Phase 1: Prepare External Drives

### Step 1.1: Rename T7 Shield to working-drive
1. [ ] Open Disk Utility
2. [ ] Select "T7 Shield" volume
3. [ ] Click "Rename" → Change to "working-drive"
4. [ ] Verify new mount point: `/Volumes/working-drive`

### Step 1.2: Verify main-filestore is mounted
1. [ ] Confirm "main-filestore" drive is mounted at `/Volumes/main-filestore`
2. [ ] Create directory structure: `/Volumes/main-filestore/ai-PA-backups`
3. [ ] Verify adequate space on both drives

---

## Phase 2: Move ai-PA-backups Folder

### Step 2.1: Stop any running backup processes
1. [ ] Check for running backup jobs: `ps aux | grep backup`
2. [ ] Stop scheduler-service if running backups
3. [ ] Wait for any in-progress backups to complete

### Step 2.2: Move backups folder
```bash
# Move the entire backups folder
sudo mv "/Volumes/T7 Shield/ai-PA-backups" "/Volumes/main-filestore/ai-PA-backups"

# Or if renaming drive first:
sudo mv "/Volumes/working-drive/ai-PA-backups" "/Volumes/main-filestore/ai-PA-backups"
```

1. [ ] Verify move completed: `ls -la /Volumes/main-filestore/ai-PA-backups`
2. [ ] Check backup files are intact (spot-check a few files)

### Step 2.3: Update symlink
```bash
# Remove old symlink
rm /Users/dorseyhomeserver/ai-PA/deployment/backups

# Create new symlink pointing to main-filestore
ln -s /Volumes/main-filestore/ai-PA-backups /Users/dorseyhomeserver/ai-PA/deployment/backups

# Verify symlink
ls -la /Users/dorseyhomeserver/ai-PA/deployment/backups
```

1. [ ] Verify symlink points to correct location
2. [ ] Test: `ls /Users/dorseyhomeserver/ai-PA/deployment/backups` should show backup folders

---

## Phase 3: Update docker-compose.yml

### Step 3.1: Update backup path reference
1. [ ] Open `docker-compose.yml`
2. [ ] Find line 352: `"/Volumes/T7 Shield/ai-PA-backups:..."`
3. [ ] Update to: `"/Volumes/main-filestore/ai-PA-backups:..."`
4. [ ] Save file

### Step 3.2: Update cloudflared path (if needed)
1. [ ] Check line 709: `/Users/dorseyhomeserver/.cloudflared`
2. [ ] If home directory remains same, leave as-is
3. [ ] If username changes, update path

### Step 3.3: Verify other path references
1. [ ] Check `~/.gmail-mcp` reference (line 548) - update if needed
2. [ ] Verify all relative paths (`./...`) are correct
3. [ ] Run validation: `docker compose config` (from project root)

---

## Phase 4: Move Project Folder

### Step 4.1: Move entire project directory
```bash
# Move project to external drive
sudo mv /Users/dorseyhomeserver/ai-PA /Volumes/main-filestore/ai-PA

# Or if you want a different name:
sudo mv /Users/dorseyhomeserver/ai-PA /Volumes/main-filestore/ai-PA-project
```

1. [ ] Verify move completed
2. [ ] Check all files are present: `ls -la /Volumes/main-filestore/ai-PA/`
3. [ ] Verify symlink still works: `ls /Volumes/main-filestore/ai-PA/deployment/backups`

### Step 4.2: Update symlink (if project location changed)
If you need a symlink at the old location for compatibility:
```bash
# Create symlink from old location to new location
ln -s /Volumes/main-filestore/ai-PA /Users/dorseyhomeserver/ai-PA
```

**OR** update any scripts/tools that reference the old path.

---

## Phase 5: Verify and Test

### Step 5.1: Validate docker-compose.yml
```bash
cd /Volumes/main-filestore/ai-PA
docker compose config
```
1. [ ] No errors in docker-compose validation
2. [ ] All volume paths resolve correctly
3. [ ] All build contexts point to correct locations

### Step 5.2: Test backup script
```bash
cd /Volumes/main-filestore/ai-PA
./deployment/scripts/backup.sh --dry-run
```
1. [ ] Dry-run completes successfully
2. [ ] Backup path resolves to: `/Volumes/main-filestore/ai-PA-backups/...`
3. [ ] No errors about missing paths

### Step 5.3: Start Docker services
```bash
cd /Volumes/main-filestore/ai-PA
docker compose up -d
```
1. [ ] All services start successfully
2. [ ] Health checks pass: `docker compose ps`
3. [ ] Verify backup volume mount works: `docker exec scheduler-service ls /workspace/deployment/backups`

---

## Phase 6: Post-Migration Cleanup

### Step 6.1: Verify backup functionality
1. [ ] Run a test backup: `./deployment/scripts/backup.sh --config-only`
2. [ ] Verify backup appears in `/Volumes/main-filestore/ai-PA-backups/`
3. [ ] Check backup manifest is created correctly

### Step 6.2: Clean up old locations (if moved, not symlinked)
1. [ ] Verify nothing references old path
2. [ ] Remove old directory if symlink approach was used
3. [ ] Update any documentation with new paths

### Step 6.3: Update environment/configuration files
1. [ ] Update any `.env` files if they have absolute paths
2. [ ] Check scheduler jobs reference correct paths
3. [ ] Update any cron jobs or systemd timers

---

## Files Modified Summary

- [x] `docker-compose.yml` - Line 352: Update backup path
- [x] `deployment/backups` - Symlink updated to point to new location
- [ ] Verify `.env` files don't have hardcoded paths
- [ ] Check `deployment/config/backup-schedule.conf` for path references

---

## Rollback Plan (if needed)

If something goes wrong:

1. **Restore symlink:**
   ```bash
   rm /Volumes/main-filestore/ai-PA/deployment/backups
   ln -s /Volumes/working-drive/ai-PA-backups /Volumes/main-filestore/ai-PA/deployment/backups
   ```

2. **Restore docker-compose.yml:**
   ```bash
   git checkout docker-compose.yml  # If in git
   # Or restore from backup
   ```

3. **Move project back:**
   ```bash
   sudo mv /Volumes/main-filestore/ai-PA /Users/dorseyhomeserver/ai-PA
   ```

4. **Move backups back:**
   ```bash
   sudo mv /Volumes/main-filestore/ai-PA-backups /Volumes/working-drive/ai-PA-backups
   ```

---

## Notes

- Docker named volumes (supabase_db, n8n_data, etc.) remain in Docker's internal storage
- If you want to move Docker volumes to external drive, that requires Docker Desktop configuration changes
- The backup script uses `BACKUP_DIR` env var or defaults to `$PROJECT_ROOT/deployment/backups` (which resolves via symlink)
- All relative paths in docker-compose.yml (`./...`) will work from the new location
- Cloudflared config at `/Users/dorseyhomeserver/.cloudflared` should remain in home directory (separate from project)

