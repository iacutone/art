# Weekly Photo Selector & Printer

An AI-powered system that finds the best photos from the past week on your Synology NAS and prints them on your Canon PIXMA G620.

## System Overview

Every Sunday evening the system:
1. **Scans** your NAS photo folders for pictures taken during the past week
2. **Rates** each photo with a local Ollama vision model (nothing leaves your network)
3. **Selects** the top photos, skipping bursts and anything already printed
4. **Prints** them on the Canon PIXMA G620

Originals stay on the NAS. The only local copies are a temporary JPEG made for each print job and the selection metadata in `~/weekly-photo-selector/selections_metadata/`.

## Setup

### 1. Install the photo selector

```bash
cd /path/to/this/repo/photos
./setup_photo_selector.sh
```

This will:
- Copy the Python scripts and `requirements.txt` to `~/weekly-photo-selector/`
- Create a virtualenv at `~/weekly-photo-selector/venv` and install the Python dependencies
- Check that Ollama is running (it exits with a message if Ollama isn't installed: `brew install ollama`)
- Pull the `llama3.2-vision` model if it isn't already installed
- Write `run_weekly_selection.sh` and `test_selection.sh`
- Create `~/weekly-photo-selector/config.json` if it doesn't exist (existing settings are kept)
- Install the launchd schedule (see [Automation Schedule](#automation-schedule))

After you change any script in this repo, re-run `./setup_photo_selector.sh`. The scheduled job runs the copies in `~/weekly-photo-selector/`, not the files here.

### 2. Set up the printer

The Canon PIXMA G620 needs to be on, and on the same network as your Mac. It advertises itself as **"Canon G600 series"**.

```bash
./setup_canon_printer.sh              # find the printer automatically
./setup_canon_printer.sh 192.168.1.50 # or give its IP address
```

The script:
- Uses an existing Canon print queue if one is already set up
- Otherwise searches the network with Bonjour (`ippfind`) and adds a queue named **`Canon_G620`** using AirPrint ("everywhere" driver)
- Saves the queue name as `printer_name` in `config.json`
- Lists the paper sizes the printer supports and offers to print a test page

If discovery fails, find the printer's IP on its panel (LAN settings > Confirm LAN settings) and pass it as an argument.

### 3. Check that everything works

```bash
# Check Ollama and the vision model, and rate a test image
~/weekly-photo-selector/venv/bin/python ~/weekly-photo-selector/test_photo_rating.py

# Run the full selection without printing
~/weekly-photo-selector/test_selection.sh
```

## Manual Usage

```bash
# Select and print now
~/weekly-photo-selector/run_weekly_selection.sh

# Select only; nothing is printed and nothing is recorded as printed
~/weekly-photo-selector/test_selection.sh
```

Or run the script directly:

```bash
cd ~/weekly-photo-selector
venv/bin/python select_and_print_photos.py          # select and print
venv/bin/python select_and_print_photos.py --test   # select only
venv/bin/python select_and_print_photos.py --config /path/to/other.json
```

## Configuration

All settings live in **`~/weekly-photo-selector/config.json`**. It is plain JSON. Any key you leave out uses its default, and an unknown key is an error, so check your spelling.

Two environment variables override settings:
- `PHOTO_SELECTOR_CONFIG`: use a different config file
- `PHOTO_SELECTOR_PRINTER`: use a different printer queue name

### Example

```json
{
  "photo_dirs": ["~/nas-home/Photos/MobileBackup", "~/nas-home/Photos/phockup"],
  "max_photos_to_select": 5,
  "print_options": {
    "fit-to-page": "true",
    "print-quality": "5",
    "media": "na_index-4x6_4x6in"
  }
}
```

For `media`, check the values your printer accepts with `lpoptions -p Canon_G620 -l`. The setup script also prints them. Use `"media": null` to leave the paper size to the printer.

### All settings

| Key | Default | Description |
|---|---|---|
| `photo_dirs` | MobileBackup and phockup folders on the NAS | Folders to scan, searched recursively. Missing folders are skipped with a warning. |
| `vision_models` | `["llama3.2-vision:latest", "llava:latest"]` | Models to try, in order. Only installed vision models are used. |
| `ollama_url` | `http://localhost:11434` | Address of the Ollama server. |
| `metadata_dir` | `~/weekly-photo-selector/selections_metadata` | Where selection JSON files and `printed_history.json` are stored. |
| `log_dir` | `~/weekly-photo-selector/logs` | Where `photo_selector.log` is written. |
| `printer_name` | `Canon_G620` | CUPS queue to print to. Set by `setup_canon_printer.sh`; check with `lpstat -p`. |
| `print_options` | `{"fit-to-page": "true", "print-quality": "5", "media": null}` | Passed to `lpr` as `-o key=value`. Keys with `null` values are skipped. |
| `max_photos_to_select` | `5` | How many photos to print each week. |
| `family_photo_focus` | `true` | Rate with the family prompt and apply the family threshold and boosts. `false` uses the general prompt. |
| `min_family_score` | `6` | Photos whose family-content score is below this are never printed. |
| `prefer_multiple_people` | `true` | Add +1 to photos where the model sees two or more people. |
| `boost_children_photos` | `true` | Add +1 to photos where the model sees children. |
| `burst_window_seconds` | `10` | Photos taken within this many seconds of a selected photo are skipped as the same burst. |
| `skip_previously_printed` | `true` | Skip photos already in `printed_history.json`, and photos from the same burst as one. |

## Selection Criteria

**Time window.** The window is the 7 full days ending at midnight tonight. Run on a Sunday, it covers Monday 00:00 through Sunday 23:59, so weekly runs don't overlap or leave gaps. A photo's date comes from EXIF `DateTimeOriginal`, falling back to `DateTimeDigitized`, then `DateTime`, then the file's modification time. Files not modified in the window are skipped without being opened, which keeps network scans fast.

**Formats.** JPEG, PNG, TIFF and HEIC/HEIF. HEIC needs `pillow-heif`, which the setup installs. Without it, HEIC files are skipped with a warning.

**Duplicates.** Exact duplicates across folders are removed by SHA-256 hash.

**Rating.** Each photo is sent to the vision model, which returns JSON with a 1-10 score and the reasons. Photos that fail to rate (unreadable file, model error, or no usable score) are left out. They are never given a default score.

**Family adjustments** (when `family_photo_focus` is on):
- If family content is below `min_family_score`, the photo is excluded, even on a week with fewer than `max_photos_to_select` candidates.
- Otherwise, +1 for two or more people and +1 for children present, depending on the settings above. The score never exceeds 10.

**Choosing.** Rated photos are sorted by score, highest first. Each one is taken unless it falls within `burst_window_seconds` of a photo already chosen or already printed. Selection stops at `max_photos_to_select`.

**Printing.** Each photo is converted to an upright, full-resolution RGB JPEG (EXIF rotation applied) and sent with `lpr`. Only jobs that were queued successfully are recorded in `printed_history.json`, so re-running the same week (e.g. `launchctl kickstart`) retries failed photos without reprinting the rest.

**Output.** Each run writes `selection_YYYYMMDD_HHMMSS.json` to `selections_metadata/`. It lists each selected photo's rank, path, hash, capture time and the model's full rating and reasoning.

### Scoring guide

The family prompt asks the model to judge:
- **Family content**: clear faces (especially children), genuine emotion, interactions, milestones
- **Memory worthiness**: will the photo be treasured in 5-10 years?
- **Print quality**: focus and lighting on faces, composition, no blur or over-exposure

Rough bands: 7-10 for clear, well-lit family moments; 5-6 for decent photos with minor problems; 1-4 for photos without people, screenshots, documents, or generic landscapes and food.

## File Structure

```
~/weekly-photo-selector/
├── select_and_print_photos.py  # Main selection and printing script
├── ollama_client.py            # Ollama API client and image encoding
├── test_photo_rating.py        # Checks Ollama and the rating prompt
├── requirements.txt            # Python dependencies
├── config.json                 # Your settings (see Configuration)
├── run_weekly_selection.sh     # Runner used by launchd and for manual runs
├── test_selection.sh           # Runs the selection with --test (no printing)
├── venv/                       # Python virtualenv
├── selections_metadata/        # Selection JSON files and printed_history.json
└── logs/                       # photo_selector.log, launchd.log, ollama.log
```

## Automation Schedule

- **When**: Sundays at 10:00 PM local time
- **What**: Selects and prints the top photos from the past week
- **Scheduler**: launchd, not cron. The job is defined in `~/Library/LaunchAgents/com.weekly-photo-selector.plist`. If the Mac was asleep at 10 PM, launchd runs the job when it wakes.

Check the schedule:
```bash
launchctl print gui/$(id -u)/com.weekly-photo-selector
```

Run the job now, outside the schedule:
```bash
launchctl kickstart gui/$(id -u)/com.weekly-photo-selector
```

## Dependencies

- **macOS** with CUPS (`lpr`, `lpstat`, `lpadmin`) and `ippfind`
- **Python 3** in the virtualenv: Pillow >= 10, pillow-heif >= 0.16, requests >= 2.31
- **Ollama**, installed with `brew install ollama`. Only vision models are used. The setup pulls `llama3.2-vision`, and text-only models are rejected so they can't invent scores.
- **Synology NAS** mounted at `~/nas-home`
- **Canon PIXMA G620** on the same network

## Troubleshooting

### No photos selected
- Check that the NAS is mounted at `~/nas-home`. A missing folder is logged as "Photo directory does not exist (is the NAS mounted?)".
- Check `photo_dirs` in `config.json` and confirm the photos fall within the past week.
- Check the log for "Could not rate" or "No valid score" lines, which mean the model failed on those photos.

### Scheduled run can't read the NAS
- Under launchd, the job runs `/bin/bash`, which may need permission to reach network volumes. Give `/bin/bash` Full Disk Access in System Settings > Privacy & Security, then run the job with `launchctl kickstart` to check.

### Printer not working
- Check the queue: `lpstat -p` should list `Canon_G620` as idle, not disabled.
- If the queue is missing, re-run `./setup_canon_printer.sh`.
- Check the paper size: `lpoptions -p Canon_G620 -l`, then update `print_options.media`.
- Make sure the printer is awake and on the same network as the Mac.

### AI service issues
- "None of the vision models ... are installed": run `ollama pull llama3.2-vision`, or add an installed vision model to `vision_models`.
- Check that Ollama is up: `curl http://localhost:11434/api/tags`. Start it with `ollama serve` if not.
- Test the model: `~/weekly-photo-selector/venv/bin/python ~/weekly-photo-selector/test_photo_rating.py`
- List installed models: `ollama list`

### HEIC photos skipped
- Re-run `./setup_photo_selector.sh` to install `pillow-heif` into the virtualenv.

## Logs & Monitoring

Follow the logs in real time:
```bash
tail -f ~/weekly-photo-selector/logs/photo_selector.log ~/weekly-photo-selector/logs/launchd.log
```

Each run logs the photos it scanned, rated and selected, the print results, and the exit code. launchd's output (including `run_weekly_selection.sh` start and finish lines) goes to `launchd.log`.
