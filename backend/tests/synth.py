"""Synthetic test documents (generated on the fly; never real people's documents)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def pdf(lines: list[str]) -> bytes:
    """A minimal, valid single-page PDF with a real text layer (Helvetica)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    body = "BT /F1 11 Tf 14 TL 50 800 Td " + " ".join(f"({esc(line)}) '" for line in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def text_image(lines: list[str]) -> bytes:
    """A 'scanned' document: text rendered into a PNG (no text layer), for OCR tests."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError:
        font = ImageFont.load_default(size=30)
    img = Image.new("L", (1400, 120 + 50 * len(lines)), 255)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((60, 60 + 50 * i), line, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def face_jpeg(name: str, scale: float = 2.5) -> bytes:
    """LFW test face, enlarged so it passes the minimum face-size quality check."""
    import cv2
    img = cv2.imread(str(FIXTURES / name))
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def two_faces_jpeg() -> bytes:
    import cv2
    import numpy as np
    a = cv2.imdecode(np.frombuffer(face_jpeg("Alvaro_Uribe_0028.jpg"), np.uint8), cv2.IMREAD_COLOR)
    b = cv2.imdecode(np.frombuffer(face_jpeg("Aaron_Tippin_0001.jpg"), np.uint8), cv2.IMREAD_COLOR)
    return cv2.imencode(".jpg", np.hstack([a, b]))[1].tobytes()


def blank_jpeg() -> bytes:
    import cv2
    import numpy as np
    return cv2.imencode(".jpg", np.full((480, 640, 3), 120, np.uint8))[1].tobytes()


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def resume(name="Arun Kumar", degree="B.E. Computer Science and Engineering", college="Anna University, Chennai", grad=(2022, 2026),
           jobs=(), skills="Python, SQL, React, Git") -> bytes:
    lines = [name, "arun@example.com | +91 98765 43210", "", "EDUCATION", f"{degree}", f"{college}  {grad[0]} - {grad[1]}  CGPA: 8.4", "",
             "SKILLS", skills, ""]
    if jobs:
        lines.append("EXPERIENCE")
        for title, company, period in jobs:
            lines += [f"{title} at {company}", period, ""]
    return pdf(lines)


def marksheet(name="ARUN KUMAR", reg="AU2026CS001", university="Anna University", degree="Bachelor of Engineering", year=2026,
              cgpa="8.40", include_year=True) -> bytes:
    lines = [university.upper(), "CONSOLIDATED MARK SHEET", f"Name of the Candidate : {name}", f"Register Number : {reg}",
             f"Degree : {degree}", "Branch : Computer Science and Engineering"]
    if include_year:
        lines.append(f"Year of Passing : {year}")
    lines += [f"CGPA : {cgpa}", "Total Marks : 3780 / 4500"]
    return pdf(lines)


def experience_letter(name="Arun Kumar", company="Zoho Corporation Pvt Ltd", title="Software Engineer Intern",
                      joined="01/05/2025", relieved="31/07/2025") -> bytes:
    return pdf([company, "EXPERIENCE CERTIFICATE", "", f"This is to certify that Mr. {name} was employed with us",
                f"as {title}.", f"Date of Joining : {joined}", f"Date of Relieving : {relieved}", "", "For " + company, "HR Manager"])
