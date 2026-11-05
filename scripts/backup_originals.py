"""Copy original files to a new backup directory and verify checksums; never deletes originals."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from dotenv import load_dotenv


def backup_originals(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    checkout = Path(__file__).resolve().parents[1]
    if (
        destination == source
        or destination.is_relative_to(source)
        or destination.is_relative_to(checkout)
    ):
        raise ValueError(
            "Choose a backup destination outside the checkout and source directory."
        )
    if not source.is_dir():
        raise ValueError("Original-file directory does not exist.")
    target = destination / (
        "aeies-originals-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    target.mkdir(parents=True)
    manifest = {}
    for path in source.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix not in (".pdf", ".docx", ".mp4")
        ):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        copied = target / path.name
        shutil.copy2(path, copied)
        if hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
            raise ValueError("Backup verification failed. Originals are unchanged.")
        manifest[path.name] = digest
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return target, len(manifest)


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        target, count = backup_originals(
            os.getenv("BACKUP_DIRECTORY", "backups/originals"), args.destination
        )
        print(f"Copied and checksum-verified {count} original files to {target}")
    except (ValueError, OSError):
        parser.exit(
            1,
            "Backup failed. Check the source directory, destination, and free disk space; originals were not removed.\n",
        )
