#!/bin/bash

# Configuration
# ---------------------------------------------------------
# PACKAGE_NAME: Must be lowercase, no spaces
PACKAGE_NAME="wiretray"

# MENU_NAME: What you see in the App Launcher
MENU_NAME="WireTray"

# Use the first argument as version, default to "1.0" if not provided
VERSION="${1:-1.0}" 
SOURCE_SCRIPT="wiretray.py" 
MAINTAINER="Jack Macqueen"
DESCRIPTION="System tray utility to manage WireGuard connections."

# Detect System Architecture (amd64, arm64, etc.)
ARCH=$(dpkg --print-architecture)
# ---------------------------------------------------------

# Check for PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: PyInstaller is not installed."
    echo "Please run: pip install pyinstaller"
    exit 1
fi

echo "Building standalone binary with PyInstaller..."
pyinstaller --noconfirm --onefile --windowed --clean --name "$PACKAGE_NAME" "$SOURCE_SCRIPT"

# Verify build succeeded
if [ ! -f "dist/$PACKAGE_NAME" ]; then
    echo "Error: PyInstaller build failed."
    exit 1
fi

# Create a temporary directory for building .deb
rm -rf build
BUILD_DIR="build/${PACKAGE_NAME}_${VERSION}_${ARCH}"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/local/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"

echo "Creating directory structure for $MENU_NAME (v$VERSION) [$ARCH]..."

# 1. Copy the Compiled Binary
cp "dist/$PACKAGE_NAME" "$BUILD_DIR/usr/local/bin/$PACKAGE_NAME"
chmod 755 "$BUILD_DIR/usr/local/bin/$PACKAGE_NAME"

# 2. Create the Control file (Metadata)
cat <<EOF > "$BUILD_DIR/DEBIAN/control"
Package: $PACKAGE_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: wireguard-tools, libxcb-cursor0
Maintainer: $MAINTAINER
Description: $DESCRIPTION
 A system tray application to toggle WireGuard interfaces.
EOF

# 3. Create the Post-Installation Script
cat <<EOF > "$BUILD_DIR/DEBIAN/postinst"
#!/bin/bash
set -e

# Define the sudoers file path
SUDOERS_FILE="/etc/sudoers.d/$PACKAGE_NAME"

# Allow the 'sudo' group to run wg-quick without password
echo "%sudo ALL=(ALL) NOPASSWD: /usr/bin/wg-quick" > "\$SUDOERS_FILE"
chmod 0440 "\$SUDOERS_FILE"

# --- NEW: Fix WireGuard Directory Permissions ---
# This allows the GUI app (running as user) to list the .conf files
if [ -d "/etc/wireguard" ]; then
    echo "Updating /etc/wireguard permissions to allow listing configs..."
    chmod o+rx /etc/wireguard
fi

exit 0
EOF

chmod 755 "$BUILD_DIR/DEBIAN/postinst"

# 4. Create the Post-Removal Script
cat <<EOF > "$BUILD_DIR/DEBIAN/postrm"
#!/bin/bash
set -e
SUDOERS_FILE="/etc/sudoers.d/$PACKAGE_NAME"
if [ "\$1" = "remove" ]; then
    if [ -f "\$SUDOERS_FILE" ]; then
        rm "\$SUDOERS_FILE"
    fi
fi
exit 0
EOF

chmod 755 "$BUILD_DIR/DEBIAN/postrm"

# 5. Create the .desktop file
cat <<EOF > "$BUILD_DIR/usr/share/applications/$PACKAGE_NAME.desktop"
[Desktop Entry]
Name=$MENU_NAME
Comment=$DESCRIPTION
Exec=/usr/local/bin/$PACKAGE_NAME
Icon=network-vpn
Terminal=false
Type=Application
Categories=Network;Utility;
EOF

# 6. Build the .deb package
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build "$BUILD_DIR" "$DEB_FILE"
rm -rf build dist "$PACKAGE_NAME.spec"

echo "Success! Package created at: $DEB_FILE"
echo "Run these commands to install:"
echo "sudo dpkg -i ./$DEB_FILE"
echo "sudo apt-get install -f"