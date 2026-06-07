#!/bin/bash

# Weekly Photo Selector Setup Script
# This script sets up the automated photo selection and printing system

set -e

echo "🖼️  Setting up Weekly Photo Selector System..."

# Create directories
SYSTEM_DIR="$HOME/weekly-photo-selector"
mkdir -p "$SYSTEM_DIR/selected_photos"
mkdir -p "$SYSTEM_DIR/logs"

echo "📁 Created system directories in $SYSTEM_DIR"

# Copy script to system directory
cp select_and_print_photos.py "$SYSTEM_DIR/"
cp requirements.txt "$SYSTEM_DIR/"
chmod +x "$SYSTEM_DIR/select_and_print_photos.py"

echo "📋 Copied scripts to system directory"

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip3 install -r requirements.txt

# Check if Ollama is running
echo "🤖 Checking Ollama service..."
if ! pgrep -x "ollama" > /dev/null; then
    echo "⚠️  Ollama is not running. Starting Ollama service..."
    ollama serve &
    sleep 5
fi

# Verify Ollama model is available
echo "🧠 Verifying Ollama model availability..."
if ! ollama list | grep -q "llama3.2:latest"; then
    echo "📥 Downloading llama3.2:latest model for vision capabilities..."
    ollama pull llama3.2-vision:latest || ollama pull llama3.2:latest
fi

# Check printer setup
echo "🖨️  Checking printer setup..."
if lpstat -p | grep -q "Canon"; then
    echo "✅ Canon printer found"
    PRINTER_NAME=$(lpstat -p | grep Canon | head -n1 | awk '{print $2}')
    echo "Detected printer: $PRINTER_NAME"
    
    # Update the printer name in the script
    sed -i.bak "s/PRINTER_NAME = \"Canon_PIXMA_G620\"/PRINTER_NAME = \"$PRINTER_NAME\"/" "$SYSTEM_DIR/select_and_print_photos.py"
else
    echo "ℹ️  Canon PIXMA G620 not found (not yet purchased)"
    echo "The system will work in selection mode and save photos to the output directory."
    echo "After you get your printer, run the printer setup script to enable printing."
fi

# Create the cron job script
cat > "$SYSTEM_DIR/run_weekly_selection.sh" << 'EOF'
#!/bin/bash

# Weekly Photo Selection Cron Job Runner
# Runs every Sunday at 10 PM EST

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Set timezone to EST
export TZ="America/New_York"

# Log file with timestamp
LOG_FILE="$HOME/weekly-photo-selector/logs/cron_$(date +%Y%m%d_%H%M%S).log"

echo "Starting weekly photo selection at $(date)" >> "$LOG_FILE"

# Ensure Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama service..." >> "$LOG_FILE"
    ollama serve >> "$LOG_FILE" 2>&1 &
    sleep 10
fi

# Run the photo selection script
cd "$HOME/weekly-photo-selector"
python3 select_and_print_photos.py >> "$LOG_FILE" 2>&1

echo "Completed weekly photo selection at $(date)" >> "$LOG_FILE"
EOF

chmod +x "$SYSTEM_DIR/run_weekly_selection.sh"

echo "📅 Created cron job runner script"

# Create the cron job entry
CRON_ENTRY="0 22 * * 0 $SYSTEM_DIR/run_weekly_selection.sh"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "run_weekly_selection.sh"; then
    echo "⚠️  Cron job already exists"
else
    # Add cron job
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "⏰ Added cron job: Every Sunday at 10:00 PM EST"
fi

# Create a test runner script
cat > "$SYSTEM_DIR/test_selection.sh" << 'EOF'
#!/bin/bash

# Test script to run photo selection manually
echo "🧪 Running photo selection test..."

cd "$HOME/weekly-photo-selector"

# Ensure Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama service..."
    ollama serve &
    sleep 10
fi

# Run with test mode (don't actually print)
python3 select_and_print_photos.py --test
EOF

chmod +x "$SYSTEM_DIR/test_selection.sh"

echo "✅ Setup completed successfully!"
echo ""
echo "📋 Summary:"
echo "   • System installed in: $SYSTEM_DIR"
echo "   • Cron job scheduled: Every Sunday at 10:00 PM EST"
echo "   • Log files saved in: $SYSTEM_DIR/logs/"
echo "   • Selected photos saved in: $SYSTEM_DIR/selected_photos/"
echo ""
echo "🧪 To test the system manually, run:"
echo "   $SYSTEM_DIR/test_selection.sh"
echo ""
echo "📝 To view/edit cron jobs:"
echo "   crontab -e"
echo ""
echo "📊 To view logs:"
echo "   tail -f $SYSTEM_DIR/logs/*.log"