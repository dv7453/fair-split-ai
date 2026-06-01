import base64
import io
from typing import Any

from PIL import Image, ImageOps


def decode_receipt_image(base64_str: str) -> tuple[Image.Image, dict[str, Any]]:
    """Decode base64 to RGB PIL image (vision path — no OpenCV)."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]

    image_bytes = base64.b64decode(base64_str)
    pil_image = Image.open(io.BytesIO(image_bytes))
    pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
    width, height = pil_image.size
    return pil_image, {"width": width, "height": height, "was_upscaled": False, "deskew_angle": 0.0}


def preprocess_image(base64_str: str) -> tuple[Image.Image, dict[str, Any]]:
    """
    Decode a base64 image, preprocess for OCR, and return a PIL image plus metadata.
    """
    import cv2
    import numpy as np

    pil_image, meta = decode_receipt_image(base64_str)
    width, height = meta["width"], meta["height"]

    image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    gray, deskew_angle = _deskew(gray)

    height, width = gray.shape[:2]
    # Denoise is very slow on large images; skip when already high-res.
    if height * width < 900_000:
        gray = cv2.fastNlMeansDenoising(gray, h=10)

    was_upscaled = False
    if width < 900:
        scale = 1000 / width
        new_width = 1000
        new_height = int(height * scale)
        gray = cv2.resize(
            gray,
            (new_width, new_height),
            interpolation=cv2.INTER_CUBIC,
        )
        width, height = new_width, new_height
        was_upscaled = True

    result = Image.fromarray(gray, mode="L")
    meta = {
        "width": width,
        "height": height,
        "was_upscaled": was_upscaled,
        "deskew_angle": deskew_angle,
    }
    return result, meta


def _deskew(gray):
    """Deskew using min-area rect of thresholded contours; rotate if |angle| > 0.5°."""
    import cv2
    import numpy as np

    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return gray, 0.0

    all_points = np.concatenate(contours)
    if len(all_points) < 5:
        return gray, 0.0

    rect = cv2.minAreaRect(all_points)
    angle = rect[-1]

    if rect[1][0] < rect[1][1]:
        angle = angle + 90
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90

    if abs(angle) <= 0.5:
        return gray, 0.0

    height, width = gray.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, float(angle)
