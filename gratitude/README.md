# Gratitude Journal Parser

A Perl script that transforms Org-mode journal entries into beautifully formatted book-style output.

## What it does

Converts structured journal entries from this format:
```
*** 2024-01-15 Monday
**** ENTRY
One: Something I'm grateful for
Two: Another thing I'm grateful for  
Three: A third thing I'm grateful for
  :LOGBOOK:
  - Added: [2024-01-15 Mon 20:30]
  :END:
```

Into this clean format:
```
*** Monday, January 15 — 20:30

One: Something I'm grateful for

Two: Another thing I'm grateful for

Three: A third thing I'm grateful for
```

## Usage

```bash
./parse_journal.pl < your_journal.org > formatted_output.txt
```

Or pipe from standard input:
```bash
cat journal_entries.org | ./parse_journal.pl > clean_journal.txt
```

## PDF Generation

Create a print-ready PDF book from your journal entries:

### Method 1: Using Docker + Pandoc (Recommended)
```bash
# Parse journal entries first
./parse_journal.pl < journal.org > clean_journal.org

# Convert to PDF using Docker
docker run --rm \
  --platform linux/amd64 \
  -v "$(pwd):/data" \
  --user $(id -u):$(id -g) \
  pandoc/extra clean_journal.org -o final_book.pdf --css=book-style.css
```

### Method 2: Local Pandoc (if available)
```bash
# Parse and convert to PDF in one step
./parse_journal.pl < journal.org | pandoc -f markdown -t html --css=book-style.css -o clean_journal.pdf --pdf-engine=wkhtmltopdf
```

### Method 3: Manual HTML conversion
```bash
# Step-by-step process
./parse_journal.pl < journal.org > formatted.txt
# Convert to HTML with your preferred processor
# Apply book-style.css
# Generate PDF using browser print or HTML-to-PDF tool
```

### Dependencies for PDF generation
```bash
# For Docker method (recommended)
# Requires Docker Desktop to be installed and running

# For local method
brew install pandoc wkhtmltopdf
```

The output PDF will be formatted as a 6" × 9" book ready for printing.

## CSS Styling Features

- **6" × 9" book format** with proper binding margins
- **Georgia serif font** for readability
- **Chapter pages** for years
- **Elegant headers** for months
- **Clean date formatting** with underlines
- **Traditional paragraph indentation**

## Dependencies

- Perl (standard on macOS/Linux)
- For PDF generation (Docker method): Docker Desktop
- For PDF generation (local method): `pandoc` and `wkhtmltopdf`
  ```bash
  brew install pandoc wkhtmltopdf
  ```