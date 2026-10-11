"""Private file storage for candidate documents.

Files live in data/uploads under random names (never the user's file name), outside every static folder,
and are only returned through authorised API endpoints.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

from fastapi import UploadFile

from .config import MAX_UPLOAD_BYTES, UPLOAD_DIR
from .errors import ApiError, bad_request

# Detected from the file's first bytes; the browser-supplied type and extension are not trusted.
_SIGNATURES = {"application/pdf": [b"%PDF-"], "image/jpeg": [b"\xff\xd8\xff"], "image/png": [b"\x89PNG\r\n\x1a\n"]}
_ALLOWED = {
    "resume": {"application/pdf"},
    "marksheet": {"application/pdf", "image/jpeg", "image/png"},
    "education_certificate": {"application/pdf", "image/jpeg", "image/png"},
    "id_document": {"application/pdf", "image/jpeg", "image/png"},
    "experience_letter": {"application/pdf", "image/jpeg", "image/png"},
    "certificate": {"application/pdf", "image/jpeg", "image/png"},
    "selfie": {"image/jpeg", "image/png"},
}
DOCUMENT_KINDS = tuple(k for k in _ALLOWED if k != "selfie")
SINGLE_KINDS = {"resume", "marksheet", "education_certificate", "id_document", "experience_letter", "selfie"}  # a new upload replaces the old one
_LABELS = {"application/pdf": "PDF", "image/jpeg": "JPG", "image/png": "PNG"}


@dataclass
class StoredFile:
    storage_name: str
    content_type: str
    size: int
    sha256: str
    original_name: str


def sniff(data: bytes) -> str | None:
    for ctype, sigs in _SIGNATURES.items():
        if any(data.startswith(s) for s in sigs):
            return ctype
    return None


def _clean_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ()]+", "_", (name or "file").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]).strip() or "file"
    return name[:120]


def save_bytes(kind: str, data: bytes, original_name: str) -> StoredFile:
    if kind not in _ALLOWED:
        raise bad_request(f"Unknown document type '{kind}'.", "invalid_document_kind")
    if not data:
        raise bad_request(f"{_clean_name(original_name)} is empty.", "empty_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", f"{_clean_name(original_name)} is larger than 5 MB.")
    ctype = sniff(data)
    if ctype not in _ALLOWED[kind]:
        allowed = " or ".join(_LABELS[t] for t in sorted(_ALLOWED[kind]))
        raise ApiError(415, "unsupported_file_type", f"{_clean_name(original_name)}: this file isn't a valid {allowed}.")
    if ctype in ("image/jpeg", "image/png"):
        from .verification.face import MAX_IMAGE_PIXELS, image_size
        size = image_size(data)
        if size and size[0] * size[1] > MAX_IMAGE_PIXELS:
            raise ApiError(413, "image_too_large", f"{_clean_name(original_name)}: the image is too large ({size[0]}×{size[1]} pixels). "
                                                   "Use a photo under 40 megapixels.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_name = secrets.token_hex(16)
    path = UPLOAD_DIR / storage_name
    with open(path, "xb") as fh:
        fh.write(data)
    return StoredFile(storage_name, ctype, len(data), hashlib.sha256(data).hexdigest(), _clean_name(original_name))


async def save_upload(kind: str, upload: UploadFile) -> StoredFile:
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    return save_bytes(kind, data, upload.filename or kind)


def save_data_url(kind: str, data_url: str, name: str) -> StoredFile:
    m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=\s]+)", data_url or "")
    if not m:
        raise bad_request("The photo is missing or not a JPG/PNG image.", "invalid_selfie")
    try:
        data = base64.b64decode(m.group(2), validate=False)
    except ValueError as exc:
        raise bad_request("The photo could not be read.", "invalid_selfie") from exc
    return save_bytes(kind, data, name)


def path_for(storage_name: str):
    path = (UPLOAD_DIR / storage_name).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        return None
    return path


def delete(storage_name: str) -> None:
    path = path_for(storage_name)
    if path:
        path.unlink(missing_ok=True)


def save_raw(data: bytes) -> tuple[str, str]:
    """Store bytes that came from a trusted integration (e.g. DigiLocker) privately; returns (storage_name, sha256)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_name = secrets.token_hex(16)
    with open(UPLOAD_DIR / storage_name, "xb") as fh:
        fh.write(data)
    return storage_name, hashlib.sha256(data).hexdigest()
