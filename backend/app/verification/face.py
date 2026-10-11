"""Face detection (YuNet) and face features (SFace) with OpenCV.

Thresholds (cosine similarity of SFace features):
  * SAME_PERSON = 0.363  – OpenCV's published threshold for SFace (cosine), used for enrolment rechecks and the ID photo.
  * DUPLICATE   = 0.50   – stricter value we chose for cross-account duplicate alerts, to keep false alerts rare.
Liveness: NOT implemented. Only basic capture quality is checked (one face, size, brightness, sharpness).
A printed photo or a screen held up to the camera can pass. Results are evidence for a human reviewer, never a decision.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("trusttrace.face")
try:  # silence OpenCV's backend warnings in the server console
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except AttributeError:
    pass
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MODEL_NAME = "YuNet-2023mar + SFace-2021dec (OpenCV)"

SAME_PERSON = 0.363
DUPLICATE = 0.50
DETECTION_SCORE = 0.80
MIN_FACE_PX = 64
MIN_BRIGHTNESS, MAX_BRIGHTNESS = 50, 215
MIN_SHARPNESS = 20.0  # variance of Laplacian on the face crop

_lock = threading.Lock()
_models: dict = {}


class FaceUnavailable(RuntimeError):
    pass


def _join_parts(path: Path) -> None:
    """The SFace model is shipped in two parts (upload size limit). Join them once, if every part is present."""
    parts = sorted(path.parent.glob(path.name + ".part*"), key=lambda p: int(p.suffix.removeprefix(".part") or 0))
    if len(parts) < 2 or [int(p.suffix.removeprefix(".part")) for p in parts] != list(range(1, len(parts) + 1)):
        return
    tmp = path.with_suffix(path.suffix + ".joining")
    with open(tmp, "wb") as out:
        for part in parts:
            out.write(part.read_bytes())
    tmp.replace(path)  # checksum is verified right after by _check_models
    log.info("Joined %d parts into %s", len(parts), path.name)


def _check_models() -> None:
    sums = {}
    sumfile = MODEL_DIR / "SHA256SUMS"
    if sumfile.is_file():
        for line in sumfile.read_text().splitlines():
            if line.strip():
                h, name = line.split()
                sums[name] = h
    for name in (DETECTOR_FILE, RECOGNIZER_FILE):
        path = MODEL_DIR / name
        if not path.is_file():
            _join_parts(path)
        if not path.is_file():
            missing = " (download zip part 2 and extract it into the same folder)" if (MODEL_DIR / f"{name}.part1").is_file() else ""
            raise FaceUnavailable(f"Face model {name} is missing from backend/models{missing}.")
        if name in sums and hashlib.sha256(path.read_bytes()).hexdigest() != sums[name]:
            raise FaceUnavailable(f"Face model {name} does not match its published checksum.")


def _get():
    with _lock:
        if not _models:
            if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
                raise FaceUnavailable("This OpenCV build has no FaceDetectorYN/FaceRecognizerSF (needs OpenCV 4.5.4+).")
            _check_models()
            _models["det"] = cv2.FaceDetectorYN.create(str(MODEL_DIR / DETECTOR_FILE), "", (320, 320), DETECTION_SCORE, 0.3, 5000)
            _models["rec"] = cv2.FaceRecognizerSF.create(str(MODEL_DIR / RECOGNIZER_FILE), "")
        return _models["det"], _models["rec"]


def available() -> tuple[bool, str]:
    try:
        _get()
        return True, ""
    except FaceUnavailable as exc:
        return False, str(exc)


@dataclass
class FaceResult:
    status: str  # ok | no_face | multiple_faces | poor_quality | unreadable | unavailable
    message: str = ""
    embedding: np.ndarray | None = None
    quality: dict = field(default_factory=dict)


MAX_IMAGE_PIXELS = 40_000_000


def image_size(data: bytes) -> tuple[int, int] | None:
    """Width/height from the image header only (no full decode), to refuse decompression bombs."""
    try:
        from io import BytesIO

        from PIL import Image
        with Image.open(BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def decode(data: bytes) -> np.ndarray | None:
    size = image_size(data)
    if size and size[0] * size[1] > MAX_IMAGE_PIXELS:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = 1280 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


def analyse(data: bytes, *, allow_multiple: bool = False, strict_quality: bool = True) -> FaceResult:
    """Detect faces, check capture quality and return the SFace feature of the (largest) face."""
    try:
        det, rec = _get()
    except FaceUnavailable as exc:
        return FaceResult("unavailable", str(exc))
    img = decode(data)
    if img is None:
        return FaceResult("unreadable", "The image could not be read.")
    h, w = img.shape[:2]
    with _lock:  # OpenCV DNN objects are not thread-safe
        det.setInputSize((w, h))
        _, faces = det.detect(img)
    faces = [] if faces is None else list(faces)
    if not faces:
        return FaceResult("no_face", "No face was found. Face the camera in good light.", quality={"faces": 0})
    faces.sort(key=lambda f: f[2] * f[3], reverse=True)
    if len(faces) > 1 and not allow_multiple:
        return FaceResult("multiple_faces", "More than one face is visible. Only the candidate should be in the frame.", quality={"faces": len(faces)})
    face = faces[0]
    x, y, fw, fh = (int(v) for v in face[:4])
    crop = cv2.cvtColor(img[max(0, y): y + fh, max(0, x): x + fw], cv2.COLOR_BGR2GRAY)
    brightness = float(crop.mean()) if crop.size else 0.0
    sharpness = float(cv2.Laplacian(crop, cv2.CV_64F).var()) if crop.size else 0.0
    quality = {"faces": len(faces), "faceSize": int(min(fw, fh)), "detectionScore": round(float(face[14]), 3),
               "brightness": round(brightness, 1), "sharpness": round(sharpness, 1)}
    problems = []
    if min(fw, fh) < MIN_FACE_PX:
        problems.append("the face is too small – move closer")
    if brightness < MIN_BRIGHTNESS:
        problems.append("the image is too dark")
    if brightness > MAX_BRIGHTNESS:
        problems.append("the image is too bright")
    if sharpness < MIN_SHARPNESS:
        problems.append("the image is blurry")
    quality["problems"] = problems
    if problems and strict_quality:
        return FaceResult("poor_quality", "Photo quality is too low: " + "; ".join(problems) + ".", quality=quality)
    with _lock:
        aligned = rec.alignCrop(img, face)
        feat = rec.feature(aligned).flatten().astype(np.float32)
    return FaceResult("ok", "", feat, quality)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, np.float32).flatten(), np.asarray(b, np.float32).flatten()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0
