#!/usr/bin/env perl
use strict;
use warnings;

my ($year, $mo_num, $day_num, $weekday, $entry_text, $time, $mo_name);
my %months = (
    '01'=>'January', '02'=>'February', '03'=>'March', '04'=>'April',
    '05'=>'May',     '06'=>'June',     '07'=>'July',  '08'=>'August',
    '09'=>'September','10'=>'October',  '11'=>'November','12'=>'December'
);

# Slurp the entire file into memory
undef $/;
my $content = <>;

# Clean the Month headers
$content =~ s/^\*\* \d{4}-\d{2} /** /gm;

# Use curly braces s{...}{...}gexs for safe multi-line execution
$content =~ s{
    \*\*\*\s+(\d{4})-(\d{2})-(\d{2})\s+(\w+)\n   # $1=Year, $2=Month Num, $3=Day Num, $4=Weekday
    \*\*\*\*\s+ENTRY\s*\n                         # Matches the literal **** ENTRY line
    (.*?)                                         # $5 = Everything inside the entry
    \s*:\s*LOGBOOK:\s*\n                          # Handles flexible leading indentation
    \s*-\s*Added:\s*\[\d{4}-\d{2}-\d{2}\s+\w+\s+(\d{2}:\d{2})\]\s*\n # $6 = Time (HH:MM)
    \s*:\s*END:
}{
    ($year, $mo_num, $day_num, $weekday, $entry_text, $time) = ($1, $2, $3, $4, $5, $6);
    
    $mo_name = $months{$mo_num} // "Month";
    
    my $new_heading = "*** $weekday, $mo_name $day_num — $time";
    
    # Clean up white spaces and split One:, Two:, Three: into distinct paragraphs
    $entry_text =~ s/^\s+|\s+$//g; 
    $entry_text =~ s/\s*One:/\nOne:/g;
    $entry_text =~ s/\s*Two:/\n\nTwo:/g;
    $entry_text =~ s/\s*Three:/\n\nThree:/g;
    
    "$new_heading\n\n$entry_text\n"
}gexs;

print $content;
