#!/bin/bash
# Weekly Photo Selector setup: installs the scripts into ~/weekly-photo-selector,
# creates a Python virtualenv, pulls a vision model and schedules the weekly
# run with launchd (Sundays at 10 PM local time).
#
#   ./setup_photo_selector.sh              # install (asks for photo source settings the first time)
#   ./setup_photo_selector.sh --configure  # only change photo source settings, e.g. fresh Amazon cookies

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEM_DIR="$HOME/weekly-photo-selector"
VENV="$SYSTEM_DIR/venv"
LABEL="com.weekly-photo-selector"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
VISION_MODEL="llama3.2-vision:latest"
ENV_FILE="$SYSTEM_DIR/photo-selector.env"
DEFAULT_SYNOLOGY_DIRS="~/nas-home/Photos/MobileBackup:~/nas-home/Photos/phockup"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Current value of KEY in the env file, or empty.
env_get() {
    [ -f "$ENV_FILE" ] || return 0
    awk -v k="$1" 'index($0, k "=") == 1 { v = substr($0, length(k) + 2) } END { print v }' "$ENV_FILE"
}

# True if VAR is exported by your shell (e.g. in ~/.bash_profile), which overrides the env file.
from_shell() { [ -n "${!1:-}" ]; }

# ask PROMPT DEFAULT [secret]: prints the answer, or DEFAULT if Enter is pressed.
ask() {
    local reply
    if [ "${3:-}" = secret ]; then
        read -r -s -p "$1${2:+ [press Enter to keep current]}: " reply
        echo >&2
    else
        read -r -p "$1${2:+ [$2]}: " reply
    fi
    printf '%s' "${reply:-$2}"
}

# env_line KEY VALUE: KEY=VALUE, or a comment if your shell already sets KEY.
env_line() {
    if from_shell "$1"; then
        echo "# $1 is set by your shell environment, which takes priority over this file."
        echo "$1="
    else
        echo "$1=$2"
    fi
}

write_env_file() {
    umask 077
    cat > "$ENV_FILE" << EOF
# Weekly Photo Selector settings. select_and_print_photos.py reads this file on
# every run (including the scheduled one), and these values override config.json.
# Edit it directly or re-run ./setup_photo_selector.sh --configure.
# Values need no quotes. Empty values are ignored. Variables exported by your
# shell (e.g. in ~/.bash_profile) take priority over this file.

# Where photos come from: synology (Synology Photos on the NAS) or amazon (Amazon Photos)
$(env_line PHOTO_SELECTOR_SOURCE "$SOURCE")

# Amazon Photos sign-in cookies, copied from a browser signed in at amazon.com/photos
# (Developer Tools > Application > Cookies). Anyone with these can use your Amazon
# account, so keep this file private.
# Region: com for amazon.com; otherwise the cookie suffix, e.g. ca for at-acbca.
$(env_line AMAZON_PHOTOS_REGION "$REGION")
$(env_line AMAZON_PHOTOS_SESSION_ID "$SESSION_ID")
$(env_line AMAZON_PHOTOS_UBID "$UBID")
$(env_line AMAZON_PHOTOS_AT "$AT")

# Synology Photos folders on the mounted NAS, separated by ':'
$(env_line SYNOLOGY_PHOTO_DIRS "$SYNOLOGY_DIRS")

# CUPS printer queue; empty uses printer_name from config.json
$(env_line PHOTO_SELECTOR_PRINTER "$PRINTER")
EOF
    chmod 600 "$ENV_FILE"
}

# Value of KEY from your shell if exported there, else from the env file.
current() { if from_shell "$1"; then printf '%s' "${!1}"; else env_get "$1"; fi; }

load_env_values() {
    SOURCE="$(current PHOTO_SELECTOR_SOURCE)"; SOURCE="${SOURCE:-synology}"
    REGION="$(current AMAZON_PHOTOS_REGION)"; REGION="${REGION:-com}"
    SESSION_ID="$(current AMAZON_PHOTOS_SESSION_ID)"
    UBID="$(current AMAZON_PHOTOS_UBID)"
    AT="$(current AMAZON_PHOTOS_AT)"
    SYNOLOGY_DIRS="$(current SYNOLOGY_PHOTO_DIRS)"; SYNOLOGY_DIRS="${SYNOLOGY_DIRS:-$DEFAULT_SYNOLOGY_DIRS}"
    PRINTER="$(current PHOTO_SELECTOR_PRINTER)"
}

# ask_var VAR PROMPT DEFAULT [secret]: like ask, but uses VAR from your shell without asking.
ask_var() {
    if from_shell "$1"; then
        echo "   Using $1 from your shell environment" >&2
        printf '%s' "${!1}"
    else
        ask "$2" "$3" "${4:-}"
    fi
}

configure_sources() {
    load_env_values
    echo ""
    echo "📸 Photo source settings (saved to $ENV_FILE)"
    while :; do
        SOURCE="$(ask_var PHOTO_SELECTOR_SOURCE "Photo source, synology or amazon" "$SOURCE" | tr '[:upper:]' '[:lower:]')"
        case "$SOURCE" in amazon|synology) break ;; esac
        if from_shell PHOTO_SELECTOR_SOURCE; then
            echo "   ❌ PHOTO_SELECTOR_SOURCE in your shell must be synology or amazon." >&2
            exit 1
        fi
        echo "   Please type synology or amazon."
    done

    if [ "$SOURCE" = amazon ]; then
        echo ""
        echo "   Sign in at https://www.amazon.com/photos (or your regional site), open the"
        echo "   browser's Developer Tools > Application > Cookies, and copy the values below."
        REGION="$(ask_var AMAZON_PHOTOS_REGION "Amazon region (com, or the cookie suffix such as ca, uk, de)" "$REGION")"
        local suffix=main
        [ "$REGION" = com ] || suffix="acb$REGION"
        SESSION_ID="$(ask_var AMAZON_PHOTOS_SESSION_ID "session-id cookie" "$SESSION_ID")"
        UBID="$(ask_var AMAZON_PHOTOS_UBID "ubid-$suffix cookie" "$UBID")"
        AT="$(ask_var AMAZON_PHOTOS_AT "at-$suffix cookie (input hidden)" "$AT" secret)"
        if [ -z "$SESSION_ID" ] || [ -z "$UBID" ] || [ -z "$AT" ]; then
            echo "   ⚠️  Some Amazon cookies are empty; the Amazon source won't work until they're set."
        fi
    else
        echo ""
        SYNOLOGY_DIRS="$(ask_var SYNOLOGY_PHOTO_DIRS "Synology Photos folders, separated by ':'" "$SYNOLOGY_DIRS")"
    fi

    write_env_file
    echo "📝 Saved $ENV_FILE"
}

if [ "${1:-}" = "--configure" ]; then
    mkdir -p "$SYSTEM_DIR"
    configure_sources
    exit 0
elif [ -n "${1:-}" ]; then
    echo "Usage: $0 [--configure]" >&2
    exit 2
fi

echo "🖼️  Setting up Weekly Photo Selector System..."

mkdir -p "$SYSTEM_DIR/selections_metadata" "$SYSTEM_DIR/logs"
cp "$SCRIPT_DIR/select_and_print_photos.py" \
   "$SCRIPT_DIR/ollama_client.py" \
   "$SCRIPT_DIR/photo_sources.py" \
   "$SCRIPT_DIR/test_photo_rating.py" \
   "$SCRIPT_DIR/requirements.txt" \
   "$SYSTEM_DIR/"
echo "📋 Copied scripts to $SYSTEM_DIR"

# Write a starter config only if there isn't one, so re-running setup keeps your settings.
if [ ! -f "$SYSTEM_DIR/config.json" ]; then
    cat > "$SYSTEM_DIR/config.json" << 'EOF'
{
  "max_photos_to_select": 5,
  "print_options": {"media": "na_index-4x6_4x6in"}
}
EOF
    echo "📝 Created $SYSTEM_DIR/config.json"
else
    echo "📝 Keeping existing $SYSTEM_DIR/config.json"
fi

if [ -f "$ENV_FILE" ]; then
    echo "📝 Keeping existing $ENV_FILE (change it with --configure)"
elif [ -t 0 ]; then
    configure_sources
else
    load_env_values
    write_env_file
    echo "📝 Created $ENV_FILE; fill in the Amazon cookies or run --configure"
fi

echo "🐍 Creating virtualenv and installing Python dependencies..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SYSTEM_DIR/requirements.txt"

echo "🤖 Checking Ollama..."
if ! command -v ollama > /dev/null; then
    echo "❌ Ollama is not installed. Install it with: brew install ollama"
    echo "   Then re-run this script."
    exit 1
fi
if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
    echo "   Starting Ollama..."
    ollama serve > "$SYSTEM_DIR/logs/ollama.log" 2>&1 &
    for _ in $(seq 1 15); do
        curl -sf http://localhost:11434/api/tags > /dev/null && break
        sleep 1
    done
fi
if ! ollama list | grep -q "^${VISION_MODEL%:latest}"; then
    echo "📥 Downloading $VISION_MODEL (several GB)..."
    ollama pull "$VISION_MODEL"
fi

# Runner used by launchd and for manual runs. Pass --test to skip printing.
cat > "$SYSTEM_DIR/run_weekly_selection.sh" << 'EOF'
#!/bin/bash
# launchd doesn't read shell startup files. Load bash's, as a login shell
# would, so variables exported there (PHOTO_SELECTOR_SOURCE, AMAZON_PHOTOS_*,
# SYNOLOGY_PHOTO_DIRS, ...) apply to scheduled runs too. They take priority
# over photo-selector.env. Set PHOTO_SELECTOR_NO_PROFILE=1 to skip this.
if [ -z "${PHOTO_SELECTOR_NO_PROFILE:-}" ]; then
    for profile in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
        if [ -f "$profile" ]; then
            source "$profile" > /dev/null 2>&1 || true
            break
        fi
    done
    [ -f "$HOME/.bashrc" ] && { source "$HOME/.bashrc" > /dev/null 2>&1 || true; }
    # Your shared variables file. Set PHOTO_SELECTOR_VARIABLES_FILE in a file above
    # if it lives somewhere else.
    VARIABLES_FILE="${PHOTO_SELECTOR_VARIABLES_FILE:-$HOME/Dropbox/variables.sh}"
    if [ -f "$VARIABLES_FILE" ]; then
        set -a  # export plain NAME=value assignments too
        source "$VARIABLES_FILE" > /dev/null 2>&1 || echo "Warning: errors while loading $VARIABLES_FILE"
        set +a
    fi
fi

# launchd has a minimal PATH; include Homebrew on both Apple Silicon and Intel.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH:/usr/bin:/bin"
SYSTEM_DIR="$HOME/weekly-photo-selector"
cd "$SYSTEM_DIR" || exit 1

echo "=== Starting weekly photo selection at $(date)"

if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
    echo "Starting Ollama..."
    ollama serve >> "$SYSTEM_DIR/logs/ollama.log" 2>&1 &
    for _ in $(seq 1 30); do
        curl -sf http://localhost:11434/api/tags > /dev/null && break
        sleep 1
    done
fi

"$SYSTEM_DIR/venv/bin/python" select_and_print_photos.py "$@"
status=$?
echo "=== Finished at $(date) with exit code $status"
exit $status
EOF
chmod +x "$SYSTEM_DIR/run_weekly_selection.sh"

cat > "$SYSTEM_DIR/test_selection.sh" << 'EOF'
#!/bin/bash
# Run the full selection without printing.
exec "$HOME/weekly-photo-selector/run_weekly_selection.sh" --test
EOF
chmod +x "$SYSTEM_DIR/test_selection.sh"
echo "📋 Created run_weekly_selection.sh and test_selection.sh"

# Remove the cron entry older versions of this script installed.
if crontab -l 2>/dev/null | grep -q "run_weekly_selection.sh"; then
    { crontab -l 2>/dev/null | grep -v "run_weekly_selection.sh" || true; } | crontab -
    echo "🧹 Removed old cron entry (replaced by launchd)"
fi

# launchd runs a missed job when the Mac wakes, unlike cron.
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SYSTEM_DIR/run_weekly_selection.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>22</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$SYSTEM_DIR/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$SYSTEM_DIR/logs/launchd.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "⏰ Scheduled with launchd: Sundays at 10:00 PM local time"

if lpstat -p 2>/dev/null | grep -qi canon; then
    echo "🖨️  A Canon printer is configured. Run ./setup_canon_printer.sh to link it to the selector."
else
    echo "🖨️  No printer configured yet. Run ./setup_canon_printer.sh next."
fi

echo ""
echo "✅ Setup completed!"
echo "   • Installed in:      $SYSTEM_DIR"
echo "   • Settings:          $SYSTEM_DIR/config.json"
echo "   • Photo source:      $ENV_FILE"
echo "   • Logs:              $SYSTEM_DIR/logs/"
echo "   • Selection history: $SYSTEM_DIR/selections_metadata/"
echo ""
echo "Next steps:"
echo "   1. ./setup_canon_printer.sh"
echo "   2. $SYSTEM_DIR/venv/bin/python $SYSTEM_DIR/test_photo_rating.py"
echo "   3. $SYSTEM_DIR/test_selection.sh"
echo ""
load_env_values
echo "📸 Photo source: $SOURCE. To change it (or refresh Amazon cookies), run"
echo "   ./setup_photo_selector.sh --configure, edit $ENV_FILE,"
echo "   or export the variables in your shell (e.g. ~/.bash_profile)."
if [ "$SOURCE" = amazon ] && { [ -z "$SESSION_ID" ] || [ -z "$UBID" ] || [ -z "$AT" ]; }; then
    echo "   ⚠️  The Amazon cookies aren't set yet, so the weekly run will fail until they are."
fi
if [ "$SOURCE" = synology ]; then
    echo "   The NAS share must be mounted at ~/nas-home when the job runs. If the scan"
    echo "   can't read it, give /bin/bash Full Disk Access in System Settings >"
    echo "   Privacy & Security."
fi
