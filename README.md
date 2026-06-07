# Art & Creative Projects

A collection of personal automation tools for creative projects and life organization.

## Projects

### 📅 [Calendar Generator](./calendar/)
Creates professional wall calendars for printing
- **Script**: `exact_match_calendar.py`
- **Output**: Large format PDF (48" × 36")
- **Use case**: Wall-mounted yearly calendar with clean design

### 🙏 [Gratitude Journal](./gratitude/)
Transforms Org-mode journal entries into book-ready format
- **Parser**: `parse_journal.pl` - Converts structured entries to clean text
- **Styling**: `book-style.css` - 6" × 9" book formatting
- **Use case**: Creating physical books from digital gratitude journals

### 📸 [Photo Management](./photos/)
AI-powered weekly photo selection and printing system
- **Main system**: `select_and_print_photos.py` - AI photo curation
- **Setup scripts**: Automated installation and printer configuration
- **Use case**: Automatically print best photos weekly on Canon PIXMA G620

## Quick Start

Each project has its own README with detailed instructions. For a quick overview:

```bash
# Generate calendar for current year
cd calendar && python3 exact_match_calendar.py

# Convert journal entries to book format
cd gratitude && ./parse_journal.pl < journal.org > formatted.txt

# Set up automated photo printing
cd photos && ./setup_photo_selector.sh
```

## Philosophy

These tools follow a "set it and forget it" approach - minimal ongoing maintenance with maximum creative output. They're designed to handle the technical details so you can focus on the creative and meaningful aspects of life documentation.