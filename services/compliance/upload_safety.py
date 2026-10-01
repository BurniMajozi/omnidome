"""Safe on-disk storage for uploaded / fetched documents.

Nothing client-controlled ever reaches a filesystem path:
  * the tenant directory is the canonical UUID of the authenticated tenant,
  * the stored file name is a random uuid plus an extension from an allow-list,
  * the final path is resolved and must stay inside the upload root,
  * size and (for binary types) magic-byte checks run before anything is written,
  * files are written non-executable and are never executed.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Union

DEFAULT_UPLOAD_ROOT = "/opt/data/uploads/compliance"

ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif",
})

_MAGIC = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
}


class UnsafeUpload(ValueError):
    """The upload (name, type, size or destination) is not acceptable."""


def upload_root() -> Path:
    return Path(os.getenv("COMPLIANCE_UPLOAD_DIR", DEFAULT_UPLOAD_ROOT))


def max_upload_bytes() -> int:
    try:
        mb = float(os.getenv("COMPLIANCE_MAX_UPLOAD_MB", "25"))
    except ValueError:
        mb = 25.0
    return int(mb * 1024 * 1024)


def tenant_dir_name(tenant_id: Union[str, uuid.UUID]) -> str:
    """Canonical lower-case UUID text; anything that is not a UUID is refused."""
    try:
        return str(uuid.UUID(str(tenant_id)))
    except (ValueError, AttributeError, TypeError):
        raise UnsafeUpload("Invalid tenant for file storage") from None


def safe_extension(filename: str | None) -> str:
    """Extension from the allow-list, derived from the base name only."""
    raw = (filename or "").replace("\x00", "")
    base = PureWindowsPath(PurePosixPath(raw).name).name  # strips / and \ directories
    ext = os.path.splitext(base)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsafeUpload(f"File type {ext or '(none)'} is not allowed")
    return ext


def display_name(filename: str | None) -> str:
    """A harmless label for the UI (never used as a path)."""
    raw = (filename or "").replace("\x00", "")
    base = PureWindowsPath(PurePosixPath(raw).name).name
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')[:200]
    return cleaned or "Untitled"


def is_within(path: Union[str, Path], root: Union[str, Path]) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def check_content(ext: str, content: bytes) -> None:
    if not content:
        raise UnsafeUpload("Empty file")
    if len(content) > max_upload_bytes():
        raise UnsafeUpload("File is too large")
    magics = _MAGIC.get(ext)
    if magics and not content.startswith(magics):
        raise UnsafeUpload("File content does not match its extension")


def build_upload_path(tenant_id: Union[str, uuid.UUID], filename: str | None, root: Union[str, Path, None] = None) -> Path:
    """Resolved destination path: <root>/<tenant uuid>/<random uuid><allowed ext>."""
    base = Path(root) if root is not None else upload_root()
    ext = safe_extension(filename)
    tenant_dir = base / tenant_dir_name(tenant_id)
    if tenant_dir.is_symlink():
        raise UnsafeUpload("Tenant storage directory is not a plain directory")
    dest = (tenant_dir / f"{uuid.uuid4().hex}{ext}").resolve()
    if not dest.is_relative_to(base.resolve()):
        raise UnsafeUpload("Destination escapes the upload root")
    return dest


def write_upload(tenant_id: Union[str, uuid.UUID], filename: str | None, content: bytes, root: Union[str, Path, None] = None) -> Path:
    """Validate and store `content`; returns the stored path. Blocking (run in a thread)."""
    ext = safe_extension(filename)
    check_content(ext, content)
    dest = build_upload_path(tenant_id, filename, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.parent.is_symlink() or not is_within(dest.parent, root if root is not None else upload_root()):
        raise UnsafeUpload("Destination escapes the upload root")
    with open(dest, "xb") as fh:  # exclusive create: never overwrite an existing file
        fh.write(content)
    try:
        os.chmod(dest, 0o640)  # not executable
    except OSError:
        pass
    return dest
