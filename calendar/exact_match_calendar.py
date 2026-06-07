#!/usr/bin/env python3
"""
Exact Match Linear Calendar Generator
Creates a calendar that precisely matches the reference image style:
- Each row is a month
- Each column is a day (1-31)
- Alternating light gray backgrounds for visual separation
- Clean, minimal typography

Usage: python3 exact_match_calendar.py [YEAR]
If no year is provided, uses the current year.
"""

import calendar
import sys
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, Color

# Colors matching the reference image
white = Color(1, 1, 1)
very_light_gray = Color(0.97, 0.97, 0.97)  # Almost white background
light_gray = Color(0.93, 0.93, 0.93)       # Slightly darker alternating background
line_gray = Color(0.85, 0.85, 0.85)        # Grid lines
text_black = Color(0, 0, 0)                 # Text color

def create_exact_match_calendar(year=None):
    # Use provided year or current year
    if year is None:
        year = datetime.now().year
    
    # Large format for wall printing
    page_width = 48 * inch
    page_height = 36 * inch
    
    filename = f"exact_match_calendar_{year}.pdf"
    c = canvas.Canvas(filename, pagesize=(page_width, page_height))
    months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
              'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    # Layout settings to match reference
    margin = 0.75 * inch
    title_height = 1.4 * inch  # Slightly more space for title
    available_width = page_width - 2 * margin
    available_height = page_height - title_height - 2 * margin
    
    # Grid dimensions
    month_label_width = 0.8 * inch  # Slightly wider for better centering
    days_columns = 31  # Show columns 1-31
    day_column_width = (available_width - month_label_width) / days_columns
    month_row_height = available_height / 12
    
    # Year title (centered, bold)
    c.setFont("Helvetica-Bold", 60)
    c.setFillColor(text_black)
    title_text = str(year)
    title_width = c.stringWidth(title_text, "Helvetica-Bold", 60)
    c.drawString((page_width - title_width) / 2, page_height - margin - 70, title_text)
    
    # Grid starting position
    grid_x = margin
    grid_y = page_height - margin - title_height
    
    # Draw the calendar
    for month_idx, month_name in enumerate(months):
        month_num = month_idx + 1
        row_y_top = grid_y - (month_idx * month_row_height)
        row_y_bottom = row_y_top - month_row_height
        
        # Alternate row background colors for visual separation
        if month_idx % 2 == 1:  # Odd months get light gray background
            c.setFillColor(very_light_gray)
            c.rect(grid_x, row_y_bottom, available_width, month_row_height, fill=1, stroke=0)
        
        # Month label (centered in the month label column)
        c.setFont("Helvetica-Bold", 18)  # Slightly larger and bold
        c.setFillColor(Color(0.2, 0.2, 0.2))  # Dark gray for better hierarchy
        month_name_width = c.stringWidth(month_name, "Helvetica-Bold", 18)
        label_x = grid_x + (month_label_width - month_name_width) / 2  # Center horizontally
        label_y = row_y_top - month_row_height / 2 - 9  # Vertically centered
        c.drawString(label_x, label_y, month_name)
        
        # Get days in this month and first day of the month
        days_in_month = calendar.monthrange(year, month_num)[1]
        first_weekday = calendar.monthrange(year, month_num)[0]  # 0=Monday, 6=Sunday
        
        # Day of week abbreviations
        weekday_abbrev = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
        
        # Draw vertical lines between all day columns first
        c.setStrokeColor(Color(0.9, 0.9, 0.9))  # Very light gray for day separators
        c.setLineWidth(0.5)
        for day in range(1, 32):  # Draw lines for all 31 possible days
            day_x = grid_x + month_label_width + day * day_column_width
            c.line(day_x, row_y_top, day_x, row_y_bottom)
        
        # Draw day numbers and weekday abbreviations
        c.setFont("Helvetica-Bold", 11)  # Bold for day numbers
        for day in range(1, days_in_month + 1):
            day_x = grid_x + month_label_width + (day - 1) * day_column_width
            
            # Calculate weekday for this day (0=Monday, 6=Sunday)
            weekday = (first_weekday + day - 1) % 7
            weekday_letter = weekday_abbrev[weekday]
            
            # Highlight weekends with subtle background
            if weekday >= 5:  # Saturday and Sunday
                c.setFillColor(Color(0.98, 0.95, 0.95))  # Very light pink/red tint
                c.rect(day_x, row_y_bottom, day_column_width, month_row_height, fill=1, stroke=0)
            
            # Draw day number in top-left of box
            c.setFillColor(text_black)
            day_str = str(day)
            text_x = day_x + 4  # Small padding from left edge
            text_y = row_y_top - 16  # From top of box
            c.drawString(text_x, text_y, day_str)
            
            # Draw weekday abbreviation below day number
            c.setFont("Helvetica", 8)  # Smaller font for weekday
            c.setFillColor(Color(0.6, 0.6, 0.6))  # Medium gray for weekday
            weekday_y = text_y - 11  # Below the day number
            c.drawString(text_x, weekday_y, weekday_letter)
            
            # Reset font and color for next iteration
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(text_black)
        
        # Draw horizontal line between months
        c.setStrokeColor(line_gray)
        c.setLineWidth(0.5)
        c.line(grid_x, row_y_bottom, grid_x + available_width, row_y_bottom)
    
    # Draw outer border
    c.setStrokeColor(line_gray)
    c.setLineWidth(1)
    # Top line
    c.line(grid_x, grid_y, grid_x + available_width, grid_y)
    # Left line  
    c.line(grid_x, grid_y, grid_x, grid_y - 12 * month_row_height)
    # Right line
    c.line(grid_x + available_width, grid_y, 
           grid_x + available_width, grid_y - 12 * month_row_height)
    
    # Vertical line separating month labels from calendar
    c.line(grid_x + month_label_width, grid_y,
           grid_x + month_label_width, grid_y - 12 * month_row_height)
    
    # Minimal footer
    c.setFont("Helvetica", 8)
    c.setFillColor(Color(0.6, 0.6, 0.6))
    footer_text = "www.staples.com/services/printing/engineering-blueprints"
    c.drawString(grid_x, margin / 4, footer_text)
    
    c.save()
    print(f"Calendar for {year} saved as {filename}")
    print(f"Style: Precise replica of reference image")
    print(f"Features: Alternating row backgrounds, clean grid, minimal design")
    print(f"Ready for large format printing!")
    
    return filename

if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            year = int(sys.argv[1])
            if year < 1900 or year > 2100:
                print("Error: Year must be between 1900 and 2100")
                sys.exit(1)
        except ValueError:
            print("Error: Year must be a valid integer")
            print("Usage: python3 exact_match_calendar.py [YEAR]")
            sys.exit(1)
    else:
        year = datetime.now().year
        print(f"No year specified, using current year: {year}")
    
    create_exact_match_calendar(year)