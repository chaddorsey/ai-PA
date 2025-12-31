#!/bin/bash
#
# Prevent macOS from creating ._* metadata files on external drives
# This script configures the system to avoid creating resource fork files
#

echo "Configuring macOS to prevent ._* metadata file creation..."
echo ""

# Method 1: Use dot_clean to remove existing and prevent future creation
# This works for mounted volumes
if [ -d "/Volumes/main-drive" ]; then
    echo "Cleaning existing ._* files on main-drive..."
    dot_clean /Volumes/main-drive/ai-PA 2>/dev/null || echo "Note: dot_clean may require admin privileges"
fi

# Method 2: Set environment variable to prevent creation
# Add to shell profile
SHELL_PROFILE=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_PROFILE="$HOME/.zshrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_PROFILE="$HOME/.bash_profile"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_PROFILE="$HOME/.bashrc"
fi

if [ -n "$SHELL_PROFILE" ]; then
    if ! grep -q "COPYFILE_DISABLE" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# Prevent macOS from creating ._* metadata files" >> "$SHELL_PROFILE"
        echo "export COPYFILE_DISABLE=1" >> "$SHELL_PROFILE"
        echo "Added COPYFILE_DISABLE to $SHELL_PROFILE"
    else
        echo "COPYFILE_DISABLE already in $SHELL_PROFILE"
    fi
fi

# Method 3: Configure git to ignore them globally
if ! git config --global core.excludesfile >/dev/null 2>&1; then
    GLOBAL_GITIGNORE="$HOME/.gitignore_global"
    touch "$GLOBAL_GITIGNORE"
    if ! grep -q "^\._\*" "$GLOBAL_GITIGNORE" 2>/dev/null; then
        echo "# macOS resource fork files" >> "$GLOBAL_GITIGNORE"
        echo "._*" >> "$GLOBAL_GITIGNORE"
        echo ".DS_Store" >> "$GLOBAL_GITIGNORE"
    fi
    git config --global core.excludesfile "$GLOBAL_GITIGNORE"
    echo "Configured global git ignore for ._* files"
fi

echo ""
echo "Configuration complete!"
echo ""
echo "To apply immediately, run:"
echo "  export COPYFILE_DISABLE=1"
echo ""
echo "Or restart your terminal."
