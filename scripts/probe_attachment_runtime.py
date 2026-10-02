"""Read-only local inference availability probe (no credentials printed)."""
import importlib.util
import json
from pathlib import Path
from urllib.request import urlopen

print({m: bool(importlib.util.find_spec(m)) for m in ["pptx", "docx", "openpyxl", "pytest"]})
for url in ["http://127.0.0.1:11434/api/tags", "http://127.0.0.1:8642/health"]:
    try:
        with urlopen(url, timeout=4) as response:
            data = json.load(response)
        if "models" in data:
            print(url, [m.get("name") for m in data["models"]])
        else:
            print(url, data)
    except Exception as exc:
        print(url, type(exc).__name__)

from PIL import Image, ImageDraw, ImageFont
from iris.runtime.attachment_context import prepare_attachments
output = Path(__file__).resolve().parents[1] / ".iris_light_test_tmp" / "attachments"
output.mkdir(parents=True, exist_ok=True)
image_path = output / "image-ocr-test.png"
image = Image.new("RGB", (900, 160), "white")
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 48)
ImageDraw.Draw(image).text((30, 45), "CODE: IMAGE-8888", fill="black", font=font)
image.save(image_path)
result = prepare_attachments([str(image_path)])
print("image OCR", result.attachments[0].text.strip(), result.attachments[0].error)
