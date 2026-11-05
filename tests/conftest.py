import itertools
import os

import psycopg
import pytest

from aeies.database.queries import Database
from aeies.services.academic_service import AcademicService
from scripts.migrate import migrate
from scripts.bootstrap_admin import bootstrap


@pytest.fixture
def world(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    # Refuse destructive fixtures against Supabase, production, or another local database.
    info = psycopg.conninfo.conninfo_to_dict(url)
    if info.get("dbname") != "aeies_test" or info.get("host") not in (
        "127.0.0.1",
        "localhost",
    ):
        pytest.fail("Integration fixture requires a loopback database named aeies_test")
    migrate(url)
    db = Database(url)
    with db.transaction() as c:
        c.execute(
            "TRUNCATE profiles,courses,academic_sessions,processed_updates RESTART IDENTITY CASCADE"
        )
    service = AcademicService(db, tmp_path)
    ids = itertools.count(1)

    def send(actor, text="", document=None, update_id=None):
        return service.handle(
            actor, next(ids) if update_id is None else update_id, text, document
        )

    def register(actor, dept=1, level=3):
        for text in ("/register", "Test Student", str(dept), str(level), "1"):
            result = send(actor, text)
        return result

    register(900)
    bootstrap(url, 900)
    send(900, "/reference add academic_sessions 2025/2026")
    send(900, "/course add EEE311|Electrical Circuits|1|3|1")
    send(900, "/course add ICE411|Communications|2|4|1")
    register(100)
    register(200, 2, 4)
    register(300)
    send(900, "/roles grant 300 resource_admin 1 3 resources,feedback")
    register(400)
    send(900, "/roles grant 400 executive 1 3 resources,feedback,courses")

    def upload(actor=300, course_id=1, unique="unique-file", dept=1, level=3):
        path = tmp_path / (unique + ".pdf")
        data = b"%PDF-1.4\nTest original file\n%%EOF"
        path.write_bytes(data)
        import hashlib

        doc = {
            "file_id": "telegram-test-file",
            "file_unique_id": unique,
            "file_size": len(data),
            "mime_type": "application/pdf",
            "backup_path": str(path),
            "backup_sha256": hashlib.sha256(data).hexdigest(),
        }
        send(actor, "/upload")
        result = send(actor, document=doc)
        if "duplicate" in result["text"].lower():
            return result
        for value in (
            "Circuit Notes",
            str(dept),
            str(level),
            "1",
            str(course_id),
            "1",
            "1",
            "Written lecture notes",
            "confirm",
        ):
            result = send(actor, value)
        return result

    return type(
        "World",
        (),
        {
            "db": db,
            "service": service,
            "url": url,
            "send": staticmethod(send),
            "register": staticmethod(register),
            "upload": staticmethod(upload),
            "directory": tmp_path,
        },
    )()
