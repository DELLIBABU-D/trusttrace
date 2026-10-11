"""Phase 3 verification engine.

Pipeline (pipeline.py) for one candidate:
  1. textract   – read text from the actual uploaded files (PyMuPDF; Tesseract OCR for scans and photos)
  2. fields     – deterministic field extraction (regex/heuristics), optionally helped by Gemini (gemini.py)
  3. rules      – deterministic comparison rules produce findings; AI never decides a mismatch
  4. face       – YuNet detection + SFace embeddings for enrolment, ID-photo match and rechecks
  5. duplicates – verified-mobile and face-embedding comparisons across consenting candidates
"""
