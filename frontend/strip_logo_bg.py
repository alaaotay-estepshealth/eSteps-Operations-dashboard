"""One-shot: strip near-white background from logo_inversed.png → transparent."""
from PIL import Image
from pathlib import Path

SRC = Path(__file__).parent / "logo_inversed.png"
DST = Path(__file__).parent / "public" / "logo_inversed.png"

img = Image.open(SRC).convert("RGBA")
pixels = img.load()
w, h = img.size
threshold = 230  # any RGB above this on all channels = treat as background

stripped = 0
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if r >= threshold and g >= threshold and b >= threshold:
            pixels[x, y] = (r, g, b, 0)
            stripped += 1

img.save(DST, "PNG")
print(f"Stripped {stripped:,} background pixels -> {DST}")
