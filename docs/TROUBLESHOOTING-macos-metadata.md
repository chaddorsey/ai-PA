# macOS Metadata Files (.DS_Store and ._*)

## The Problem

macOS creates metadata files that can cause issues:
- **`._*` files**: Resource fork files storing extended attributes
- **`.DS_Store` files**: Finder metadata for folder views

These files are especially problematic on:
- External drives (like `/Volumes/main-drive`)
- Docker-mounted volumes
- Python virtual environments
- Git repositories

## Why They Appear

1. **External Drives**: macOS creates resource forks on non-HFS+ volumes to preserve extended attributes
2. **File Operations**: Created when copying, moving, or accessing files
3. **Finder**: `.DS_Store` files are created when browsing folders in Finder

## Prevention

### 1. Environment Variable (Recommended)

Add to your `~/.zshrc` or `~/.bash_profile`:
```bash
export COPYFILE_DISABLE=1
```

This prevents creation during `tar`, `cp`, and other operations.

### 2. Global Git Ignore

Already configured via:
```bash
git config --global core.excludesfile ~/.gitignore_global
```

This ensures git ignores these files globally.

### 3. Project .gitignore

The project `.gitignore` already includes:
```
._*
.DS_Store
```

### 4. Clean Existing Files

Run the cleanup script:
```bash
./scripts/clean-macos-metadata.sh
```

Or use macOS's built-in tool:
```bash
dot_clean /Volumes/main-drive/ai-PA
```

## Configuration Script

Run once to set up all prevention measures:
```bash
./scripts/prevent-macos-metadata.sh
```

This will:
- Add `COPYFILE_DISABLE=1` to your shell profile
- Configure global git ignore
- Clean existing metadata files

## When They Still Appear

Even with prevention, they may still appear because:
- Some tools bypass `COPYFILE_DISABLE`
- Finder creates `.DS_Store` regardless
- External drive behavior is hard to fully prevent

**Solution**: The cleanup script and git ignore handle this automatically.

## References

- [Apple: dot_clean man page](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man1/dot_clean.1.html)
- [Git: Ignoring Files](https://git-scm.com/docs/gitignore)

