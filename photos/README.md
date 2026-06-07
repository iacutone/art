# Weekly Photo Selector & Printer

An AI-powered system that automatically selects the best photos from your collection each week and prints them on your Canon PIXMA G620.

## System Overview

This system uses computer vision AI to:
1. **Scan** your photo directories for pictures from the past week
2. **Analyze** each photo for technical quality and emotional impact
3. **Select** the top 5 photos based on AI ratings
4. **Print** them automatically every Sunday at 10 PM EST

## Setup Instructions

### 1. Initial System Setup

```bash
# Install the photo selection system
./setup_photo_selector.sh
```

This will:
- Install Python dependencies
- Set up Ollama AI service
- Create directory structure
- Schedule weekly cron job

### 2. Printer Setup (when you get your Canon PIXMA G620)

```bash
# Configure your Canon PIXMA G620 printer
./setup_canon_printer.sh
```

This will:
- Detect your Canon printer
- Configure print settings
- Test printing functionality

## Manual Usage

### Test the Selection System
```bash
# Test photo selection without printing
~/weekly-photo-selector/test_selection.sh
```

### Manual Photo Selection & Printing
```bash
# Run the full system manually
cd ~/weekly-photo-selector
python3 select_and_print_photos.py

# Test mode (no actual printing)
python3 select_and_print_photos.py --test
```

### Test AI Vision System
```bash
# Verify Ollama AI is working correctly
python3 test_photo_rating.py
```

## Configuration

### Photo Directories
Edit `select_and_print_photos.py` to change photo source directories:
```python
PHOTO_DIRS = [
    "~/nas-home/Photos/MobileBackup",
    "~/nas-home/Photos/phockup"
]
```

### Selection Criteria
- **Maximum photos per week**: 5 (configurable)
- **Rating scale**: 1-10 based on:
  - Technical quality (focus, exposure, composition)
  - Emotional impact and memorability
  - Print worthiness
  - Uniqueness and interest

## File Structure

```
~/weekly-photo-selector/
├── select_and_print_photos.py  # Main selection script
├── run_weekly_selection.sh     # Cron job runner
├── test_selection.sh           # Manual test runner
├── selected_photos/            # Weekly selections
└── logs/                      # System logs
```

## Automation Schedule

- **When**: Every Sunday at 10:00 PM EST
- **What**: Selects and prints best 5 photos from the past week
- **Logs**: Saved to `~/weekly-photo-selector/logs/`

## Utilities

### `find_canon_printer.sh`
Helps locate your Canon PIXMA G620 on the network:
```bash
./find_canon_printer.sh
```

### `test_photo_rating.py`
Verifies the AI rating system is working:
```bash
python3 test_photo_rating.py
```

## Dependencies

- **Python 3** with PIL (Pillow), requests
- **Ollama** AI service with vision models
- **Canon PIXMA G620** printer (when purchased)
- **macOS** printing system (cups/lpr)

## Troubleshooting

### No Photos Selected
- Check photo directory paths in configuration
- Verify photos exist in the past week's date range
- Check logs for AI service errors

### Printer Not Working
- Run `./find_canon_printer.sh` to locate printer
- Verify printer is connected to same network
- Check printer status: `lpstat -p`

### AI Service Issues
- Restart Ollama: `ollama serve`
- Test with: `python3 test_photo_rating.py`
- Check available models: `ollama list`

## Logs & Monitoring

View real-time logs:
```bash
tail -f ~/weekly-photo-selector/logs/*.log
```

Check cron job status:
```bash
crontab -l
```