# Calendar Generator

A Python script that creates precise, wall-mountable calendars for any year.

## Features

- **Large format**: 48" × 36" designed for professional printing
- **Linear layout**: Each row is a month, each column is a day (1-31)
- **Visual clarity**: Alternating gray backgrounds, weekend highlighting
- **Print-ready**: Professional quality PDF output
- **Flexible**: Generate calendar for any year

## Usage

```bash
# Generate calendar for current year
python3 exact_match_calendar.py

# Generate calendar for specific year
python3 exact_match_calendar.py 2026

# Generate calendar for any year (1900-2100)
python3 exact_match_calendar.py 2024
```

This creates `exact_match_calendar_YYYY.pdf` in the current directory.

## Output

- **Format**: PDF suitable for large format printing
- **Layout**: 12 rows (months) × 31 columns (days)
- **Features**: 
  - Year title at top
  - Month abbreviations in left column
  - Day numbers with weekday abbreviations
  - Weekend highlighting in light pink
  - Clean grid lines and typography

## Dependencies

```bash
pip install reportlab
```

## Printing

The PDF is designed for large format printing services like Staples Engineering Prints. The recommended size is 48" × 36" for wall mounting.