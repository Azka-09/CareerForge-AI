"""Upload validation. Returns (ok, message) so the UI can show a clear error."""
import os

ALLOWED_EXT = {".pdf", ".docx"}


def validate_upload(filename: str, data: bytes, max_mb: int = 5) -> tuple[bool, str]:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        return False, "Unsupported format. Please upload a PDF or DOCX file."
    if not data:
        return False, "The file is empty."
    if len(data) > max_mb * 1024 * 1024:
        return False, f"File is larger than {max_mb} MB."
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        return False, "This does not look like a valid PDF."
    if ext == ".docx" and not data.startswith(b"PK"):
        return False, "This does not look like a valid DOCX."
    return True, ""
