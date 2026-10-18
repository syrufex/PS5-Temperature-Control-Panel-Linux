# PS5 Temperature Control Panel (Linux)

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform: Linux on PS5](https://img.shields.io/badge/platform-Linux%20on%20PS5-6bb6ff.svg)
![Python 3](https://img.shields.io/badge/python-3-green.svg)

A small desktop app for **Linux running on a PS5**. It puts temperature monitoring, fan control, the front LED and an on-screen overlay in one window, so you don't have to type commands.

<!-- To add a screenshot: upload it to this repo as screenshot.png, then delete this comment line and remove the two marker lines around the image line below.
-->
<!--
![PS5 Control Panel](screenshot.png)
-->

## Features

- **Live temperatures** for CPU and NVMe, with a 3-minute graph. Readings turn green, amber or red as they get hotter.
- **Fan thermal target**: a slider from 40 to 95 °C that writes to `/sys/devices/platform/ps5-fan/target_temp`. Lower means the fan works harder, sooner.
- **Fixed fan patterns and boost**: Fan On / Off / Max and Boost On / Off buttons, using the `ps5_control` command.
- **Front LED color**: pick a color or animation for the PS5 indicator LED.
- **Screen overlay**: a small always-on-top temperature box you can pin to any corner of the screen, with adjustable opacity.
- **Themes and fonts**: Dark, Light, or System (follows your desktop), plus a font picker.
- **Remembers your settings** between launches.

## Requirements

- Linux running on a PS5, with the PS5 fan and LED kernel drivers available.
- An Arch-based distro for the one-step installer (it uses `pacman`). Other distros can install the dependencies by hand.
- Python 3 with Tk, plus `lm_sensors`, `polkit`, `xorg-xhost` and Pillow (`python-pillow`). The installer sets these up for you. The app still runs without Pillow, just with rougher-looking graphics.
- Optional: the `ps5_control` command. The Fan On / Off / Max and Boost buttons call it. Without it those buttons show a "not installed" message and everything else still works.

## Install

```sh
git clone https://github.com/syrufex/PS5-Temperature-Control-Panel-Linux.git
cd PS5-Temperature-Control-Panel-Linux
sudo sh install.sh
```

Then open **PS5 Control Panel** from your app menu, or run:

```sh
ps5-control-panel
```

The app asks for your password in a normal pop-up, because changing fan and LED settings needs root.

No git? Click the green **Code** button on this page, choose **Download ZIP**, extract it, open a terminal in the extracted folder and run `sudo sh install.sh`.

### On another distro

Install the equivalents of `tk`, `polkit`, `xorg-xhost`, `lm_sensors` and Pillow with your package manager, then run `sudo sh install.sh`. The installer skips the `pacman` step when `pacman` isn't found.

### Run without installing

```sh
sudo python3 ps5_control_gui.py
```

## Using the app

| Tab | What it does |
| --- | --- |
| **Monitor** | Live CPU and NVMe temperatures, the graph, and the screen overlay controls (show/hide, corner, opacity). |
| **Cooling** | The fan target slider (press **Apply target** to save it) and the fixed fan and boost buttons. |
| **LED** | Choose a front LED color or animation, then press **Set color**. |
| **Style** | Pick Dark, Light or System theme, and a font. Only installed fonts are listed. |

## Update

Download the latest version and run the installer again. It replaces the old install:

```sh
git pull
sudo sh install.sh
```

## Uninstall

```sh
sudo sh uninstall.sh
```

This removes the app, the `ps5-control-panel` command, the app-menu entry and your saved settings. It does not remove the packages the installer added, since other programs may use them.

## Troubleshooting

- **The window doesn't open from the app menu.** Run `ps5-control-panel` in a terminal and read the error. On Wayland the app runs through XWayland, and the launcher uses `xhost` to let root draw on your screen.
- **Temperatures show `?`, or "sensors not available".** Install `lm_sensors` and run `sudo sensors-detect`. The app reads `Tctl` (CPU) and `Composite` (NVMe) from the `sensors` command.
- **"Write failed" when applying the fan target.** The `ps5-fan` driver isn't loaded, or its sysfs path is different on your setup.
- **LED colors do nothing.** The app writes to `/sys/class/leds/ps5:<name>:indicator`. Check that those entries exist.
- **The font list only shows "System default".** Install a font, for example `sudo pacman -S inter-font`, then reopen the app.
- **Buttons look jagged.** Pillow isn't installed. Run `sudo pacman -S python-pillow`.
- **The overlay hides behind fullscreen games.** It is a normal always-on-top window, which some Wayland compositors ignore for fullscreen apps.

## How it works

- `ps5_control_gui.py` is the whole app. It is written in Python with Tkinter, and Pillow is used only to draw smooth shapes.
- `ps5-control-panel` is the launcher. It uses `pkexec` to run the app as root.
- `install.sh` copies the app to `/opt/ps5-control-panel`, adds the `ps5-control-panel` command and the app-menu entry.
- Settings are saved in `/var/lib/ps5-control-panel/settings.json`.

## Files

| File | Purpose |
| --- | --- |
| `ps5_control_gui.py` | The app |
| `ps5-control-panel` | Launcher script (asks for your password, then starts the app) |
| `ps5-control-panel.desktop` | App-menu entry |
| `icon.svg` | App icon |
| `install.sh` / `uninstall.sh` | Install and remove |
| `CHANGELOG.md` | Version history |
| `LICENSE` | MIT license |

## Contributing

Bug reports and ideas are welcome. Open an [issue](https://github.com/syrufex/PS5-Temperature-Control-Panel-Linux/issues) and include the error message plus your distro. Pull requests are welcome too.

## License

[MIT](LICENSE) © 2026 syrufex
