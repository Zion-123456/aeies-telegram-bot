"""Telegram delivery with durable original-file backups behind a storage interface."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import hashlib
import os
import uuid

MAX_UPLOAD = 20 * 1024 * 1024
MIMES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "video/mp4": ".mp4",
}


@dataclass(frozen=True)
class Backup:
    path: str
    sha256: str


class Storage(Protocol):
    async def backup(self, bot, document) -> Backup: ...
    async def deliver(self, bot, chat_id, resource): ...


def validate_document(document):
    if not document.file_size or not 0 < document.file_size <= MAX_UPLOAD:
        raise ValueError("Uploads must be no larger than 20 MB (AEIES policy).")
    if document.mime_type not in MIMES:
        raise ValueError("Please upload a PDF, DOCX, or MP4 as a Telegram document.")
    if Path(document.file_name or "").suffix.lower() != MIMES[document.mime_type]:
        raise ValueError("The filename must match the PDF, DOCX, or MP4 file type.")


class TelegramStorage:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    async def backup(self, bot, document):
        import asyncio

        validate_document(document)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / (uuid.uuid4().hex + MIMES[document.mime_type])
        partial = path.with_suffix(".partial")
        try:
            file = await bot.get_file(document.file_id)
            await file.download_to_drive(partial)
            partial.chmod(0o600)
            digest = await asyncio.to_thread(self._verify, partial, document)
            os.replace(partial, path)
            # Never discard completed originals, even if subsequent metadata publication fails.
            return Backup(str(path), digest)
        finally:
            partial.unlink(missing_ok=True)

    @staticmethod
    def _verify(path, document):
        if (
            path.stat().st_size != document.file_size
            or path.stat().st_size > MAX_UPLOAD
        ):
            raise ValueError("Downloaded file size does not match the upload.")
        data = path.read_bytes()
        if document.mime_type == "application/pdf" and not data.startswith(b"%PDF-"):
            raise ValueError("The uploaded file is not a PDF.")
        if (
            document.mime_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            import zipfile

            if not zipfile.is_zipfile(path):
                raise ValueError("The uploaded file is not a DOCX archive.")
            with zipfile.ZipFile(path) as archive:
                if not {"[Content_Types].xml", "word/document.xml"} <= set(
                    archive.namelist()
                ):
                    raise ValueError("The uploaded file is not a Word document.")
        if document.mime_type == "video/mp4" and (
            len(data) < 12 or data[4:8] != b"ftyp"
        ):
            raise ValueError("The uploaded file is not an MP4 container.")
        return hashlib.sha256(data).hexdigest()

    async def deliver(self, bot, chat_id, resource):
        from datetime import datetime

        uploaded_at = resource["uploaded_at"]
        if isinstance(uploaded_at, str):
            uploaded_at = datetime.fromisoformat(uploaded_at)
        caption = (
            f"{resource['title']}\n{resource['code']} · {resource['category']}\n"
            f"Session: {resource['session']} · Uploaded: {uploaded_at:%Y-%m-%d}\n"
            f"{resource['description']}"
        )[:1024]
        await bot.send_document(
            chat_id=chat_id, document=resource["file_id"], caption=caption
        )
