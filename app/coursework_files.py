"""Private, size-limited storage helpers for course and assignment files."""

from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class CourseworkFileError(ValueError):
    """Raised when an uploaded coursework file cannot be stored safely."""


def storage_directory(kind: str) -> Path:
    configured = current_app.config.get(f"{kind.upper()}_DIR")
    directory = Path(configured or Path(current_app.instance_path) / kind)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_coursework_file(upload: FileStorage, kind: str) -> tuple[str, str]:
    original = secure_filename(upload.filename or "")
    if not original:
        raise CourseworkFileError("Choose a file to upload.")
    suffix = Path(original).suffix.casefold()
    storage_name = f"{uuid4().hex}{suffix}"
    destination = storage_directory(kind) / storage_name
    upload.save(destination)
    maximum = int(current_app.config.get("COURSEWORK_FILE_MAX_BYTES", 10 * 1024 * 1024))
    if destination.stat().st_size > maximum:
        destination.unlink(missing_ok=True)
        raise CourseworkFileError("Files are limited to 10 MB.")
    return storage_name, original


def delete_coursework_file(storage_name: str | None, kind: str) -> None:
    if storage_name:
        (storage_directory(kind) / storage_name).unlink(missing_ok=True)
