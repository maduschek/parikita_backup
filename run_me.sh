
#!/usr/bin/env bash
#
# PariKita Backup Assistant
# -------------------------
# 1. Install and verify dependencies
# 2. Connect and prepare the Android device
# 3. Start Frida in a background tmux session
# 4. Capture the authentication token
# 5. Run the backup script
#
# Requirements:
#   - Linux with ADB and Python
#   - Rooted Android device with USB debugging
#   - token.js and pari_backup.py in this directory
#

set -o pipefail

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

APP_NAME="PariKita"
SESSION="parikita_frida"

WORKDIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKDIR" || exit 1

TOKEN_FILE="$WORKDIR/mytoken.txt"
FRIDA_LOG="$WORKDIR/frida.log"
SERVER_FILE="$WORKDIR/frida-server"

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ------------------------------------------------------------
# USER INTERFACE
# ------------------------------------------------------------

clear

printf "${CYAN}${BOLD}"
cat <<'EOF'
   ____________________________________________
  /                                            \
 |     ____            _ _  ___ _ _            |
 |    |  _ \ __ _ _ __(_) |/ (_) |_ __ _       |
 |    | |_) / _` | '__| | ' /| | __/ _` |      |
 |    |  __/ (_| | |  | | . \| | || (_| |      |
 |    |_|   \__,_|_|  |_|_|\_\_|\__\__,_|      |
 |                                             |
 |            B A C K U P   A S S I S T A N T  |
  \____________________________________________/
EOF
printf "${RESET}\n"

info() {
    printf "${CYAN}[INFO]${RESET} %s\n" "$*"
}

success() {
    printf "${GREEN}[ OK ]${RESET} %s\n" "$*"
}

warning() {
    printf "${YELLOW}[WARN]${RESET} %s\n" "$*"
}

error() {
    printf "${RED}[FAIL]${RESET} %s\n" "$*" >&2
    exit 1
}

step() {
    printf "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "${BOLD} STEP %s${RESET}\n" "$1"
    printf "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"
}

pause() {
    printf "\n${YELLOW}➜ %s${RESET}" "$1"
    read -r -n 1 -s _
    printf "\n"
}

# ------------------------------------------------------------
# STEP 1: INSTALL DEPENDENCIES
# ------------------------------------------------------------

step "1/5 — Checking dependencies"

# Install Linux utilities only when missing.
PACKAGES=()

command -v tmux >/dev/null || PACKAGES+=(tmux)
command -v adb  >/dev/null || PACKAGES+=(adb)
command -v wget >/dev/null || PACKAGES+=(wget)
command -v unxz >/dev/null || PACKAGES+=(xz-utils)

if ((${#PACKAGES[@]} > 0)); then
    info "Installing: ${PACKAGES[*]}"
    sudo apt install -y "${PACKAGES[@]}" ||
        error "Failed to install required packages."
fi

# Install Frida into the current Python/Conda environment.
if ! command -v frida >/dev/null; then
    info "Installing Frida tools..."
    python -m pip install frida-tools ||
        error "Frida installation failed."
fi

# Resolve absolute executable paths to avoid tmux PATH problems.
FRIDA_BIN="$(command -v frida)"
PYTHON_BIN="$(command -v python)"

FRIDA_VERSION="$(frida --version)" ||
    error "Cannot determine Frida version."

success "Frida version: $FRIDA_VERSION"
success "Python: $PYTHON_BIN"

# Ensure the local scripts exist.
[[ -f token.js ]] ||
    error "Missing file: token.js"

[[ -f pari_backup.py ]] ||
    error "Missing file: pari_backup.py"

# ------------------------------------------------------------
# STEP 2: CONNECT AND PREPARE ANDROID DEVICE
# ------------------------------------------------------------

step "2/5 — Preparing Android device"

printf "Connect your Android phone using USB.\n\n"
printf "Make sure the following are enabled:\n"
printf "  [1] Developer options\n"
printf "  [2] USB debugging\n"
printf "  [3] Root access / Rooted debugging\n"

pause "Press any key when your phone is connected..."

adb start-server >/dev/null

# Verify that ADB can communicate with the phone.
if [[ "$(adb get-state 2>/dev/null)" != "device" ]]; then
    adb devices
    error "No authorized Android device found."
fi

success "Android device connected."

# Check architecture.
DEVICE_ARCH="$(adb shell getprop ro.product.cpu.abi | tr -d '\r')"

case "$DEVICE_ARCH" in
    arm64-v8a) SERVER_ARCH="android-arm64" ;;
    armeabi-v7a) SERVER_ARCH="android-arm" ;;
    x86_64) SERVER_ARCH="android-x86_64" ;;
    x86) SERVER_ARCH="android-x86" ;;
    *) error "Unsupported Android architecture: $DEVICE_ARCH" ;;
esac

info "Device architecture: $DEVICE_ARCH"

# ------------------------------------------------------------
# DOWNLOAD AND START FRIDA SERVER
# ------------------------------------------------------------

info "Preparing Frida server $FRIDA_VERSION..."

ARCHIVE="frida-server-${FRIDA_VERSION}-${SERVER_ARCH}.xz"
URL="https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/${ARCHIVE}"

# Download only when necessary.
if [[ ! -f "$SERVER_FILE" ]] ||
   [[ ! -f ".frida-version-${FRIDA_VERSION}-${SERVER_ARCH}" ]]; then

    wget -q --show-progress -O "$ARCHIVE" "$URL" ||
        error "Cannot download Frida server. Check the version and URL."

    xz -dc "$ARCHIVE" > "$SERVER_FILE" ||
        error "Cannot extract Frida server."

    chmod +x "$SERVER_FILE"

    rm -f "$ARCHIVE" .frida-version-*
    touch ".frida-version-${FRIDA_VERSION}-${SERVER_ARCH}"
fi

success "Frida server ready."

info "Uploading Frida server..."
adb push "$SERVER_FILE" /data/local/tmp/frida-server >/dev/null ||
    error "Failed to upload Frida server."

info "Starting Frida server with root privileges..."

adb shell "su -c 'chmod 755 /data/local/tmp/frida-server'" ||
    error "Root access failed."

adb shell "su -c '/data/local/tmp/frida-server >/dev/null 2>&1 </dev/null &'" ||
    error "Could not start Frida server."

sleep 2

# Verify that Frida can communicate with the device.
frida-ps -U >/dev/null 2>&1 ||
    error "Frida server is not responding."

success "Frida server running."

# ------------------------------------------------------------
# STEP 3: START PARIKITA AND TOKEN CAPTURE
# ------------------------------------------------------------

step "3/5 — Starting token capture"

printf "On your phone:\n\n"
printf "  1. Open ${BOLD}%s${RESET}.\n" "$APP_NAME"
printf "  2. Stay at the login screen.\n"
printf "  3. Do NOT log in yet.\n"

pause "Press any key once the app is open..."

# Avoid conflicts with an old tmux session.
if tmux has-session -t "=$SESSION" 2>/dev/null; then
    warning "Closing an existing Frida session."
    tmux kill-session -t "=$SESSION"
fi

# Clear logs from the previous run.
rm -f "$TOKEN_FILE" "$FRIDA_LOG"

info "Starting Frida in a background tmux session..."

# Build a shell-safe command using absolute paths.
# This retains the current Conda Python environment through
# the absolute Frida executable rather than relying on tmux PATH.
printf -v FRIDA_CMD '%q ' \
    "$FRIDA_BIN" -U -n "$APP_NAME" -l "$WORKDIR/token.js"

printf -v LOG_PATH '%q' "$FRIDA_LOG"

tmux new-session -d -s "$SESSION" -c "$WORKDIR" \
    "set -o pipefail; ${FRIDA_CMD} 2>&1 | tee ${LOG_PATH}" ||
    error "Could not start the Frida tmux session."

success "Frida session started."
info "Session name: $SESSION"
info "Full output: $FRIDA_LOG"

# Give Frida a moment to attach before login.
sleep 3

if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
    cat "$FRIDA_LOG"
    error "Frida terminated before login."
fi

# ------------------------------------------------------------
# STEP 4: CAPTURE TOKEN
# ------------------------------------------------------------

step "4/5 — Waiting for authentication token"

printf "${GREEN}${BOLD}"
printf "  ========================================\n"
printf "          LOG IN TO PARIKITA NOW\n"
printf "  ========================================\n"
printf "${RESET}\n"

info "Monitoring Frida output for TOKEN=..."
info "Press Ctrl+C to cancel."

# Wait for a line containing TOKEN=.
# Unlike ^TOKEN=, this also matches Frida prompt prefixes.
while ! grep -aq 'TOKEN=' "$FRIDA_LOG" 2>/dev/null; do

    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf "\n"
        cat "$FRIDA_LOG" 2>/dev/null
        error "Frida terminated unexpectedly."
    fi

    sleep 0.5
done

success "Token detected."

# Stop Frida before reading the final output.
tmux kill-session -t "=$SESSION" 2>/dev/null || true

# Extract the last token, stripping any Frida prompt prefix.
# Preserve '=' characters that may appear in Base64 tokens.
TOKEN="$(
    grep -a 'TOKEN=' "$FRIDA_LOG" |
    tail -n 1 |
    sed 's/.*TOKEN=//' |
    tr -d '\r'
)"

[[ -n "$TOKEN" ]] ||
    error "Token extraction returned an empty value."

# Save only the token, without extra Frida output.
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

success "Token saved to mytoken.txt."

# Never print the authentication token to the terminal.

# ------------------------------------------------------------
# STEP 5: START BACKUP
# ------------------------------------------------------------

step "5/5 — Starting backup"

info "Launching pari_backup.py..."

"$PYTHON_BIN" "$WORKDIR/pari_backup.py"
BACKUP_STATUS=$?

if [[ $BACKUP_STATUS -eq 0 ]]; then
    printf "\n${GREEN}${BOLD}"
    printf "  ========================================\n"
    printf "            BACKUP COMPLETED\n"
    printf "  ========================================\n"
    printf "${RESET}\n"
else
    warning "Backup exited with code $BACKUP_STATUS."
fi


# ------------------------------------------------------------
# STEP 6: LAUNCH BULLETIN VIEWER
# ------------------------------------------------------------

if [[ $BACKUP_STATUS -eq 0 ]]; then
    printf "\n"
    read -r -p "$(printf "${CYAN}➜${RESET} Start Bulletin Viewer now? [Y/n]: ")" ANSWER

    case "${ANSWER,,}" in
        ""|y|yes)
            info "Starting Bulletin Viewer..."
            "$PYTHON_BIN" "$WORKDIR/bulletin_viewer.py" ||
                warning "Bulletin Viewer could not be started."
            ;;
        *)
            info "Bulletin Viewer skipped."
            ;;
    esac
fi

printf "\n"
success "All tasks finished."

exit "$BACKUP_STATUS"