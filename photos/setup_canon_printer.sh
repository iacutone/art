#!/bin/bash

# Canon PIXMA G620 Printer Setup Script
# Run this after you've purchased and connected your Canon PIXMA G620

set -e

echo "🖨️  Canon PIXMA G620 Printer Setup"
echo "======================================"

SYSTEM_DIR="$HOME/weekly-photo-selector"

# Check if main system is installed
if [ ! -d "$SYSTEM_DIR" ]; then
    echo "❌ Weekly photo selector system not found. Run setup_photo_selector.sh first."
    exit 1
fi

echo "🔍 Searching for Canon PIXMA G620..."

# Function to detect Canon printer
detect_canon_printer() {
    local printer_name=""
    
    # Check configured printers
    if lpstat -p 2>/dev/null | grep -i canon | grep -i g620; then
        printer_name=$(lpstat -p | grep -i canon | grep -i g620 | head -n1 | awk '{print $2}')
        echo "✅ Found configured Canon PIXMA G620: $printer_name"
        return 0
    fi
    
    # Check for any Canon printer
    if lpstat -p 2>/dev/null | grep -i canon; then
        printer_name=$(lpstat -p | grep -i canon | head -n1 | awk '{print $2}')
        echo "✅ Found Canon printer: $printer_name"
        echo "⚠️  This might be your PIXMA G620, or a different Canon printer."
        read -p "Is this your Canon PIXMA G620? (y/n): " confirm
        if [[ $confirm == [Yy]* ]]; then
            return 0
        fi
    fi
    
    return 1
}

# Try to detect the printer
if detect_canon_printer; then
    # Update the script with the correct printer name
    echo "🔧 Updating photo selector script with printer name: $printer_name"
    sed -i.bak "s/PRINTER_NAME = \"Canon_PIXMA_G620\"/PRINTER_NAME = \"$printer_name\"/" "$SYSTEM_DIR/select_and_print_photos.py"
    echo "✅ Printer configuration updated"
else
    echo "❌ Canon PIXMA G620 not found"
    echo ""
    echo "📋 To add your Canon PIXMA G620:"
    echo "1. Make sure your printer is connected to the same network as your Mac"
    echo "2. Go to System Settings > Printers & Scanners"
    echo "3. Click the '+' button"
    echo "4. Select your Canon PIXMA G620 from the list"
    echo "5. Follow the setup instructions"
    echo ""
    echo "After adding the printer, run this script again."
    exit 1
fi

# Test print functionality
echo "🧪 Testing printer connectivity..."
if lpstat -p "$printer_name" | grep -q "idle"; then
    echo "✅ Printer is ready"
    
    # Offer to do a test print
    read -p "Would you like to do a test print? (y/n): " test_print
    if [[ $test_print == [Yy]* ]]; then
        # Create a simple test page
        cat > /tmp/test_page.txt << 'EOF'
Canon PIXMA G620 Test Page
Weekly Photo Selector System
=========================

This is a test print to verify your Canon PIXMA G620 is working correctly with the weekly photo selector system.

If you can see this page, your printer is configured correctly!

Date: $(date)
EOF
        
        echo "🖨️  Sending test page to printer..."
        lpr -P "$printer_name" /tmp/test_page.txt
        
        if [ $? -eq 0 ]; then
            echo "✅ Test print job sent successfully!"
            echo "Check your printer for the test page."
        else
            echo "❌ Failed to send test print job"
        fi
        
        # Clean up
        rm -f /tmp/test_page.txt
    fi
else
    echo "⚠️  Printer status: $(lpstat -p "$printer_name")"
    echo "Make sure your printer is turned on and ready."
fi

echo ""
echo "✅ Canon PIXMA G620 setup completed!"
echo ""
echo "Your weekly photo selector system is now ready to:"
echo "• Select the best photos from each week using AI"
echo "• Automatically print them every Sunday at 10 PM EST"
echo ""
echo "📊 To test the full system:"
echo "   $SYSTEM_DIR/test_selection.sh"