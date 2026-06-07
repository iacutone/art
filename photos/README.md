# Weekly Photo Selector & Printer

An AI-powered system that automatically selects the best photos from your Synology NAS each week and prints them directly on your Canon PIXMA G620.

## System Overview

This system uses computer vision AI to:
1. **Scan** your Synology photo directories for pictures from the past week
2. **Analyze** each photo for technical quality and emotional impact
3. **Select** the top 5 photos based on AI ratings
4. **Print** them directly from the NAS every Sunday at 10 PM EST

**Key Feature**: Photos are printed directly from your Synology NAS without copying to local storage, saving disk space and maintaining organization.

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

### Family Photo Customization
Adjust family photo selection behavior by editing these settings in `select_and_print_photos.py`:

```python
# Family Photo Rating Configuration
FAMILY_PHOTO_FOCUS = True      # Enable family-focused rating (vs general photos)
MIN_FAMILY_SCORE = 6           # Minimum family content score (1-10)
PREFER_MULTIPLE_PEOPLE = True  # Boost scores for group/interaction photos
BOOST_CHILDREN_PHOTOS = True   # Give extra points to photos with children
MAX_PHOTOS_TO_SELECT = 5       # Number of photos to print each week
```

**Customization Options:**
- **Turn off family focus**: Set `FAMILY_PHOTO_FOCUS = False` for general photo selection
- **Stricter family filtering**: Increase `MIN_FAMILY_SCORE` to 7 or 8
- **More photos**: Increase `MAX_PHOTOS_TO_SELECT` to 7 or 10
- **Disable boosts**: Set boost options to `False` for pure AI scoring

### Selection Criteria
The AI evaluates each photo on a **1-10 scale** optimized for **family memories**:

**Primary Focus (Family Photos):**
- **Family content** (clear faces, especially children)
- **Emotional significance** (genuine moments, milestones, celebrations)
- **Memory worthiness** (will this be treasured in 5-10 years?)
- **Print quality** (good focus and lighting on faces)

**Scoring Priority:**
- **High scores (7-10)**: Clear family photos, emotional moments, special occasions
- **Medium scores (5-6)**: Decent family photos with minor technical issues
- **Low scores (1-4)**: Non-family content, blurry faces, screenshots, generic landscapes

**Smart Boosting:**
- **+1 point** for photos with multiple family members (interactions)
- **+1 point** for photos featuring children
- **Minimum family score threshold**: Photos must score ≥6 on family content

**Selection process:**
1. Scans Synology directories for images from the past week
2. Rates each photo using family-focused AI criteria
3. Applies smart scoring boosts for family interactions and children
4. Selects **top 5 highest-scoring family photos** for printing
5. Saves selection metadata with detailed reasoning

**Output naming:** Selection metadata saved as `selection_YYYYMMDD_HHMMSS.json`
**Storage efficiency:** Photos remain on Synology NAS, only metadata stored locally

## File Structure

```
~/weekly-photo-selector/
├── select_and_print_photos.py  # Main selection script
├── run_weekly_selection.sh     # Cron job runner
├── test_selection.sh           # Manual test runner
├── selections_metadata/        # Selection history (JSON files only)
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