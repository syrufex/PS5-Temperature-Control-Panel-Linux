# PS5 Control Panel

A small desktop app for **Linux running on a PS5**. It puts the fan, LED and temperature controls in one window instead of the terminal.

<!-- Add a screenshot: save it as screenshot.png in this folder and uncomment the next line -->
<!-- ![PS5 Control Panel](screenshot.png) -->

## Features

- **Live temperatures** for CPU and NVMe, with a 3-minute graph. Values are colored green, amber or red depending on how hot they are.
- **Fan thermal target** slider (40 to 95 °C) that writes to `/sys/devices/platform/ps5-fan/target_temp`.
- **Fixed fan patterns and boost** buttons (Fan On / Off / Max, Boost On / Off) through the `ps5_control` tool.
- **Front LED color** picker for the PS5 indicator LED.
- **Screen overlay**: an always-on-top temperature box you can pin to any screen corner, with adjustable opacity.
- **Themes and fonts**: Dark, Light, or System (follows your desktop), plus a font picker. Your choices are remembered.

## Requirements

- Linux running on a PS5 with the PS5 fan and LED kernel drivers available.
- Python 3 with Tk, `lm_sensors`, `polkit` and Pillow (`python-pillow`, for smooth anti-aliased buttons and graph). The installer sets these up on Arch-based distros. The app still runs without Pillow, just with rougher-looking graphics.
- Optional: the `ps5_control` command, which the Fan On / Off / Max and Boost buttons call. Without it, those buttons show a "not installed" message and everything else still works.

## Install

On an Arch-based distro (Arch, CachyOS, Manjaro, ...):

```sh
git clone https://github.com/YOUR_USERNAME/ps5-control-panel.git
cd ps5-control-panel
sudo ./install.sh
```

Then open **PS5 Control Panel** from your app menu, or run:

```sh
ps5-control-panel
```

It asks for your password in a normal pop-up because changing fan and LED settings needs root.

On other distros, install the equivalents of `tk`, `polkit`, `xorg-xhost`, `lm_sensors` and Pillow yourself, then run `install.sh`. The pacman step is skipped when `pacman` is not found.

### Run without installing

```sh
sudo python3 ps5_control_gui.py
```

## Update

Pull the latest version and run the installer again. It replaces the old install:

```sh
git pull
sudo ./install.sh
```

## Uninstall

```sh
sudo ./uninstall.sh
sudo rm -rf /var/lib/ps5-control-panel   # optional: removes saved settings
```

The uninstaller does not remove the packages the installer added, since other programs may use them.

## Troubleshooting

- **The window doesn't open from the app menu.** Run `ps5-control-panel` in a terminal and read the error. On Wayland desktops the app runs through XWayland, and the launcher uses `xhost` to let root draw on your screen.
- **"sensors not available" or `?` temperatures.** Install `lm_sensors` and run `sudo sensors-detect`. The app reads `Tctl` (CPU) and `Composite` (NVMe) from `sensors`.
- **"Write failed" when applying the fan target.** The `ps5-fan` driver is not loaded, or its sysfs path is different on your setup.
- **The LED colors do nothing.** The app writes to `/sys/class/leds/ps5:<name>:indicator`. Check that those entries exist.
- **Only "System default" in the font list.** Install a font, for example `sudo pacman -S inter-font`, and reopen the app.
- **The overlay sits behind fullscreen games.** It uses a normal always-on-top window, which some Wayland compositors ignore for fullscreen apps.

## How it works

- `ps5_control_gui.py` is the whole app (Tkinter, no extra Python packages).
- `ps5-control-panel` is the launcher. It uses `pkexec` to run the app as root.
- `install.sh` copies everything to `/opt/ps5-control-panel`, adds the `ps5-control-panel` command and the app-menu entry.
- Settings are saved in `/var/lib/ps5-control-panel/settings.json`.

## Files

| File | Purpose |
| --- | --- |
| `ps5_control_gui.py` | The app |
| `ps5-control-panel` | Launcher script (asks for your password, then starts the app) |
| `ps5-control-panel.desktop` | App-menu entry |
| `icon.svg` | App icon |
| `install.sh` / `uninstall.sh` | Install and remove |
