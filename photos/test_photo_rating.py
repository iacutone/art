#!/usr/bin/env python3
"""
Check that Ollama is running, a vision model is installed, and that the model
returns ratings the photo selector can use.

    python3 test_photo_rating.py               # synthetic test image
    python3 test_photo_rating.py ~/photo.jpg   # rate a real photo
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from ollama_client import HEIF_SUPPORTED, OllamaClient, OllamaError, encode_image_base64
from select_and_print_photos import FAMILY_PROMPT, GENERAL_PROMPT, load_config, to_score


def create_test_image() -> Image.Image:
    """A blue card with a red circle and the word TEST, so we can check the model sees it."""
    img = Image.new("RGB", (400, 300), color="lightblue")
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 350, 250], outline="darkblue", width=3)
    draw.ellipse([150, 90, 250, 190], fill="red")
    draw.text((180, 210), "TEST", fill="darkblue")
    return img


def main() -> int:
    config = load_config()
    client = OllamaClient(config["ollama_url"])
    print("🤖 Testing Weekly Photo Selector System")
    print("=" * 40)

    try:
        model = client.pick_vision_model(config["vision_models"])
    except OllamaError as e:
        print(f"❌ {e}")
        print("Make sure Ollama is running: ollama serve")
        return 1
    print(f"✅ Ollama is running; using vision model {model}")
    print(f"{'✅' if HEIF_SUPPORTED else '⚠️ '} HEIC support: {'yes' if HEIF_SUPPORTED else 'no (pip install pillow-heif)'}")
    print()

    if len(sys.argv) > 1:
        image = Path(sys.argv[1]).expanduser()
        label = image.name
    else:
        image = create_test_image()
        label = "synthetic test image"
    image_b64 = encode_image_base64(image)

    print(f"🧪 Vision check ({label})...")
    try:
        reply = client.generate_json(
            model,
            'Describe this image. Respond with JSON: {"description": "<one sentence>"}',
            image_b64,
        )
    except OllamaError as e:
        print(f"❌ {e}")
        return 1
    description = reply.get("description", reply)
    print(f"   Model says: {description}")
    if label == "synthetic test image" and "red" not in str(description).lower():
        print("⚠️  Expected the description to mention a red circle; the model may not be seeing the image.")
    print()

    print("🎯 Rating check (same prompt as the weekly run)...")
    prompt = FAMILY_PROMPT if config["family_photo_focus"] else GENERAL_PROMPT
    try:
        rating = client.generate_json(model, prompt, image_b64)
    except OllamaError as e:
        print(f"❌ {e}")
        return 1
    score = to_score(rating.get("score"))
    if score is None:
        print(f"❌ Reply has no usable score: {rating}")
        return 1
    print(f"✅ Score: {score}/10")
    print(f"   Reasoning: {rating.get('reasoning', 'N/A')}")
    print()
    print("🎉 All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
