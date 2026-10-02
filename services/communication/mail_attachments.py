"""Bounded PDF attachments; only inline bytes, never provider-fetched URLs."""
import base64
import binascii
from typing import Literal
from pydantic import BaseModel, Field, field_validator

MAX_PDF_BYTES = 5 * 1024 * 1024

class PdfAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content_type: Literal["application/pdf"] = "application/pdf"
    content: str = Field(min_length=1, max_length=((MAX_PDF_BYTES + 2) // 3) * 4)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value):
        if not value.lower().endswith(".pdf") or any(c in value for c in ("/", "\\")) or any(ord(c) < 32 for c in value):
            raise ValueError("Attachment filename must be a plain PDF filename")
        return value

    @field_validator("content")
    @classmethod
    def pdf_bytes(cls, value):
        try:
            blob = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Attachment must contain valid base64 PDF bytes")
        if len(blob) > MAX_PDF_BYTES or not blob.startswith(b"%PDF-"):
            raise ValueError("Attachment must be a PDF of at most 5 MB")
        return value
