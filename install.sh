#!/bin/sh
# Installs PS5 Control Panel system-wide. Run: sudo ./install.sh
set -e
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo ./install.sh"; exit 1; }
cd "$(dirname "$0")"

# Dependencies (Arch/CachyOS): tkinter, polkit, xorg-xhost, lm_sensors,
# python-pillow (smooth, anti-aliased buttons and graph)
if command -v pacman >/dev/null 2>&1; then
    pacman -S --needed --noconfirm tk polkit xorg-xhost lm_sensors python-pillow
fi

install -d /opt/ps5-control-panel
install -m 755 ps5_control_gui.py /opt/ps5-control-panel/ps5_control_gui.py
install -m 644 icon.svg /opt/ps5-control-panel/icon.svg
install -m 755 ps5-control-panel /usr/local/bin/ps5-control-panel
install -m 644 ps5-control-panel.desktop /usr/share/applications/ps5-control-panel.desktop
update-desktop-database /usr/share/applications 2>/dev/null || true

echo "Installed. Find 'PS5 Control Panel' in your app menu, or run: ps5-control-panel"
