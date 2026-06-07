#!/usr/bin/env python3
"""
Weekly Photo Selector and Printer
Automatically selects the best photos from the past week and prints them.
"""

import os
import sys
import json
import subprocess
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
from typing import List, Dict, Tuple
import base64
import requests
from PIL import Image, ExifTags
import time

# Configuration
PHOTO_DIRS = [
    "~/nas-home/Photos/MobileBackup",
    "~/nas-home/Photos/phockup"
]
# Try different vision-capable models in order of preference
VISION_MODELS = ["llama3.2-vision:latest", "llava:latest", "llama3.2:latest"]
OLLAMA_URL = "http://localhost:11434"
OUTPUT_DIR = "~/weekly-photo-selector/selected_photos"
LOG_FILE = "~/weekly-photo-selector/photo_selector.log"
PRINTER_NAME = "Canon_PIXMA_G620"  # Adjust based on your printer setup
MAX_PHOTOS_TO_SELECT = 5  # Number of photos to select and print

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.expanduser(LOG_FILE)),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PhotoSelector:
    def __init__(self, test_mode=False):
        self.output_dir = Path(os.path.expanduser(OUTPUT_DIR))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.test_mode = test_mode
        self.selected_model = None
        
        # Find the best available vision model
        self._select_vision_model()
        
    def _select_vision_model(self):
        """Select the best available vision model from Ollama."""
        try:
            # Get list of available models
            response = requests.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                available_models = [model['name'] for model in response.json().get('models', [])]
                
                # Find the first available vision model
                for model in VISION_MODELS:
                    if model in available_models:
                        self.selected_model = model
                        logger.info(f"Using vision model: {model}")
                        return
                
                # Fallback to first available model
                if available_models:
                    self.selected_model = available_models[0]
                    logger.warning(f"No preferred vision model found, using: {self.selected_model}")
                else:
                    logger.error("No Ollama models available")
                    
        except Exception as e:
            logger.error(f"Error selecting vision model: {e}")
            self.selected_model = VISION_MODELS[0]  # Fallback
        
    def get_week_range(self) -> Tuple[datetime, datetime]:
        """Get the date range for the past week (Sunday to Sunday)."""
        today = datetime.now()
        # Get last Sunday
        days_since_sunday = today.weekday() + 1 if today.weekday() != 6 else 0
        last_sunday = today - timedelta(days=days_since_sunday)
        # Get the Sunday before that
        week_start = last_sunday - timedelta(days=7)
        week_end = last_sunday
        
        logger.info(f"Selecting photos from {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
        return week_start, week_end
    
    def get_image_date(self, image_path: Path) -> datetime:
        """Extract the date from image EXIF data or fall back to file modification time."""
        try:
            with Image.open(image_path) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        if tag in ExifTags.TAGS:
                            if ExifTags.TAGS[tag] == 'DateTime':
                                return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                            elif ExifTags.TAGS[tag] == 'DateTimeOriginal':
                                return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"Could not read EXIF from {image_path}: {e}")
        
        # Fall back to file modification time
        return datetime.fromtimestamp(image_path.stat().st_mtime)
    
    def collect_weekly_photos(self) -> List[Path]:
        """Collect all photos from the past week."""
        week_start, week_end = self.get_week_range()
        weekly_photos = []
        
        for photo_dir_str in PHOTO_DIRS:
            photo_dir = Path(os.path.expanduser(photo_dir_str))
            if not photo_dir.exists():
                logger.warning(f"Photo directory does not exist: {photo_dir}")
                continue
                
            logger.info(f"Scanning {photo_dir}")
            
            # Common image extensions
            image_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.tiff', '.tif'}
            
            for image_path in photo_dir.rglob('*'):
                if image_path.suffix.lower() in image_extensions:
                    try:
                        image_date = self.get_image_date(image_path)
                        if week_start <= image_date <= week_end:
                            weekly_photos.append(image_path)
                            logger.debug(f"Added photo: {image_path} (taken: {image_date})")
                    except Exception as e:
                        logger.warning(f"Error processing {image_path}: {e}")
        
        logger.info(f"Found {len(weekly_photos)} photos from the past week")
        return weekly_photos
    
    def encode_image_base64(self, image_path: Path) -> str:
        """Encode image to base64 for Ollama vision model."""
        try:
            with Image.open(image_path) as img:
                # Resize image if too large to save on processing time
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save to memory as JPEG
                from io import BytesIO
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                buffer.seek(0)
                
                return base64.b64encode(buffer.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image {image_path}: {e}")
            return None
    
    def rate_photo_with_ollama(self, image_path: Path) -> Dict:
        """Use Ollama to rate and analyze a photo."""
        if not self.selected_model:
            return {"score": 5, "reasoning": "No model available"}
            
        base64_image = self.encode_image_base64(image_path)
        if not base64_image:
            return {"score": 0, "reasoning": "Failed to encode image"}
        
        prompt = """Rate this photo on a scale of 1-10 for printing quality and emotional impact. Consider:
        1. Technical quality (focus, exposure, composition)
        2. Emotional impact and memorability
        3. Print worthiness (how good it would look printed)
        4. Uniqueness and interest
        
        Respond with JSON format:
        {
            "score": <number 1-10>,
            "reasoning": "<brief explanation>",
            "technical_quality": <1-10>,
            "emotional_impact": <1-10>,
            "print_worthiness": <1-10>
        }"""
        
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "images": [base64_image],
                    "stream": False,
                    "format": "json"
                },
                timeout=120  # Increased timeout for vision models
            )
            
            if response.status_code == 200:
                result = response.json()
                try:
                    rating = json.loads(result['response'])
                    logger.info(f"Rated {image_path.name}: {rating.get('score', 'N/A')}/10")
                    return rating
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse JSON response for {image_path}: {e}")
                    # Fallback: try to extract score from text
                    text = result.get('response', '')
                    import re
                    score_match = re.search(r'(?:score|rating).*?(\d+)', text.lower())
                    score = int(score_match.group(1)) if score_match else 5
                    return {"score": score, "reasoning": "Fallback parsing"}
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return {"score": 5, "reasoning": "API error"}
                
        except Exception as e:
            logger.error(f"Error rating photo {image_path}: {e}")
            return {"score": 5, "reasoning": f"Error: {str(e)}"}
    
    def print_photos(self, photo_paths: List[Path]):
        """Print the selected photos."""
        if not photo_paths:
            logger.warning("No photos to print")
            return
            
        if self.test_mode:
            logger.info(f"TEST MODE: Would print {len(photo_paths)} photos:")
            for photo_path in photo_paths:
                logger.info(f"  - {photo_path.name}")
            return
        
        # Check if printer is available
        try:
            result = subprocess.run(["lpstat", "-p", PRINTER_NAME], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"Printer '{PRINTER_NAME}' not found or not configured")
                logger.info(f"Photos are saved in: {self.output_dir}")
                logger.info("Run setup_canon_printer.sh after you get your Canon PIXMA G620")
                return
        except Exception as e:
            logger.warning(f"Could not check printer status: {e}")
            logger.info("Skipping printing - photos are saved for when printer is available")
            return
        
        logger.info(f"Printing {len(photo_paths)} photos on {PRINTER_NAME}...")
        
        for photo_path in photo_paths:
            try:
                # Use lpr to print (standard Unix printing command)
                cmd = ["lpr", "-P", PRINTER_NAME, str(photo_path)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Successfully printed: {photo_path.name}")
                else:
                    logger.error(f"Failed to print {photo_path.name}: {result.stderr}")
                    
            except Exception as e:
                logger.error(f"Error printing {photo_path}: {e}")
        
        logger.info("Printing jobs submitted to printer queue")
    
    def run(self):
        """Main execution method."""
        logger.info("Starting weekly photo selection and printing")
        
        try:
            # Collect photos from the past week
            weekly_photos = self.collect_weekly_photos()
            
            if not weekly_photos:
                logger.warning("No photos found for the past week")
                return
            
            # Select top photos using Ollama
            selected_photos = self.select_top_photos(weekly_photos)
            
            if not selected_photos:
                logger.warning("No photos selected")
                return
            
            # Copy selected photos to output directory
            copied_photos = self.copy_selected_photos(selected_photos)
            
            # Print the photos
            self.print_photos(copied_photos)
            
            logger.info("Weekly photo selection and printing completed successfully")
            
        except Exception as e:
            logger.error(f"Error in photo selection process: {e}")
            raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weekly Photo Selector and Printer")
    parser.add_argument("--test", action="store_true", help="Run in test mode (don't actually print)")
    args = parser.parse_args()
    
    selector = PhotoSelector(test_mode=args.test)
    selector.run()