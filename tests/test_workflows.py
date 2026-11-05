from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from aeies.database.queries import one, rows, Database, DatabaseUnavailable
from aeies.services.academic_service import AcademicService
from aeies.services.storage_service import (
    TelegramStorage,
    validate_document,
    MAX_UPLOAD,
)
from aeies.handlers.router import handle_update, retry_rate_limit
from telegram.error import RetryAfter, BadRequest


def test_registration_and_profile_updates(world):
    world.register(101, 2, 4)
    result = world.send(101, "/profile")
    assert "Communication" in result["text"] and "400L" in result["text"]
    world.register(101, 1, 3)
    assert "300L" in world.send(101, "/profile")["text"]


def test_invalid_selection_and_registration_gate(world):
    assert "complete /register" in world.send(777, "/recent")["text"]
    world.send(777, "/register")
    world.send(777, "New Student")
    assert "unavailable" in world.send(777, "999")["text"]
    assert "academic level" in world.send(777, "1")["text"]


@pytest.mark.parametrize(
    "student,department,level,course_code,course_id",
    [(100, 1, 3, "EEE311", 1), (200, 2, 4, "ICE411", 2)],
)
def test_department_course_and_resource_browsing(
    world, student, department, level, course_code, course_id
):
    world.upload(900, course_id, unique=course_code, dept=department, level=level)
    world.send(student, "/browse")
    for value in (str(department), str(level), "1"):
        result = world.send(student, value)
    assert any(course_code in label for label, _ in result["buttons"])
    world.send(student, str(course_id))
    result = world.send(student, "1")
    assert course_code in result["text"]


@pytest.mark.parametrize("query", ["EEE311", "Electrical Circuits", "Circuit Notes"])
def test_search_by_code_course_and_resource_title(world, query):
    world.upload()
    assert "Circuit Notes" in world.send(100, "/search " + query)["text"]


def test_search_missing_and_wildcards(world):
    assert "not have been onboarded" in world.send(100, "/search absent")["text"]
    assert ("Request missing resource", "/request") in world.send(100, "/search %")[
        "buttons"
    ]


def test_bookmark_unique_remove_and_open(world):
    world.upload()
    world.send(100, "/save 1")
    world.send(100, "/save 1")
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM bookmarks")["n"] == 1
    assert "Circuit Notes" in world.send(100, "/bookmarks")["text"]
    assert world.send(100, "/open 1")["delivery"]["file_id"] == "telegram-test-file"
    world.send(100, "/unsave 1")
    assert "No resources" in world.send(100, "/bookmarks")["text"]


def test_student_cannot_upload_or_modify(world):
    assert "authorized" in world.send(100, "/upload")["text"]
    world.upload()
    assert "permission" in world.send(100, "/archive 1")["text"]
    with pytest.raises(ValueError):
        world.service.upload_allowed(100)


def test_scoped_upload_and_cross_scope_denial(world):
    assert "Published" in world.upload()["text"]
    world.upload(900, 2, "ice-file", 2, 4)
    assert "permission" in world.send(300, "/archive 2")["text"]
    assert "permission" in world.send(300, "/edit 1 course_id 2")["text"]
    assert "updated" in world.send(300, "/archive 1")["text"]
    assert "unavailable" in world.send(100, "/open 1")["text"]
    assert "updated" in world.send(300, "/restore 1")["text"]


def test_executive_permissions_and_role_escalation_denied(world):
    world.upload()
    assert "updated" in world.send(400, "/edit 1 title Executive Notes")["text"]
    assert "permission" in world.send(400, "/roles grant 100 super * * roles")["text"]
    assert "permission" in world.send(400, "/reference add semesters Extra")["text"]
    assert "updated" in world.send(400, "/course edit 1 title Revised Circuits")["text"]
    assert "permission" in world.send(400, "/course edit 2 title Other")["text"]


def test_duplicate_upload_and_audit(world):
    world.upload()
    result = world.upload()
    assert "duplicate" in result["text"].lower()
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM resources")["n"] == 1
        assert (
            one(c, "SELECT count(*) n FROM audit_logs WHERE action='publish'")["n"] == 1
        )


def test_feedback_submission_queue_status_assignment_and_privacy(world):
    world.send(100, "/feedback")
    world.send(100, "Incorrect course information")
    result = world.send(100, "The title should be reviewed.")
    ref = result["text"].split("Reference: ")[1].split("\n")[0]
    assert ref in world.send(300, "/feedbackqueue")["text"]
    assert "New" in world.send(100, "/track " + ref)["text"]
    assert "not found or unavailable" in world.send(200, "/track " + ref)["text"]
    assert "updated" in world.send(300, "/status " + ref + "|Under Review|400")["text"]
    assert "Under Review" in world.send(100, "/track " + ref)["text"]
    assert "permission" in world.send(200, "/status " + ref + "|Resolved")["text"]
    world.send(300, "/status " + ref + "|Resolved")
    assert "Resolved" in world.send(100, "/track " + ref)["text"]
    with world.db.transaction() as c:
        assert (
            one(c, "SELECT count(*) n FROM audit_logs WHERE action='feedback_status'")[
                "n"
            ]
            == 2
        )


def test_missing_resource_request_and_resource_report(world):
    world.send(100, "/request")
    assert "Reference:" in world.send(100, "Please add EEE312 lecture notes")["text"]
    world.upload()
    world.send(100, "/report 1")
    world.send(100, "Broken resource")
    world.send(100, "File does not open.")
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM resource_reports")["n"] == 1
        assert (
            one(c, "SELECT count(*) n FROM feedback WHERE kind='Missing resource'")["n"]
            == 1
        )


def test_feedback_scoping(world):
    world.send(200, "/request")
    ref = (
        world.send(200, "Please add ICE resources")["text"]
        .split("Reference: ")[1]
        .split("\n")[0]
    )
    assert ref not in world.send(300, "/feedbackqueue")["text"]
    assert "permission" in world.send(300, "/submission " + ref)["text"]


def test_update_idempotency_and_restart_recovery(world):
    world.send(100, "/request")
    first = world.send(100, "A missing resource", update_id=90001)
    restarted = AcademicService(Database(world.url), world.directory)
    assert restarted.handle(100, 90001, "A missing resource") == first
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM feedback")["n"] == 1
    world.send(100, "/register")
    world.send(100, "Updated Student")
    assert "academic level" in restarted.handle(100, 90002, "2")["text"]


def test_expired_callback_and_resume(world):
    world.send(100, "/register")
    department = world.send(100, "Changed Student")
    callback = department["buttons"][0][1]
    assert "academic level" in world.send(100, callback)["text"]
    assert "expired" in world.send(100, callback)["text"]
    assert "Resume" in world.send(100, "/resume")["text"]


def test_original_backup_copy(tmp_path):
    from scripts.backup_originals import backup_originals

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.pdf").write_bytes(b"%PDF-original")
    (source / "incomplete.partial").write_bytes(b"partial")
    target, count = backup_originals(source, tmp_path / "external")
    assert count == 1 and (target / "a.pdf").read_bytes() == b"%PDF-original"
    assert (source / "a.pdf").exists()
    assert (target / "manifest.json").exists()
    with pytest.raises(ValueError):
        backup_originals(source, source / "nested")


def test_interleaved_users_and_concurrent_students(world):
    for actor in (501, 502):
        world.send(actor, "/register")
    world.send(501, "Student One")
    world.send(502, "Student Two")
    world.send(501, "1")
    world.send(502, "2")
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(world.service.handle, actor, 91000 + actor, "3")
            for actor in (501, 502)
        ]
        assert all("semester" in f.result()["text"] for f in futures)
    world.send(501, "1")
    world.send(502, "1")
    with world.db.transaction() as c:
        a = one(c, "SELECT * FROM profiles WHERE id=501")
        b = one(c, "SELECT * FROM profiles WHERE id=502")
        assert a["department_id"] == 1 and b["department_id"] == 2
        assert a["full_name"] == "Student One" and b["full_name"] == "Student Two"


def test_invalid_input_preserves_upload_step(world):
    world.send(300, "/upload")
    assert "send a PDF" in world.send(300, "text")["text"]
    assert world.upload()["text"].startswith("Published")


def test_course_management_and_duplicate(world):
    assert (
        "updated"
        in world.send(900, "/course add CPE311|Computer Systems|3|3|1")["text"]
    )
    from aeies.database.queries import Duplicate

    with pytest.raises(Duplicate):
        world.send(900, "/course add CPE311|Computer Systems|3|3|1")
    assert "updated" in world.send(900, "/course archive 3")["text"]
    assert "updated" in world.send(900, "/course restore 3")["text"]
    assert (
        "consecutive"
        in world.send(900, "/reference add academic_sessions 2025/2030")["text"]
    )


def test_course_search_without_resources(world):
    assert any(
        "EEE311" in label
        for label, _ in world.send(100, "/courses Electrical")["buttons"]
    )
    assert any(
        "ICE411" in label for label, _ in world.send(200, "/courses ICE411")["buttons"]
    )
    assert "Choose a category" in world.send(100, "/browsecourse 1")["text"]


def test_archived_management_scope_and_revocation(world):
    world.upload()
    world.upload(900, 2, "ice-admin", 2, 4)
    world.send(300, "/archive 1")
    result = world.send(300, "/manage")
    assert "archived" in result["text"] and "ICE411" not in result["text"]
    assert ("Restore #1", "/restore 1") in result["buttons"]
    assert "permission" in world.send(100, "/manage")["text"]
    with world.db.transaction() as c:
        role = one(c, "SELECT id FROM admin_roles WHERE profile_id=300")["id"]
    world.send(900, "/roles revoke " + str(role))
    assert "permission" in world.send(300, "/page 0")["text"]


def test_publication_rolls_back_when_audit_fails(world):
    # Exercise an actual database failure after INSERT resources, before commit.
    from unittest.mock import patch

    with patch(
        "aeies.services.academic_service.audit", side_effect=RuntimeError("test fault")
    ):
        with pytest.raises(RuntimeError):
            world.upload()
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM resources")["n"] == 0
        state = one(c, "SELECT state FROM conversations WHERE profile_id=300")["state"]
        assert state["step"] == "upload_confirm"
    assert list(world.directory.glob("*.pdf"))
    assert "Published" in world.send(300, "confirm")["text"]


def test_metrics_only_confirmed_deliveries(world):
    world.upload()
    world.send(100, "/open 1")
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM access_events")["n"] == 0
    world.service.record_delivery(100, 1, 92000)
    world.service.record_delivery(100, 1, 92000)
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM access_events")["n"] == 1
    assert "Confirmed deliveries" in world.send(900, "/analytics")["text"]
    assert "permission" in world.send(100, "/analytics")["text"]


def test_safe_pagination(world):
    for i in range(8):
        world.upload(unique=f"file-{i}")
    assert ("Next", "/page 1") in world.send(100, "/recent")["buttons"]
    second = world.send(100, "/page 1")
    assert ("Previous", "/page 0") in second["buttons"]
    assert ("Next", "/page 2") not in second["buttons"]
    assert "Invalid page" in world.send(100, "/page -1")["text"]


def test_last_super_cannot_be_revoked(world):
    with world.db.transaction() as c:
        role = one(c, "SELECT id FROM admin_roles WHERE role='super'")["id"]
    assert "last super" in world.send(900, "/roles revoke " + str(role))["text"]


def test_migrations_repeatable_and_rls(world):
    from scripts.migrate import migrate
    from scripts.verify_database import verify

    migrate(world.url)
    verify(world.url)
    with world.db.transaction() as c:
        tables = rows(
            c,
            "SELECT relname,relrowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='aeies' AND relkind='r'",
        )
        assert {t["relname"] for t in tables} == {
            "departments",
            "academic_levels",
            "semesters",
            "academic_sessions",
            "courses",
            "resource_categories",
            "profiles",
            "admin_roles",
            "resources",
            "bookmarks",
            "resource_reports",
            "feedback",
            "audit_logs",
            "access_events",
            "conversations",
            "processed_updates",
        }
        assert all(t["relrowsecurity"] for t in tables)
        c.execute("SET LOCAL ROLE aeies_backend")
        assert one(c, "SELECT count(*) n FROM profiles")["n"] >= 5
    with world.db.transaction() as c:
        c.execute("SET LOCAL ROLE aeies_backend")
        import psycopg

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with c.transaction():
                c.execute("DELETE FROM audit_logs")


def test_database_foreign_key_checks_and_duplicate_bookmarks(world):
    import psycopg

    with world.db.transaction() as c:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with c.transaction():
                c.execute(
                    "INSERT INTO bookmarks(profile_id,resource_id) VALUES (100,999999)"
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with c.transaction():
                c.execute(
                    "INSERT INTO courses(code,title,department_id,level_id,semester_id) VALUES ('invalid','Bad',1,3,1)"
                )


def test_database_errors_hide_credentials():
    with pytest.raises(DatabaseUnavailable) as exc:
        with Database(
            "postgresql://private:private@127.0.0.1:1/absent?connect_timeout=1"
        ).transaction():
            pass
    assert "private" not in str(exc.value)


def test_remote_database_requires_verified_tls():
    from aeies.database.queries import connect
    from unittest.mock import patch

    with pytest.raises(ValueError, match="verify-full"):
        connect("postgresql://example.invalid/db?sslmode=disable")
    with patch("aeies.database.queries.psycopg.connect") as mocked:
        connect("postgresql://example.invalid/db")
        assert mocked.call_args.kwargs["sslmode"] == "verify-full"
        assert mocked.call_args.kwargs["sslrootcert"]


def test_full_workflow_with_restricted_backend_role(world):
    from psycopg.conninfo import make_conninfo

    runtime = AcademicService(
        Database(make_conninfo(world.url, options="-c role=aeies_backend")),
        world.directory,
    )
    profile = runtime.handle(100, 98000, "/profile")["text"]
    assert "Test Student" in profile and "300L" in profile
    assert (
        "Course #"
        in runtime.handle(900, 98001, "/course add EEE312|More Circuits|1|3|1")["text"]
    )
    assert "Reference:" not in runtime.handle(100, 98002, "/request")["text"]
    assert (
        "Reference:"
        in runtime.handle(100, 98003, "Please add notes for EEE312")["text"]
    )


@pytest.mark.parametrize(
    "size,mime,name",
    [
        (MAX_UPLOAD + 1, "application/pdf", "a.pdf"),
        (1, "text/plain", "a.txt"),
        (10, "application/pdf", "a.exe"),
        (None, "application/pdf", "a.pdf"),
    ],
)
def test_upload_validation(size, mime, name):
    with pytest.raises(ValueError):
        validate_document(
            SimpleNamespace(file_size=size, mime_type=mime, file_name=name)
        )


@pytest.mark.asyncio
async def test_storage_backup_and_mock_delivery(tmp_path):
    data = b"%PDF-1.4\ntest\n%%EOF"

    async def download(path):
        path.write_bytes(data)

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download)),
        send_document=AsyncMock(),
    )
    doc = SimpleNamespace(
        file_id="mock-file",
        file_unique_id="unique",
        file_size=len(data),
        mime_type="application/pdf",
        file_name="notes.pdf",
    )
    storage = TelegramStorage(tmp_path)
    backup = await storage.backup(bot, doc)
    from pathlib import Path

    assert Path(backup.path).read_bytes() == data
    assert len(backup.sha256) == 64
    await storage.deliver(
        bot,
        100,
        dict(
            title="Notes",
            code="EEE311",
            category="Lecture notes",
            session="2025/2026",
            description="Description",
            uploaded_at="2026-11-05T00:00:00+00:00",
            file_id="mock-file",
        ),
    )
    assert bot.send_document.call_args.kwargs["document"] == "mock-file"


@pytest.mark.asyncio
async def test_corrupt_backup_not_published(tmp_path):
    async def download(path):
        path.write_bytes(b"not pdf")

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download))
    )
    doc = SimpleNamespace(
        file_id="mock", file_size=7, mime_type="application/pdf", file_name="a.pdf"
    )
    with pytest.raises(ValueError, match="not a PDF"):
        await TelegramStorage(tmp_path).backup(bot, doc)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mime,filename",
    [
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "notes.docx",
        ),
        ("video/mp4", "lecture.mp4"),
    ],
)
async def test_docx_and_mp4_original_backups(tmp_path, mime, filename):
    import io
    import zipfile

    if mime == "video/mp4":
        data = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<document/>")
        data = buffer.getvalue()

    async def download(path):
        path.write_bytes(data)

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download))
    )
    doc = SimpleNamespace(
        file_id="mock", file_size=len(data), mime_type=mime, file_name=filename
    )
    result = await TelegramStorage(tmp_path).backup(bot, doc)
    from pathlib import Path

    assert Path(result.path).read_bytes() == data


def test_mp4_publication_and_audit_details(world):
    import hashlib

    data = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
    path = world.directory / "video.mp4"
    path.write_bytes(data)
    world.send(300, "/upload")
    world.send(
        300,
        document={
            "file_id": "video-document-id",
            "file_unique_id": "unique-video",
            "file_size": len(data),
            "mime_type": "video/mp4",
            "backup_path": str(path),
            "backup_sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    for value in (
        "Educational lecture",
        "1",
        "3",
        "1",
        "1",
        "4",
        "1",
        "Video lecture",
        "confirm",
    ):
        result = world.send(300, value)
    assert "Published" in result["text"]
    assert world.send(100, "/open 1")["delivery"]["file_id"] == "video-document-id"
    assert "actor" in world.send(900, "/audit")["text"]


@pytest.mark.asyncio
async def test_rate_limit_backoff(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("aeies.handlers.router.asyncio.sleep", sleep)
    operation = AsyncMock(side_effect=[RetryAfter(1), "sent"])
    assert await retry_rate_limit(operation) == "sent"
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_mock_telegram_router_and_delivery(world):
    world.upload()
    message = SimpleNamespace(text="/open 1", document=None, reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=100),
        effective_chat=SimpleNamespace(id=100, type="private"),
        callback_query=None,
        update_id=99000,
    )
    storage = SimpleNamespace(deliver=AsyncMock())
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"service": world.service, "storage": storage}
        ),
        bot=object(),
    )
    await handle_update(update, context)
    storage.deliver.assert_awaited_once()
    message.reply_text.assert_awaited_once()
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM access_events")["n"] == 1


@pytest.mark.asyncio
async def test_failed_delivery_not_counted(world):
    world.upload()
    message = SimpleNamespace(text="/open 1", document=None, reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=100),
        effective_chat=SimpleNamespace(id=100, type="private"),
        callback_query=None,
        update_id=99001,
    )
    storage = SimpleNamespace(deliver=AsyncMock(side_effect=BadRequest("file missing")))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"service": world.service, "storage": storage}
        ),
        bot=object(),
    )
    await handle_update(update, context)
    assert "/report 1" in message.reply_text.call_args.args[0]
    with world.db.transaction() as c:
        assert one(c, "SELECT count(*) n FROM access_events")["n"] == 0
