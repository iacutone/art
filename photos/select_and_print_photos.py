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
OUTPUT_DIR = "~/weekly-photo-selector/selections_metadata"  # Store selection metadata only
LOG_FILE = "~/weekly-photo-selector/photo_selector.log"
PRINTER_NAME = "Canon_PIXMA_G620"  # Adjust based on your printer setup
MAX_PHOTOS_TO_SELECT = 5  # Number of photos to select and print

# Family Photo Rating Configuration
FAMILY_PHOTO_FOCUS = True  # Set to False for general photo selection
MIN_FAMILY_SCORE = 6       # Minimum score to consider for family photos
PREFER_MULTIPLE_PEOPLE = True  # Boost scores for photos with multiple family members
BOOST_CHILDREN_PHOTOS = True   # Give extra points to photos with children

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
        """Use Ollama to rate and analyze a photo with family-focused criteria."""
        if not self.selected_model:
            return {"score": 5, "reasoning": "No model available"}
            
        base64_image = self.encode_image_base64(image_path)
        if not base64_image:
            return {"score": 0, "reasoning": "Failed to encode image"}
        
        # Use family-focused prompt if enabled
        if FAMILY_PHOTO_FOCUS:
            prompt = self._get_family_photo_prompt()
        else:
            prompt = self._get_general_photo_prompt()
        
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
                    
                    # Apply family-specific scoring adjustments
                    if FAMILY_PHOTO_FOCUS:
                        rating = self._apply_family_scoring_boost(rating, result.get('response', ''))
                    
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
    
    def _get_family_photo_prompt(self) -> str:
        """Get the family-focused rating prompt."""
        return """Rate this photo on a scale of 1-10 for family memory value and printing quality. Consider:
        1. Family content and emotional significance:
           - Clear faces of family members (especially children)
           - Genuine emotions, smiles, laughter, or meaningful expressions
           - Family interactions, bonding moments, milestones
           - Special occasions, holidays, vacations, everyday precious moments
        2. Memory worthiness:
           - Will this be treasured in 5-10 years?
           - Does it capture personality or a special moment in time?
           - Is it the kind of photo you'd put in a family album?
        3. Print quality:
           - Good focus and lighting on faces
           - Composition that works well for physical printing
           - Not blurry, overexposed, or technically poor
        4. Prioritize over generic content:
           - Family photos > landscape/object photos
           - Candid moments > posed shots (unless special occasions)
           - Multiple family members > solo shots (unless very special)
           
        Give LOWER scores (1-4) to:
        - Photos without clear family members
        - Blurry faces or poor lighting on people
        - Screenshots, memes, or non-memorable content
        - Generic landscape/food photos without family context
        
        Give HIGHER scores (7-10) to:
        - Clear, well-lit photos of family members
        - Emotional moments, celebrations, milestones
        - Photos that capture personality and relationships
        - Images that tell a family story
        
        Respond with JSON format:
        {
            "score": <number 1-10>,
            "reasoning": "<brief explanation focusing on family memory value>",
            "family_content": <1-10>,
            "emotional_impact": <1-10>,
            "print_quality": <1-10>,
            "memory_worthiness": <1-10>
        }"""
    
    def _get_general_photo_prompt(self) -> str:
        """Get the general photo rating prompt."""
        return """Rate this photo on a scale of 1-10 for printing quality and emotional impact. Consider:
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
    
    def _apply_family_scoring_boost(self, rating: Dict, raw_response: str) -> Dict:
        """Apply family-specific scoring boosts based on configuration."""
        base_score = rating.get('score', 5)
        family_content = rating.get('family_content', 5)
        
        # Apply minimum family score filter
        if family_content < MIN_FAMILY_SCORE:
            logger.debug(f"Photo scored low on family content ({family_content}), reducing overall score")
            rating['score'] = min(base_score, 4)  # Cap at 4 for non-family content
            return rating
        
        boost = 0
        boost_reasons = []
        
        # Boost for multiple people (family interactions)
        if PREFER_MULTIPLE_PEOPLE:
            response_lower = raw_response.lower()
            if any(phrase in response_lower for phrase in ['multiple people', 'family members', 'group', 'together']):
                boost += 1
                boost_reasons.append("multiple family members")
        
        # Boost for children
        if BOOST_CHILDREN_PHOTOS:
            response_lower = raw_response.lower()
            if any(phrase in response_lower for phrase in ['child', 'children', 'kid', 'baby', 'toddler']):
                boost += 1
                boost_reasons.append("children present")
        
        # Apply boost but cap at 10
        if boost > 0:
            new_score = min(base_score + boost, 10)
            rating['score'] = new_score
            boost_text = f" (boosted +{boost} for: {', '.join(boost_reasons)})"
            rating['reasoning'] += boost_text
            logger.debug(f"Applied family boost: {boost_reasons}")
        
        return rating
    
    def select_top_photos(self, weekly_photos: List[Path]) -> List[Tuple[Path, Dict]]:
        """Rate all photos and select the top ones based on AI scoring."""
        if not weekly_photos:
            return []
        
        logger.info(f"Rating {len(weekly_photos)} photos with AI...")
        rated_photos = []
        
        for i, photo_path in enumerate(weekly_photos):
            logger.info(f"Processing photo {i+1}/{len(weekly_photos)}: {photo_path.name}")
            
            try:
                rating = self.rate_photo_with_ollama(photo_path)
                score = rating.get('score', 0)
                
                if score > 0:  # Only include photos with valid scores
                    rated_photos.append((photo_path, rating))
                    logger.debug(f"Added {photo_path.name} with score {score}")
                else:
                    logger.warning(f"Skipping {photo_path.name} due to low/invalid score: {score}")
                    
            except Exception as e:
                logger.error(f"Error rating {photo_path.name}: {e}")
                continue
            
            # Small delay to be nice to the AI service
            time.sleep(0.5)
        
        if not rated_photos:
            logger.warning("No photos received valid ratings")
            return []
        
        # Sort by score (highest first) and take top N
        sorted_photos = sorted(rated_photos, key=lambda x: x[1].get('score', 0), reverse=True)
        top_photos = sorted_photos[:MAX_PHOTOS_TO_SELECT]
        
        logger.info(f"Selected top {len(top_photos)} photos:")
        for i, (photo_path, rating) in enumerate(top_photos, 1):
            score = rating.get('score', 'N/A')
            reasoning = rating.get('reasoning', 'No reasoning provided')
            logger.info(f"  {i}. {photo_path.name} - Score: {score}/10")
            logger.info(f"     Reasoning: {reasoning}")
        
        return top_photos
    
    def copy_selected_photos(self, selected_photos: List[Tuple[Path, Dict]]) -> List[Path]:
        """Save selection metadata and return original photo paths for direct printing."""
        if not selected_photos:
            return []
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        photo_paths = []
        
        # Create a summary file with all selections
        summary_file = self.output_dir / f"selection_{timestamp}.json"
        selections_summary = {
            'selection_date': timestamp,
            'week_range': f"{self.get_week_range()[0].strftime('%Y-%m-%d')} to {self.get_week_range()[1].strftime('%Y-%m-%d')}",
            'total_photos_evaluated': len(selected_photos),
            'selected_photos': []
        }
        
        logger.info(f"Preparing {len(selected_photos)} photos for direct printing from Synology:")
        
        for i, (photo_path, rating) in enumerate(selected_photos, 1):
            try:
                score = rating.get('score', 'unknown')
                reasoning = rating.get('reasoning', 'No reasoning provided')
                
                # Add to summary
                photo_info = {
                    'rank': i,
                    'original_path': str(photo_path),
                    'filename': photo_path.name,
                    'rating': rating
                }
                selections_summary['selected_photos'].append(photo_info)
                
                # Keep original path for direct printing
                photo_paths.append(photo_path)
                
                logger.info(f"Rank {i}: {photo_path.name} (Score: {score}/10)")
                logger.info(f"    Path: {photo_path}")
                logger.info(f"    Reasoning: {reasoning}")
                
            except Exception as e:
                logger.error(f"Error processing {photo_path}: {e}")
                continue
        
        # Save selection summary
        try:
            with open(summary_file, 'w') as f:
                json.dump(selections_summary, f, indent=2)
            logger.info(f"Selection metadata saved to: {summary_file}")
        except Exception as e:
            logger.warning(f"Could not save selection metadata: {e}")
        
        logger.info(f"Ready to print {len(photo_paths)} photos directly from Synology NAS")
        return photo_paths

    def print_photos(self, photo_paths: List[Path]):
        """Print the selected photos directly from their original locations."""
        if not photo_paths:
            logger.warning("No photos to print")
            return
            
        if self.test_mode:
            logger.info(f"TEST MODE: Would print {len(photo_paths)} photos directly from Synology:")
            for i, photo_path in enumerate(photo_paths, 1):
                logger.info(f"  {i}. {photo_path}")
            return
        
        # Check if printer is available
        try:
            result = subprocess.run(["lpstat", "-p", PRINTER_NAME], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"Printer '{PRINTER_NAME}' not found or not configured")
                logger.info(f"Selection metadata saved in: {self.output_dir}")
                logger.info("Run setup_canon_printer.sh after you get your Canon PIXMA G620")
                return
        except Exception as e:
            logger.warning(f"Could not check printer status: {e}")
            logger.info("Skipping printing - selection metadata is saved for when printer is available")
            return
        
        logger.info(f"Printing {len(photo_paths)} photos directly from Synology on {PRINTER_NAME}...")
        
        for i, photo_path in enumerate(photo_paths, 1):
            try:
                logger.info(f"Printing photo {i}/{len(photo_paths)}: {photo_path.name}")
                
                # Verify file still exists and is accessible
                if not photo_path.exists():
                    logger.error(f"Photo no longer exists: {photo_path}")
                    continue
                
                # Use lpr to print directly from network location
                cmd = ["lpr", "-P", PRINTER_NAME, str(photo_path)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"✓ Successfully sent to printer: {photo_path.name}")
                else:
                    logger.error(f"✗ Failed to print {photo_path.name}: {result.stderr}")
                    # Log the full path for troubleshooting
                    logger.error(f"  Full path: {photo_path}")
                    
            except Exception as e:
                logger.error(f"Error printing {photo_path}: {e}")
        
        logger.info("Print jobs submitted to printer queue")
        logger.info("Photos printed directly from Synology NAS - no local storage used")
    
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