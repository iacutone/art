#!/bin/bash

echo "🔍 Searching for Canon PIXMA G620 printer..."

# Check if printer is already configured
if lpstat -p | grep -i canon | grep -i g620; then
    echo "✅ Canon PIXMA G620 found in configured printers"
    exit 0
fi

# Search for network printers
echo "🌐 Scanning for network printers..."

# Use avahi-browse to find network printers (if available)
if command -v avahi-browse &> /dev/null; then
    echo "Scanning with Avahi..."
    avahi-browse -rt _ipp._tcp | grep -i canon
fi

# Use ippfind to discover IPP printers
if command -v ippfind &> /dev/null; then
    echo "Scanning with ippfind..."
    ippfind | grep -i canon
fi

echo ""
echo "📝 To add your Canon PIXMA G620 manually:"
echo "1. Go to System Settings > Printers & Scanners"
echo "2. Click the '+' button to add a printer"
echo "3. Select your Canon PIXMA G620 from the network"
echo ""
echo "Or use the command line:"
echo "lpadmin -p Canon_PIXMA_G620 -E -v ipp://YOUR_PRINTER_IP:631/ipp/print -P /System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/PrintCore.framework/Versions/A/Resources/Generic.ppd"
echo ""
echo "Replace YOUR_PRINTER_IP with your printer's IP address"