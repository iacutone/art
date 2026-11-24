#!/bin/bash
# Canon PIXMA G620 printer setup.
#
# Finds the printer (already-configured queue, or on the network via Bonjour),
# adds it as an AirPrint/IPP Everywhere queue if needed, and saves the queue
# name to ~/weekly-photo-selector/config.json.
#
# Note: the G620 advertises itself on the network as "Canon G600 series".
#
#   ./setup_canon_printer.sh              # auto-detect
#   ./setup_canon_printer.sh <printer-ip> # skip discovery and use this address

set -euo pipefail

SYSTEM_DIR="$HOME/weekly-photo-selector"
CONFIG="$SYSTEM_DIR/config.json"
QUEUE_NAME="Canon_G620"

echo "🖨️  Canon PIXMA G620 Printer Setup"
echo "======================================"

if [ ! -x "$SYSTEM_DIR/venv/bin/python" ]; then
    echo "❌ Photo selector not installed. Run ./setup_photo_selector.sh first."
    exit 1
fi

printer_name=""
printer_uri=""

if [ $# -ge 1 ]; then
    printer_uri="ipp://$1/ipp/print"
else
    # 1. An existing Canon queue?
    existing=$(lpstat -p 2>/dev/null | awk '/^printer/ {print $2}' | grep -i canon || true)
    if [ -n "$existing" ]; then
        count=$(echo "$existing" | wc -l | tr -d ' ')
        if [ "$count" -eq 1 ]; then
            printer_name="$existing"
            echo "✅ Found configured Canon printer: $printer_name"
        else
            echo "Several Canon printers are configured:"
            select choice in $existing; do
                [ -n "$choice" ] && printer_name="$choice" && break
            done
        fi
    else
        # 2. Discover on the network.
        echo "🔍 Searching the network for Canon printers (5s)..."
        found=$(ippfind -T 5 _ipp._tcp --exec echo '{service_name}|{service_uri}' \; 2>/dev/null \
                | grep -i canon | sort -u || true)
        if [ -z "$found" ]; then
            echo "❌ No Canon printer found on the network."
            echo ""
            echo "Check that the printer is on and connected to the same Wi-Fi as this Mac,"
            echo "then re-run this script. If you know its IP address (printer menu:"
            echo "LAN settings > Confirm LAN settings), run:"
            echo "   ./setup_canon_printer.sh <printer-ip>"
            exit 1
        fi
        count=$(echo "$found" | wc -l | tr -d ' ')
        if [ "$count" -eq 1 ]; then
            echo "✅ Found: ${found%%|*}"
            printer_uri="${found#*|}"
        else
            echo "Several Canon printers found:"
            IFS=$'\n'
            select choice in $found; do
                [ -n "$choice" ] && printer_uri="${choice#*|}" && break
            done
            unset IFS
        fi
    fi
fi

# 3. Add a queue if we only have a network address.
if [ -z "$printer_name" ]; then
    echo "➕ Adding printer queue $QUEUE_NAME -> $printer_uri"
    # "everywhere" builds the driver from the printer's own AirPrint/IPP
    # description, so paper sizes and photo quality options are correct.
    if ! lpadmin -p "$QUEUE_NAME" -E -v "$printer_uri" -m everywhere \
            -D "Canon PIXMA G620" -L "Weekly photo selector"; then
        echo "❌ Could not add the printer (the printer may be asleep, or you may need admin rights)."
        echo "   Add it in System Settings > Printers & Scanners instead, then re-run this script."
        exit 1
    fi
    printer_name="$QUEUE_NAME"
fi

# 4. Save the queue name to the selector config.
"$SYSTEM_DIR/venv/bin/python" - "$CONFIG" "$printer_name" << 'EOF'
import json, sys
from pathlib import Path
path, name = Path(sys.argv[1]), sys.argv[2]
config = json.loads(path.read_text()) if path.exists() else {}
config["printer_name"] = name
path.write_text(json.dumps(config, indent=2) + "\n")
EOF
echo "🔧 Saved printer_name=\"$printer_name\" to $CONFIG"

# 5. Status and paper sizes.
echo ""
echo "🧪 Printer status: $(lpstat -p "$printer_name" | head -n1)"
echo ""
echo "📄 Paper sizes this printer supports (set one as print_options.media in config.json,"
echo "   e.g. \"na_index-4x6_4x6in\" for 4x6 photo paper):"
lpoptions -p "$printer_name" -l 2>/dev/null | grep -iE '^(media|PageSize)' | cut -c1-300 || echo "   (not available)"
echo ""

read -r -p "Print a test page now? (y/n): " test_print
if [[ $test_print == [Yy]* ]]; then
    test_page="$(mktemp -t canon_test)"
    cat > "$test_page" << EOF
Canon PIXMA G620 Test Page
Weekly Photo Selector System
============================

If you can read this, the printer is set up correctly.

Queue: $printer_name
Date:  $(date)
EOF
    if lpr -P "$printer_name" -T "Photo selector test page" "$test_page"; then
        echo "✅ Test page sent. Check the printer."
    else
        echo "❌ Failed to send the test page."
    fi
    rm -f "$test_page"
fi

echo ""
echo "✅ Printer setup completed!"
echo "   To test the full system without printing: $SYSTEM_DIR/test_selection.sh"
