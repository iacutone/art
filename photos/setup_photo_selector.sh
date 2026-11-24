#!/bin/bash
# Weekly Photo Selector setup: installs the scripts into ~/weekly-photo-selector,
# creates a Python virtualenv, pulls a vision model and schedules the weekly
# run with launchd (Sundays at 10 PM local time).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEM_DIR="$HOME/weekly-photo-selector"
VENV="$SYSTEM_DIR/venv"
LABEL="com.weekly-photo-selector"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
VISION_MODEL="llama3.2-vision:latest"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "🖼️  Setting up Weekly Photo Selector System..."

mkdir -p "$SYSTEM_DIR/selections_metadata" "$SYSTEM_DIR/logs"
cp "$SCRIPT_DIR/select_and_print_photos.py" \
   "$SCRIPT_DIR/ollama_client.py" \
   "$SCRIPT_DIR/test_photo_rating.py" \
   "$SCRIPT_DIR/requirements.txt" \
   "$SYSTEM_DIR/"
echo "📋 Copied scripts to $SYSTEM_DIR"

# Write a starter config only if there isn't one, so re-running setup keeps your settings.
if [ ! -f "$SYSTEM_DIR/config.json" ]; then
    cat > "$SYSTEM_DIR/config.json" << 'EOF'
{
  "photo_dirs": ["~/nas-home/Photos/MobileBackup", "~/nas-home/Photos/phockup"],
  "max_photos_to_select": 5,
  "print_options": {"media": "na_index-4x6_4x6in"}
}
EOF
    echo "📝 Created $SYSTEM_DIR/config.json"
else
    echo "📝 Keeping existing $SYSTEM_DIR/config.json"
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
# launchd has a minimal PATH; include Homebrew on both Apple Silicon and Intel.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
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
echo "   • Logs:              $SYSTEM_DIR/logs/"
echo "   • Selection history: $SYSTEM_DIR/selections_metadata/"
echo ""
echo "Next steps:"
echo "   1. ./setup_canon_printer.sh"
echo "   2. $SYSTEM_DIR/venv/bin/python $SYSTEM_DIR/test_photo_rating.py"
echo "   3. $SYSTEM_DIR/test_selection.sh"
echo ""
echo "⚠️  The NAS share must be mounted at ~/nas-home when the job runs."
echo "   If the scan can't read it, give /bin/bash Full Disk Access in"
echo "   System Settings > Privacy & Security."
