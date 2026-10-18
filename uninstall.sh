#!/bin/sh
# Run: sudo ./uninstall.sh
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo ./uninstall.sh"; exit 1; }
rm -rf /opt/ps5-control-panel
rm -f /usr/local/bin/ps5-control-panel /usr/share/applications/ps5-control-panel.desktop
update-desktop-database /usr/share/applications 2>/dev/null || true
echo "Removed."
