#!/bin/bash
# Build and install the openfile:// URL scheme handler
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Applications/OpenFileHandler.app"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"

echo "Building OpenFileHandler..."
mkdir -p "$APP_DIR/Contents/MacOS"
cp "$SCRIPT_DIR/Info.plist" "$APP_DIR/Contents/"

swiftc -o "$APP_DIR/Contents/MacOS/openfile-handler" \
    -framework Cocoa \
    "$SCRIPT_DIR/main.swift"

echo "Registering URL scheme..."
"$LSREGISTER" -R "$APP_DIR"

echo "Installed to $APP_DIR"
echo "Test with: open 'openfile:///System/Library/CoreServices/Finder.app'"
