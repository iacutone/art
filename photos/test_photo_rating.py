#!/usr/bin/env python3
"""
Test script to verify the photo rating system works with your Ollama setup.
"""

import requests
import base64
import json
from PIL import Image
from io import BytesIO

def create_test_image():
    """Create a simple test image."""
    img = Image.new('RGB', (400, 300), color='lightblue')
    
    # Add some simple content
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    
    try:
        # Try to use a system font
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    draw.text((50, 100), "Test Photo", fill='darkblue', font=font)
    draw.text((50, 150), "Weekly Selector", fill='darkblue', font=font)
    draw.rectangle([50, 50, 350, 250], outline='darkblue', width=3)
    
    return img

def test_ollama_vision():
    """Test if Ollama can process images."""
    print("🧪 Testing Ollama vision capabilities...")
    
    # Create test image
    test_img = create_test_image()
    
    # Convert to base64
    buffer = BytesIO()
    test_img.save(buffer, format='JPEG')
    buffer.seek(0)
    base64_image = base64.b64encode(buffer.read()).decode('utf-8')
    
    # Test with Ollama
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:latest",
                "prompt": "Describe this image briefly.",
                "images": [base64_image],
                "stream": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            description = result.get('response', '')
            print("✅ Ollama vision test successful!")
            print(f"Image description: {description}")
            return True
        else:
            print(f"❌ Ollama API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Ollama: {e}")
        return False

def test_photo_rating():
    """Test the photo rating functionality."""
    print("🎯 Testing photo rating system...")
    
    test_img = create_test_image()
    buffer = BytesIO()
    test_img.save(buffer, format='JPEG')
    buffer.seek(0)
    base64_image = base64.b64encode(buffer.read()).decode('utf-8')
    
    prompt = """Rate this photo on a scale of 1-10 for printing quality and emotional impact. Consider:
    1. Technical quality (focus, exposure, composition)
    2. Emotional impact and memorability
    3. Print worthiness (how good it would look printed)
    4. Uniqueness and interest
    
    Respond with JSON format:
    {
        "score": <number 1-10>,
        "reasoning": "<brief explanation>"
    }"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:latest",
                "prompt": prompt,
                "images": [base64_image],
                "stream": False,
                "format": "json"
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            try:
                rating = json.loads(result['response'])
                print("✅ Photo rating test successful!")
                print(f"Score: {rating.get('score', 'N/A')}/10")
                print(f"Reasoning: {rating.get('reasoning', 'N/A')}")
                return True
            except json.JSONDecodeError:
                print("⚠️  JSON parsing failed, but Ollama responded:")
                print(result.get('response', 'No response'))
                return False
        else:
            print(f"❌ Rating API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing rating: {e}")
        return False

if __name__ == "__main__":
    print("🤖 Testing Weekly Photo Selector System")
    print("=" * 40)
    
    # Check if Ollama is running
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama service is running")
        else:
            print("❌ Ollama service not responding")
            exit(1)
    except:
        print("❌ Cannot connect to Ollama service")
        print("Make sure Ollama is running: ollama serve")
        exit(1)
    
    print()
    
    # Test vision capabilities
    vision_works = test_ollama_vision()
    print()
    
    # Test rating system
    rating_works = test_photo_rating()
    print()
    
    if vision_works and rating_works:
        print("🎉 All tests passed! Your system is ready.")
        print()
        print("Next steps:")
        print("1. Run ./setup_photo_selector.sh to install the full system")
        print("2. When you get your Canon PIXMA G620, run ./setup_canon_printer.sh")
    else:
        print("⚠️  Some tests failed. Check the errors above.")