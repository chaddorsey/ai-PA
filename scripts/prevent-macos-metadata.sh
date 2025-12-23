#!/bin/bash
# Prevent macOS from creating metadata files on external drives and network volumes
# Run this once to configure your system

echo "Configuring macOS to prevent metadata file creation..."
echo ""

# Prevent .DS_Store on network and USB volumes
echo "Preventing .DS_Store creation on network and USB volumes..."
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true

# Verify settings
echo ""
echo "Current settings:"
echo "  DSDontWriteNetworkStores: $(defaults read com.apple.desktopservices DSDontWriteNetworkStores 2>/dev/null || echo 'not set')"
echo "  DSDontWriteUSBStores: $(defaults read com.apple.desktopservices DSDontWriteUSBStores 2>/dev/null || echo 'not set')"
echo ""

echo "✓ Configuration applied"
echo ""
echo "Note: You may need to log out and log back in for these changes to take full effect."
echo ""
echo "To also prevent ._* files during file operations, add to your ~/.zshrc:"
echo "  export COPYFILE_DISABLE=1"
