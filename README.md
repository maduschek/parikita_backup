<div align="center">

# PariKita Backup & Bulletin Viewer

**Back up your PariKita data and explore bulletin posts, calendar entries, and photos in a local desktop viewer.**

[Getting started](#quick-start) · [How it works](#how-it-works) · [Bulletin Viewer](#bulletin-viewer) · [Troubleshooting](#troubleshooting)

</div>

---

## About this project

PariKita is an app used for communication between childcare institutions and families. Over time, important information can accumulate in announcements, messages, calendars, and photos. This community-developed project offers a way to **export data accessible to your own PariKita account** and browse part of that archive on a computer.

The project has two main components:

- **Backup Assistant** (`run_me.sh`) — guides you through connecting an Android phone, capturing a session token with Frida, and downloading data from the PariKita API.
- **Bulletin Viewer** (`bulletin_viewer.py`) — a local Tkinter desktop application for browsing bulletin entries, calendar information, and associated photographs and attachments.

The downloaded records are stored locally as JSON, with additional human-readable text exports and downloaded media. This is an **unofficial project**, not affiliated with or endorsed by PariKita or its operator. API compatibility may change when the app is updated.

> [!IMPORTANT]
> Use this software only with an account and data you are authorized to access. Backups may contain children's photos, messages, contact details, and other personal information. Keep the output private and follow applicable privacy and institutional rules.

## Features

| Backup | Local viewer |
| --- | --- |
| Guided terminal setup and phone connection | Search bulletin and calendar content |
| Frida server download matched to the installed client | Sort entries by date, newest or oldest first |
| Session-token capture during app login | Show only entries with available images |
| API-based export of bulletin posts, feed, and gallery data | Read formatted post text and calendar information |
| Retrieval of messages, calendar items, and other accessible records | Browse image thumbnails and open full-size photos |
| Download of images and available attachments | Zoom images and navigate between photos |
| JSON files and readable text exports | Open supported attachments in the default system application |

The exact data available depends on the account, the current API, and the coverage of the Python scripts. The viewer focuses on bulletin, calendar, and image content; it is **not** a complete graphical interface for every exported JSON file.

## Requirements

### Computer

- **Linux** (the assistant uses `apt`, so Debian/Ubuntu-based distributions are the easiest option)
- **Python 3.10+** (for the type annotations used in the viewer)
- **Git**, **ADB**, **tmux**, **wget**, and **xz-utils**
- **Tkinter** for the graphical viewer (`python3-tk` on Ubuntu/Debian)
- **Python dependencies** listed in [`requirements.txt`](requirements.txt), including `requests`, `Pillow`, `frida-tools`, `fonttools`, and `uiautomator2`
- A desktop environment for the Bulletin Viewer
- An internet connection for installation and API downloads

### Android phone

- PariKita installed and a working, authorized account
- USB cable and **USB debugging** enabled in Android Developer Options
- **Root access** on the phone, available through `su` (required by the provided Frida-server workflow)
- Approval of the computer's USB debugging authorization prompt

> [!NOTE]
> Root access is different from merely enabling Developer Options. The provided workflow launches Frida server as root on the Android device. Rooting a device may reduce its security or affect other applications. The project does not provide a rooting procedure.

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/maduschek/parikita_parsing.git
cd parikita_parsing
```

### 2. Install dependencies

```bash
sudo apt update
sudo apt install -y git adb tmux wget xz-utils python3 python3-pip python3-venv python3-tk

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

You can use an existing Conda environment instead. Activate it **before** launching the assistant so that the same Python environment is used for Frida and the backup.

### 3. Configure the backup script

Review [`pari_backup.py`](pari_backup.py) before the first run. In particular, check the account-dependent identifiers such as `CHILD_ID` and `INSTITUTION_ID`. These are **not automatically generalized for every account** in the current script. The signed-in user's ID is obtained from the API during the backup, but other configured IDs may still need adjustment.

**Do not put session tokens, private identifiers, or exported personal data into Git commits.** See [Security and privacy](#security-and-privacy).

### 4. Connect your Android device

Enable USB debugging, connect the phone by cable, and approve the authorization prompt. Check the connection with:

```bash
adb devices
```

You should see one device with status `device`, not `unauthorized`.

### 5. Start the guided assistant

```bash
chmod +x run_me.sh
./run_me.sh
```

Follow the on-screen steps:

1. The assistant checks the required tools and prepares a matching Frida server.
2. It uploads and starts Frida server on the rooted Android phone.
3. **Open PariKita but do not log in yet.** Confirm in the terminal when the app is ready.
4. The assistant attaches its Frida script. **Log in only when prompted.**
5. After a token is captured, the script downloads the available data to `parikita_backup/`.
6. Once the backup finishes successfully, choose whether to start the **Bulletin Viewer**.

The first run may take longer because dependencies must be installed and images downloaded. The script requires the PariKita process to be running when Frida attaches.

## How it works

```text
  Android phone                       Linux computer
  ┌─────────────────┐                 ┌────────────────────────────┐
  │ PariKita app    │◄──── ADB ─────►│ run_me.sh                  │
  │                 │                 │  ├─ Frida server setup     │
  │ Login / session │── Frida hook ──►│  ├─ token.js               │
  └─────────────────┘                 │  └─ session token capture  │
                                      └────────────┬───────────────┘
                                                   │
                                           authenticated API calls
                                                   │
                                      ┌────────────▼───────────────┐
                                      │ pari_backup.py             │
                                      │ JSON · text · photos       │
                                      └────────────┬───────────────┘
                                                   │
                                      ┌────────────▼───────────────┐
                                      │ bulletin_viewer.py         │
                                      │ Local desktop interface    │
                                      └────────────────────────────┘
```

**1. Token capture.** The JavaScript hook in [`token.js`](token.js) uses [Frida](https://frida.re/) to observe the app's session-token setup during login. The assistant runs the Frida client inside a detached `tmux` session, monitors its output for `TOKEN=`, and writes the captured token into `mytoken.txt`.

**2. API export.** [`pari_backup.py`](pari_backup.py) reads the token, sends authenticated requests to the service API, and writes downloaded records and available media to disk. Some endpoints are paginated. Exported data includes feed and bulletin records, mail folders, calendar information, gallery images, attachments, and additional account data when supported.

**3. Local browsing.** [`bulletin_viewer.py`](bulletin_viewer.py) reads the saved JSON files and media folders. Browsing an existing archive does not require a connected phone or another login.

## Backup files

A successful backup creates a directory approximately like this:

```text
parikita_backup/
├── json/
│   ├── bulletin_all.json
│   ├── calendar_entries.json
│   ├── feed_all.json
│   ├── mails_folder_1.json
│   ├── ...
│   └── profile.json
├── text/
│   ├── posts_readable.txt
│   └── mails_readable.txt
└── downloads/
    ├── images/
    │   └── YYYY-MM-DD/
    │       └── ...
    ├── attachments/
    └── mail_attachments/
```

The full list of generated files can vary by API response and script version. Images are generally placed in date-based folders, where possible, and the backup code attempts to retain useful descriptions in image metadata.

## Bulletin Viewer

The **Bulletin Viewer** provides a convenient graphical way to revisit exported announcements and related media without scrolling through raw JSON or navigating hundreds of folders.

### Launch it

The Backup Assistant offers to start the viewer after a successful backup. You can also open it independently:

```bash
python bulletin_viewer.py
```

The default data sources are:

- `parikita_backup/json/bulletin_all.json`
- `parikita_backup/json/calendar_entries.json`
- Downloaded media under `parikita_backup/downloads/`

### Browse your archive

The application features a list of dated entries on the left and a detail area on the right. You can:

- **Search** entries by text.
- **Change date order** between newest first and oldest first.
- **Filter** for posts that have locally available images.
- **Read** posts and calendar items, including relevant meal-plan and event details when present.
- **Open** linked local attachments using your operating system's default application.
- **Explore photos** as thumbnails and click to view larger versions.

In the full-screen-style image dialog, use the **left/right arrow keys** to switch images, **+ / −** to zoom, **0** to reset zoom, and **Esc** to close the dialog.

### Custom archive locations

To open exported data stored elsewhere:

```bash
python bulletin_viewer.py \
  --json /path/to/archive/json/bulletin_all.json \
  --calendar-json /path/to/archive/json/calendar_entries.json \
  --images /path/to/archive/downloads/images \
           /path/to/archive/downloads/attachments \
           /path/to/archive/downloads/mail_attachments
```

The viewer uses Tkinter and Pillow. It runs locally; the underlying backup files remain on your computer.

## Project files

| File | Purpose |
| --- | --- |
| [`run_me.sh`](run_me.sh) | Interactive end-to-end setup, token capture, backup, and optional viewer launch |
| [`token.js`](token.js) | Frida hooks for observing session-token creation |
| [`pari_backup.py`](pari_backup.py) | API client and data/media exporter |
| [`bulletin_viewer.py`](bulletin_viewer.py) | Tkinter-based browser for bulletin, calendar, images, and attachments |
| [`requirements.txt`](requirements.txt) | Python dependencies |
| [`setup_phone.sh`](setup_phone.sh) | Earlier, less automated phone setup script |
| [`old_scripts/`](old_scripts/) | Historical parsing experiments |

## Troubleshooting

**`adb devices` shows `unauthorized` or no device.** Unlock the phone, accept the USB debugging prompt, reconnect the cable, and check that USB debugging is enabled.

**Frida cannot connect or terminates immediately.** Verify that the phone is rooted, `su` is available, Frida server is running, and the server/client versions match. Also confirm that the PariKita app is open before attaching. Inspect `frida.log` for the full Frida output.

**The assistant keeps waiting for `TOKEN=`.** Make sure you log in *after* the hook is installed. The hook depends on app internals and may need updating for a newer PariKita release. Check `frida.log` for hook errors or unexpected output.

**Python reports a missing module.** Activate the environment used for installation and rerun `python -m pip install -r requirements.txt`. For `tkinter` errors on Ubuntu/Debian, install `python3-tk`.

**The viewer shows no records or images.** Confirm that `bulletin_all.json` exists and that the media paths point to downloaded files. Pass custom locations using `--json`, `--calendar-json`, and `--images` if necessary.

**An API request returns 401/403 or unexpected JSON.** The session may have expired, the requested data may not be accessible to your account, or the service API may have changed. Capture a new session through the normal login flow and review account-specific configuration.

## Security and privacy

> [!CAUTION]
> **The repository currently contains a hard-coded token and account-specific identifiers in `pari_backup.py`. These should be treated as exposed and removed from the public source.** Revoke or invalidate any exposed live credentials, move configuration to local environment variables or an ignored configuration file, and review Git history. Merely deleting a secret from the latest commit does not remove it from earlier commits.

- `mytoken.txt` and `frida.log` can contain authentication secrets. Never upload or share them.
- The default `.gitignore` excludes `parikita_backup/`, but you should **also exclude local tokens and logs** before using Git. A useful addition is:

  ```gitignore
  mytoken.txt
  frida.log
  .venv/
  *.tmp
  ```

- Exported material may contain sensitive information about children, families, and staff. Store it on an encrypted disk where appropriate, do not publish it, and delete copies you no longer need.
- This script does not bypass account authorization: use it only for material you are permitted to view and export.

## Limitations

This is an experimental, community-maintained utility. It may require adaptation to different Android devices, PariKita versions, account structures, or API responses. Downloads are not guaranteed to cover every in-app feature; some API calls are implemented on a best-effort basis. No official backup or restore compatibility is implied.

## Contributing

Bug reports and improvements are welcome through [GitHub Issues](https://github.com/maduschek/parikita_parsing/issues). Useful contributions include safer configuration handling, more reliable API parsing, better device support, and enhancements to the Bulletin Viewer.

Please redact tokens, names, personal messages, and images before sharing logs or example data.

---

<div align="center">

**PariKita Backup & Bulletin Viewer**  
*An unofficial tool for creating and exploring a personal local archive.*

</div>
