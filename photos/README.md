# Weekly Photo Selector & Printer

An AI-powered system that finds the best photos from the past week in **Synology Photos** on your NAS (the default) or **Amazon Photos**, and prints them on your Canon PIXMA G620.

## System Overview

Every Sunday evening the system:
1. **Finds** pictures taken during the past week in your Synology Photos folders on the NAS, or in Amazon Photos
2. **Rates** each photo with a local Ollama vision model (nothing leaves your network)
3. **Selects** the top photos, skipping bursts and anything already printed
4. **Prints** them on the Canon PIXMA G620

Originals are never changed. When the source is Amazon Photos, the week's photos are downloaded to a temporary folder that is deleted when the run ends. The only other local copies are a temporary JPEG made for each print job and the selection metadata in `~/weekly-photo-selector/selections_metadata/`.

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
- Create `~/weekly-photo-selector/photo-selector.env` if it doesn't exist, asking for your photo source settings (see [Choose a photo source](#2-choose-a-photo-source))
- Install the launchd schedule (see [Automation Schedule](#automation-schedule))

After you change any script in this repo, re-run `./setup_photo_selector.sh`. The scheduled job runs the copies in `~/weekly-photo-selector/`, not the files here.

### 2. Choose a photo source

| Source | Value | Needs |
|---|---|---|
| Synology Photos (default) | `synology` | The NAS mounted at `~/nas-home`, and the folders to scan |
| Amazon Photos | `amazon` | Sign-in cookies copied from your browser (see [Amazon Photos sign-in](#amazon-photos-sign-in)) |

The first time you run `./setup_photo_selector.sh`, it asks for these settings. To change them later, for example to switch sources or paste fresh Amazon cookies, run:

```bash
./setup_photo_selector.sh --configure
```

This only rewrites `~/weekly-photo-selector/photo-selector.env` and doesn't reinstall anything.

#### Setting them with environment variables

The settings are environment variables. You can set them in three places. When a variable is set in more than one, the higher one in this list wins:

1. **Your shell.** Export them in `~/Dropbox/variables.sh`, `~/.bash_profile`, `~/.bashrc` or `~/.profile`. The scheduled run loads these files too (`variables.sh` last, so it wins), so it sees the same values as your terminal. `--configure` uses any values your shell already exports without asking, and doesn't copy them into the env file.
2. **`~/weekly-photo-selector/photo-selector.env`**, as `KEY=value` lines. No quotes are needed, even for the Amazon `Atza|...` cookie. The file is created with `chmod 600`.
3. **`config.json`**, see [Configuration](#configuration).

`--source synology` or `--source amazon` on the command line overrides all three for one run.

| Variable | Meaning |
|---|---|
| `PHOTO_SELECTOR_SOURCE` | `synology` (default) or `amazon` |
| `SYNOLOGY_PHOTO_DIRS` | Synology Photos folders, separated by `:`, e.g. `~/nas-home/Photos/MobileBackup:~/nas-home/Photos/phockup` |
| `AMAZON_PHOTOS_SESSION_ID` | The `session-id` cookie |
| `AMAZON_PHOTOS_UBID` | The `ubid-main` cookie (`ubid-acb<region>` outside the US) |
| `AMAZON_PHOTOS_AT` | The `at-main` cookie (`at-acb<region>` outside the US) |
| `AMAZON_PHOTOS_REGION` | `com` (default) for amazon.com; otherwise the cookie suffix, e.g. `ca`, `uk`, `de` |
| `AMAZON_PHOTOS_COOKIES_FILE` | A JSON file of cookies, used only when the three cookie variables aren't set |
| `PHOTO_SELECTOR_PRINTER` | CUPS printer queue name |
| `PHOTO_SELECTOR_CONFIG` | Path to a different `config.json` |
| `PHOTO_SELECTOR_ENV` | Path to a different env file |
| `PHOTO_SELECTOR_VARIABLES_FILE` | Path to your shared variables file if it isn't `~/Dropbox/variables.sh`. Set it in a bash startup file so the scheduled run can find it. |
| `PHOTO_SELECTOR_NO_PROFILE` | Set to `1` to stop the scheduled run from loading your bash startup files and variables file |

Example lines for `~/Dropbox/variables.sh`:

```bash
export PHOTO_SELECTOR_SOURCE=synology
export SYNOLOGY_PHOTO_DIRS="$HOME/nas-home/Photos/MobileBackup:$HOME/nas-home/Photos/phockup"
```

`variables.sh` is loaded with bash, so it must use bash syntax (`export NAME=value` or `NAME=value`). If Dropbox keeps it as an online-only file, mark it "Make available offline" so the scheduled run can read it while Dropbox is syncing or offline. If the log shows "errors while loading" it, give `/bin/bash` Full Disk Access (System Settings > Privacy & Security).

Apart from `variables.sh`, the scheduled run reads bash startup files only, not fish or zsh ones. If you set variables in `~/.config/fish/config.fish` or `~/.zshrc`, also add them to `~/.bash_profile` or the env file. Also, many `~/.bashrc` files stop early when the shell isn't interactive (for example `[ -z "$PS1" ] && return`). Put the exports above that line, or in `~/.bash_profile`.

#### Amazon Photos sign-in

Amazon doesn't offer a public Amazon Photos API. The script uses the same web API as the Amazon Photos website, signed in with cookies copied from your browser. No extra libraries are needed:

1. Sign in at [amazon.com/photos](https://www.amazon.com/photos) in your browser.
2. Open the developer tools (Chrome: View > Developer > Developer Tools), then go to **Application > Cookies > https://www.amazon.com**.
3. Run `./setup_photo_selector.sh --configure`, choose `amazon`, and paste the `session-id`, `ubid-main` and `at-main` values. You can also set the `AMAZON_PHOTOS_*` variables yourself.

Anyone with these cookies can access your Amazon account, so keep them private.

Outside the US, use your regional site. Its cookies are named `ubid-acb<region>` and `at-acb<region>` (e.g. `at-acbca` for amazon.ca). Set `AMAZON_PHOTOS_REGION` to that suffix.

The cookies eventually expire, and signing out of Amazon in that browser ends them. When that happens the log says "Amazon Photos rejected the sign-in cookies". Run `--configure` again with fresh ones. Because this API is unofficial, it can also stop working if Amazon changes its website.

### 3. Set up the printer

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

### 4. Check that everything works

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
venv/bin/python select_and_print_photos.py --source synology --test  # use Synology Photos for this run
venv/bin/python select_and_print_photos.py --config /path/to/other.json
```

## Configuration

All settings live in **`~/weekly-photo-selector/config.json`**. It is plain JSON. Any key you leave out uses its default, and an unknown key is an error, so check your spelling.

Environment variables, whether exported in your shell or set in `photo-selector.env`, override these settings. See [Setting them with environment variables](#setting-them-with-environment-variables).

### Example

```json
{
  "photo_source": "synology",
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
| `photo_source` | `"synology"` | Where photos come from: `"synology"` (Synology Photos on the NAS) or `"amazon"` (Amazon Photos). Overridden by `PHOTO_SELECTOR_SOURCE` and `--source`. |
| `amazon_photos` | `{"cookies_file": "~/weekly-photo-selector/amazon_cookies.json", "cookies": null}` | Amazon sign-in: a `cookies` object, or a JSON file of cookies. The `AMAZON_PHOTOS_*` variables take priority. |
| `photo_dirs` | MobileBackup and phockup folders on the NAS | Synology Photos folders to scan, searched recursively. Used when `photo_source` is `"synology"`. Missing folders are skipped with a warning. |
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

**Time window.** The window is the 7 full days ending at midnight tonight. Run on a Sunday, it covers Monday 00:00 through Sunday 23:59, so weekly runs don't overlap or leave gaps. A photo's date comes from EXIF `DateTimeOriginal`, falling back to `DateTimeDigitized`, then `DateTime`, then the file's modification time. With Synology Photos, files not modified in the window are skipped without being opened, which keeps network scans fast. With Amazon Photos, the script lists photos uploaded since the day before the window, newest first. It downloads those whose Amazon capture date is within a day of the window, then checks the EXIF date. The extra day covers time-zone differences, since Amazon stores dates in UTC and EXIF has no time zone.

**Formats.** JPEG, PNG, TIFF and HEIC/HEIF. HEIC needs `pillow-heif`, which the setup installs. Without it, HEIC files are skipped with a warning.

**Duplicates.** Exact duplicates are removed by SHA-256 hash. The print history uses the same hash, so a photo printed from one source isn't printed again from the other.

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
├── photo_sources.py            # Amazon Photos and Synology Photos sources
├── test_photo_rating.py        # Checks Ollama and the rating prompt
├── requirements.txt            # Python dependencies
├── config.json                 # Your settings (see Configuration)
├── photo-selector.env          # Photo source settings and Amazon cookies (chmod 600)
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
- **Synology NAS** running Synology Photos and mounted at `~/nas-home` (default source), or an **Amazon Photos** account
- **Canon PIXMA G620** on the same network

## Troubleshooting

### Amazon Photos errors
- "No Amazon Photos sign-in": run `./setup_photo_selector.sh --configure` (see [Amazon Photos sign-in](#amazon-photos-sign-in)).
- "Set all of AMAZON_PHOTOS_SESSION_ID, ...": only some of the cookie variables are set. Check your shell exports and the env file.
- "rejected the sign-in cookies (HTTP 401/403)": the cookies expired. Run `--configure` with fresh ones from your browser.
- Other "Amazon Photos request failed" errors may mean Amazon changed its website API. Until it's fixed, run with `--source synology`.

### No photos selected
- Check which source the run used. The log line "Selecting photos from ... in Amazon Photos" names it.
- For Synology Photos, check that the NAS is mounted at `~/nas-home`. A missing folder is logged as "Photo directory does not exist (is the NAS mounted?)".
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
