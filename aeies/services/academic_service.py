"""Transactional use cases. All user IDs come from Telegram, never callback payloads."""

import copy
import re
import hashlib
import secrets
from pathlib import Path

from psycopg.types.json import Jsonb
from aeies.database.queries import one, rows
from aeies.services.permission_service import require, require_student, Denied
from aeies.services.storage_service import MAX_UPLOAD, MIMES

PAGE_SIZE = 6
REFERENCE_TABLES = {
    "departments",
    "academic_levels",
    "semesters",
    "academic_sessions",
    "resource_categories",
}
KINDS = [
    "Missing resource",
    "Incorrect resource",
    "Broken resource",
    "Outdated material",
    "Incorrect course information",
    "Suggestion",
    "General feedback",
]
STATUSES = ["New", "Under Review", "Resolved", "Declined"]
RESOURCE_SELECT = """SELECT r.*,c.code,c.title AS course_title,c.department_id,c.level_id,c.semester_id,
 cat.name AS category,s.name AS session FROM resources r JOIN courses c ON c.id=r.course_id
 JOIN resource_categories cat ON cat.id=r.category_id JOIN academic_sessions s ON s.id=r.session_id"""


def answer(text, buttons=None, **extra):
    return {"text": text, "buttons": buttons or [], **extra}


def clean(value, minimum=2, maximum=200):
    value = str(value).strip()
    if not minimum <= len(value) <= maximum or any(
        ord(c) < 32 and c != "\n" for c in value
    ):
        raise ValueError(f"Please enter between {minimum} and {maximum} characters.")
    return value


def identifier(value):
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise ValueError("Please choose a valid numeric ID.") from None
    if not 0 < number < 2**63:
        raise ValueError("Please choose a valid numeric ID.")
    return number


def audit(c, actor, action, entity, entity_id, details=None):
    c.execute(
        "INSERT INTO audit_logs(actor_id,action,entity,entity_id,details) VALUES (%s,%s,%s,%s,%s)",
        (actor, action, entity, entity_id, Jsonb(details or {})),
    )


def reference(c, table, value):
    if table not in REFERENCE_TABLES:
        raise ValueError("Unknown reference data type.")
    row = one(
        c,
        f"SELECT * FROM {table} WHERE id=%s AND NOT archived FOR SHARE",
        (identifier(value),),
    )
    if not row:
        raise ValueError(
            "That selection is unavailable. Choose an active entry from /catalog."
        )
    return row


def course(c, value, active=True):
    row = one(c, "SELECT * FROM courses WHERE id=%s FOR SHARE", (identifier(value),))
    if not row or (active and row["archived"]):
        raise ValueError(
            "That course has not been onboarded. Use /request to request it."
        )
    return row


def resource(c, value, published=True):
    row = one(
        c,
        RESOURCE_SELECT + " WHERE r.id=%s FOR UPDATE OF r FOR SHARE OF c",
        (identifier(value),),
    )
    if not row or (published and row["status"] != "published"):
        raise ValueError(
            "That resource is unavailable. Use /request or /report for help."
        )
    return row


class AcademicService:
    def __init__(self, database, backup_directory):
        self.database = database
        self.backup_directory = Path(backup_directory).resolve()

    def handle(self, actor, update_id, text="", document=None):
        actor = identifier(actor)
        with self.database.transaction() as c:
            # Serialize a student's concurrent updates across workers and restarts.
            c.execute("SELECT pg_advisory_xact_lock(%s)", (actor,))
            previous = one(
                c,
                "SELECT response FROM processed_updates WHERE update_id=%s",
                (update_id,),
            )
            if previous:
                cached = previous["response"]
                if cached.get("_actor") != actor:
                    raise Denied(
                        "This update cannot be replayed. Please repeat your action."
                    )
                return cached["result"]
            c.execute(
                "INSERT INTO profiles(id) VALUES (%s) ON CONFLICT DO NOTHING", (actor,)
            )
            old = one(
                c, "SELECT state FROM conversations WHERE profile_id=%s", (actor,)
            )
            state = copy.deepcopy(old["state"]) if old else {}
            # A savepoint keeps invalid inputs from discarding an in-progress conversation.
            try:
                with c.transaction():
                    if text.startswith("pick:"):
                        parts = text.split(":")
                        if (
                            len(parts) != 3
                            or parts[1] != state.get("_nonce")
                            or not parts[2].isdigit()
                        ):
                            raise ValueError(
                                "That selection has expired. Use /resume for the current workflow."
                            )
                        index = int(parts[2])
                        choices = state.get("_choices", [])
                        if not 0 <= index < len(choices):
                            raise ValueError("Invalid selection. Use /resume.")
                        text = choices[index]
                    state.pop("_nonce", None)
                    state.pop("_choices", None)
                    result = self.route(c, actor, text.strip(), document, state)
            except ValueError as exc:
                result = answer(str(exc), [("Cancel", "/cancel")])
                # route mutates state; only persist it following a successful operation.
                state = old["state"] if old else {}
            choices = [
                data[6:] for _, data in result["buttons"] if data.startswith("input:")
            ]
            if choices:
                nonce = secrets.token_hex(4)
                state.update(_choices=choices, _nonce=nonce)
                index = iter(range(len(choices)))
                result["buttons"] = [
                    (
                        label,
                        f"pick:{nonce}:{next(index)}"
                        if data.startswith("input:")
                        else data,
                    )
                    for label, data in result["buttons"]
                ]
            c.execute(
                "INSERT INTO conversations(profile_id,state) VALUES (%s,%s) "
                "ON CONFLICT(profile_id) DO UPDATE SET state=excluded.state,updated_at=now()",
                (actor, Jsonb(state)),
            )
            c.execute(
                "INSERT INTO processed_updates(update_id,response) VALUES (%s,%s)",
                (update_id, Jsonb({"_actor": actor, "result": result})),
            )
            return result

    def upload_allowed(self, actor):
        with self.database.transaction() as c:
            require_student(c, actor)
            roles = rows(
                c, "SELECT * FROM admin_roles WHERE profile_id=%s AND active", (actor,)
            )
            if not any(
                r["role"] == "super" or "resources" in r["permissions"] for r in roles
            ):
                raise Denied("Only authorized resource administrators may upload.")
            current = one(
                c, "SELECT state FROM conversations WHERE profile_id=%s", (actor,)
            )
            if not current or current["state"].get("step") != "upload_document":
                raise ValueError("Use /upload before sending a document.")

    @staticmethod
    def menu():
        return answer(
            "AEIES Academic Assistant — choose an option.",
            [
                ("Browse resources", "/browse"),
                ("Search resources", "/search"),
                ("My bookmarks", "/bookmarks"),
                ("Recently added", "/recent"),
                ("Request a resource", "/request"),
                ("Feedback and support", "/feedback"),
                ("My profile", "/profile"),
                ("Help", "/help"),
            ],
        )

    def route(self, c, actor, text, document, state):
        command, _, arg = text.partition(" ")
        command = command.split("@")[0].lower()
        if command in ("/cancel", "/menu"):
            state.clear()
            return self.menu()
        if command == "/help":
            return answer(
                "Register with /register or update with /register. Browse /browse, search /search, "
                "course catalogue /courses [query], "
                "recent /recent, bookmarks /bookmarks. Request /request, feedback /feedback, "
                "report /report RESOURCE_ID. Track /track REFERENCE. /cancel exits any workflow. "
                "/resume shows your saved workflow step. Administrators: /admin. This is not university identity verification."
            )
        if command == "/resume":
            return self.resume(c, state)
        if command in ("/start", "/register"):
            profile = one(c, "SELECT * FROM profiles WHERE id=%s", (actor,))
            if command == "/start" and profile["full_name"]:
                state.clear()
                return self.menu()
            state.clear()
            state["step"] = "register_name"
            return answer(
                "Welcome to AEIES. Discover, save, and request academic resources. "
                "Registration is required; we do not verify university enrolment. Enter your full name:"
            )
        if state.get("step", "").startswith("register_") and not command.startswith(
            "/"
        ):
            return self.registration(c, actor, text, state)
        profile = require_student(c, actor)
        if command == "/profile":
            p = one(
                c,
                "SELECT p.full_name,d.name department,l.name level,s.name semester FROM profiles p "
                "JOIN departments d ON d.id=p.department_id JOIN academic_levels l ON l.id=p.level_id "
                "LEFT JOIN semesters s ON s.id=p.semester_id WHERE p.id=%s",
                (actor,),
            )
            return answer(
                f"{p['full_name']}\n{p['department']} · {p['level']}\nSemester: {p['semester'] or 'Not selected'}\nYour Telegram ID: {actor}",
                [("Update profile", "/register"), ("Main menu", "/menu")],
            )
        if command == "/catalog":
            return self.catalog(c)
        if command in ("/courses", "/coursepage"):
            if command == "/courses":
                state.clear()
                state.update(course_query=clean(arg, 1, 100) if arg else "")
                page = 0
            else:
                page = self.page_number(arg)
            query = (
                state.get("course_query", "")
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            found = rows(
                c,
                "SELECT id,code,title,department_id,level_id FROM courses WHERE NOT archived AND (code ILIKE %s OR title ILIKE %s) ORDER BY code,id LIMIT %s OFFSET %s",
                ("%" + query + "%", "%" + query + "%", PAGE_SIZE + 1, page * PAGE_SIZE),
            )
            buttons = [
                (f"{r['code']} — {r['title']}", f"/browsecourse {r['id']}")
                for r in found[:PAGE_SIZE]
            ]
            if page:
                buttons.append(("Previous", f"/coursepage {page - 1}"))
            if len(found) > PAGE_SIZE:
                buttons.append(("Next", f"/coursepage {page + 1}"))
            return answer(
                "Choose a course:"
                if found
                else "No courses found. Use /request to request onboarding.",
                buttons,
            )
        if command == "/browsecourse":
            selected = course(c, arg)
            state.clear()
            state.update(step="browse_category", filters={"course_id": selected["id"]})
            return self.choices(c, "resource_categories", "Choose a category:")
        if command == "/manage":
            self.require_any(c, actor, "resources")
            state.clear()
            state.update(mode="manage", query=clean(arg, 1, 100) if arg else "")
            return self.list_resources(c, actor, state, 0)
        if command == "/admin":
            roles = rows(
                c,
                "SELECT id,role,department_id,level_id,permissions FROM admin_roles WHERE profile_id=%s AND active",
                (actor,),
            )
            if not roles:
                raise Denied("Administrator access required.")
            return answer(
                "Admin commands:\n/upload — guided upload\n/edit ID field value\n/archive ID · /restore ID\n"
                "/course — course management\n/roles — scoped role management\n/reference — reference data\n"
                "/feedbackqueue [page]\n/submission REFERENCE\n/status REF|STATUS|ASSIGNEE_ID (optional)\n"
                "/manage [search] — resources including archived\n/analytics · /audit\n/catalog — selection IDs\nOnly assigned permissions and scopes apply.",
                [
                    ("Upload", "/upload"),
                    ("Feedback queue", "/feedbackqueue"),
                    ("Analytics", "/analytics"),
                ],
            )
        if command == "/upload":
            roles = rows(
                c, "SELECT * FROM admin_roles WHERE profile_id=%s AND active", (actor,)
            )
            if not any(
                r["role"] == "super" or "resources" in r["permissions"] for r in roles
            ):
                raise Denied("Only authorized resource administrators may upload.")
            state.clear()
            state["step"] = "upload_document"
            return answer(
                "Send a PDF, DOCX, or MP4 as a document/file, up to 20 MB. The original is backed up before publication. /cancel to stop."
            )
        if state.get("step", "").startswith("upload_") and (
            document or not command.startswith("/")
        ):
            return self.upload(c, actor, text, document, state)
        if command == "/browse":
            state.clear()
            state.update(step="browse_department", filters={})
            return self.choices(c, "departments", "Choose a department:")
        if state.get("step", "").startswith("browse_") and not command.startswith("/"):
            return self.browse(c, actor, text, state)
        if command in ("/search", "/recent", "/bookmarks"):
            state.clear()
            state["mode"] = command[1:]
            if command == "/search" and not arg:
                state["step"] = "search"
                return answer("Enter a course code, course title, or resource title:")
            state["query"] = clean(arg, 1, 100) if command == "/search" else ""
            return self.list_resources(c, actor, state, 0)
        if state.get("step") == "search" and not command.startswith("/"):
            state.update(query=clean(text, 1, 100), step="")
            return self.list_resources(c, actor, state, 0)
        if command == "/page":
            page = self.page_number(arg)
            return self.list_resources(c, actor, state, page)
        if command in ("/open", "/save", "/unsave", "/archive", "/restore", "/edit"):
            return self.resource_action(c, actor, command, arg)
        if command in ("/feedback", "/request", "/report"):
            state.clear()
            state["step"] = "feedback_kind"
            if command == "/request":
                state.update(kind="Missing resource", step="feedback_body")
                return answer(
                    "Describe the missing course or resource, including course code and academic scope:"
                )
            if command == "/report":
                r = resource(c, arg, False)
                state["resource_id"] = r["id"]
            return answer(
                "Choose a feedback category:",
                [(kind, "input:" + kind) for kind in KINDS],
            )
        if state.get("step", "").startswith("feedback_") and not command.startswith(
            "/"
        ):
            if state["step"] == "feedback_kind":
                if text not in KINDS:
                    raise ValueError("Choose a listed feedback category.")
                state.update(kind=text, step="feedback_body")
                return answer(
                    "Describe the issue or suggestion (3–2000 characters). Do not include passwords or sensitive personal information."
                )
            body = clean(text, 3, 2000)
            department, level = profile["department_id"], profile["level_id"]
            if state.get("resource_id"):
                r = resource(c, state["resource_id"], False)
                department, level = r["department_id"], r["level_id"]
            f = one(
                c,
                "INSERT INTO feedback(profile_id,department_id,level_id,kind,body) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (actor, department, level, state["kind"], body),
            )
            if state.get("resource_id"):
                c.execute(
                    "INSERT INTO resource_reports(feedback_id,resource_id) VALUES (%s,%s)",
                    (f["id"], state["resource_id"]),
                )
            state.clear()
            return answer(
                f"Saved. Reference: {f['reference']}\nStatus: New\nUse /track {f['reference']} to check progress."
            )
        if command in ("/track", "/submission", "/status", "/feedbackqueue"):
            return self.feedback_admin(c, actor, command, arg)
        if command == "/course":
            return self.manage_course(c, actor, arg)
        if command == "/roles":
            return self.manage_roles(c, actor, arg)
        if command == "/reference":
            return self.manage_reference(c, actor, arg)
        if command == "/analytics":
            return self.analytics(c, actor)
        if command == "/audit":
            require(c, actor, "audit")
            page = self.page_number(arg or "0")
            logs = rows(
                c,
                "SELECT id,actor_id,action,entity,entity_id,details,created_at FROM audit_logs ORDER BY id DESC LIMIT %s OFFSET %s",
                (PAGE_SIZE + 1, page * PAGE_SIZE),
            )
            buttons = ([("Previous", f"/audit {page - 1}")] if page else []) + (
                [("Next", f"/audit {page + 1}")] if len(logs) > PAGE_SIZE else []
            )
            return answer(
                "\n".join(
                    f"#{r['id']} {r['action']} {r['entity']} #{r['entity_id']} · actor {r['actor_id']}\n{r['details']} · {r['created_at']:%Y-%m-%d %H:%M UTC}"
                    for r in logs[:PAGE_SIZE]
                )
                or "No audit events.",
                buttons,
            )
        return answer(
            "Use /menu to choose an action, or /cancel to exit the current workflow."
        )

    def registration(self, c, actor, text, state):
        step = state["step"]
        if step == "register_name":
            state.update(full_name=clean(text, 2, 120), step="register_department")
            return self.choices(c, "departments", "Choose your department:")
        if step == "register_department":
            state.update(
                department_id=reference(c, "departments", text)["id"],
                step="register_level",
            )
            return self.choices(c, "academic_levels", "Choose your academic level:")
        if step == "register_level":
            state.update(
                level_id=reference(c, "academic_levels", text)["id"],
                step="register_semester",
            )
            return self.choices(c, "semesters", "Choose your preferred semester:")
        semester = reference(c, "semesters", text)["id"]
        c.execute(
            "UPDATE profiles SET full_name=%s,department_id=%s,level_id=%s,semester_id=%s,updated_at=now() WHERE id=%s",
            (
                state["full_name"],
                state["department_id"],
                state["level_id"],
                semester,
                actor,
            ),
        )
        state.clear()
        return self.menu()

    @staticmethod
    def choices(c, table, prompt):
        if table not in REFERENCE_TABLES:
            raise ValueError("Unknown selection.")
        choices = rows(c, f"SELECT id,name FROM {table} WHERE NOT archived ORDER BY id")
        return answer(
            prompt
            if choices
            else "No entries have been onboarded. Ask an administrator or use /request.",
            [(r["name"], "input:" + str(r["id"])) for r in choices],
        )

    @staticmethod
    def catalog(c):
        lines = []
        for table in sorted(REFERENCE_TABLES):
            values = rows(
                c,
                f"SELECT id,name FROM {table} WHERE NOT archived ORDER BY id LIMIT 30",
            )
            lines.append(
                table + ": " + ", ".join(f"{r['id']}={r['name']}" for r in values)
            )
        return answer("\n".join(lines))

    def browse(self, c, actor, text, state):
        step = state["step"]
        f = state["filters"]
        if step == "browse_department":
            f["department_id"] = reference(c, "departments", text)["id"]
            state["step"] = "browse_level"
            return self.choices(c, "academic_levels", "Choose a level:")
        if step == "browse_level":
            f["level_id"] = reference(c, "academic_levels", text)["id"]
            state["step"] = "browse_semester"
            return self.choices(c, "semesters", "Choose a semester:")
        if step == "browse_semester":
            f["semester_id"] = reference(c, "semesters", text)["id"]
            state["step"] = "browse_course"
            courses = rows(
                c,
                "SELECT id,code,title FROM courses WHERE department_id=%s AND level_id=%s AND semester_id=%s AND NOT archived ORDER BY code LIMIT 100",
                (f["department_id"], f["level_id"], f["semester_id"]),
            )
            return answer(
                "Choose a course:"
                if courses
                else "This course scope has not been onboarded. Use /request.",
                [
                    (f"{r['code']} — {r['title']}", "input:" + str(r["id"]))
                    for r in courses
                ],
            )
        if step == "browse_course":
            selected = course(c, text)
            if any(
                selected[k] != f[k]
                for k in ("department_id", "level_id", "semester_id")
            ):
                raise ValueError("Choose a course in the selected scope.")
            f["course_id"] = selected["id"]
            state["step"] = "browse_category"
            return self.choices(c, "resource_categories", "Choose a resource category:")
        f["category_id"] = reference(c, "resource_categories", text)["id"]
        state.update(step="", mode="browse")
        return self.list_resources(c, actor, state, 0)

    @staticmethod
    def list_resources(c, actor, state, page):
        require_student(c, actor)
        mode = state.get("mode", "recent")
        where = ["r.status='published'", "NOT c.archived"]
        params = []
        if mode == "manage":
            AcademicService.require_any(c, actor, "resources")
            where = [AcademicService.scope_sql("c", "resources")]
            params.append(actor)
            q = (
                state.get("query", "")
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            where.append("(r.title ILIKE %s OR c.title ILIKE %s OR c.code ILIKE %s)")
            params.extend(["%" + q + "%"] * 3)
        if mode == "search":
            q = (
                state.get("query", "")
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            where.append("(r.title ILIKE %s OR c.title ILIKE %s OR c.code ILIKE %s)")
            params.extend(["%" + q + "%"] * 3)
        elif mode == "browse":
            f = state.get("filters", {})
            for key, column in (
                ("course_id", "r.course_id"),
                ("category_id", "r.category_id"),
            ):
                where.append(column + "=%s")
                params.append(identifier(f.get(key)))
        elif mode == "bookmarks":
            where.append(
                "EXISTS(SELECT 1 FROM bookmarks b WHERE b.profile_id=%s AND b.resource_id=r.id)"
            )
            params.append(actor)
        found = rows(
            c,
            RESOURCE_SELECT
            + " WHERE "
            + " AND ".join(where)
            + " ORDER BY r.uploaded_at DESC,r.id DESC LIMIT %s OFFSET %s",
            (*params, PAGE_SIZE + 1, page * PAGE_SIZE),
        )
        buttons = []
        lines = []
        for r in found[:PAGE_SIZE]:
            lines.append(
                f"#{r['id']} {r['code']} — {r['title']} · {r['category']} · {r['session']} · {r['status']}"
            )
            if r["status"] == "published":
                buttons.append((f"Open #{r['id']}", f"/open {r['id']}"))
            if mode == "manage":
                action = "archive" if r["status"] == "published" else "restore"
                buttons.append((f"{action.title()} #{r['id']}", f"/{action} {r['id']}"))
        if page:
            buttons.append(("Previous", f"/page {page - 1}"))
        if len(found) > PAGE_SIZE:
            buttons.append(("Next", f"/page {page + 1}"))
        if not found:
            lines.append(
                "No resources found. This material may not have been onboarded."
            )
            buttons.append(("Request missing resource", "/request"))
        return answer("\n".join(lines), buttons)

    def resource_action(self, c, actor, command, arg):
        parts = arg.split(" ", 2)
        r = resource(c, parts[0], command in ("/open", "/save"))
        if command in ("/open", "/save", "/unsave"):
            require_student(c, actor)
            if command == "/save":
                c.execute(
                    "INSERT INTO bookmarks(profile_id,resource_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (actor, r["id"]),
                )
                return answer("Bookmark saved.")
            if command == "/unsave":
                c.execute(
                    "DELETE FROM bookmarks WHERE profile_id=%s AND resource_id=%s",
                    (actor, r["id"]),
                )
                return answer("Bookmark removed.")
            # Data required for delivery only; private backup paths never leave the backend.
            delivery = {
                key: r[key]
                for key in (
                    "id",
                    "file_id",
                    "title",
                    "code",
                    "category",
                    "session",
                    "description",
                )
            }
            delivery["uploaded_at"] = r["uploaded_at"].isoformat()
            return answer(
                f"{r['title']}\n{r['description']}",
                [
                    ("Save bookmark", f"/save {r['id']}"),
                    ("Remove bookmark", f"/unsave {r['id']}"),
                    ("Report", f"/report {r['id']}"),
                ],
                delivery=delivery,
            )
        require(c, actor, "resources", r["department_id"], r["level_id"])
        if command == "/edit":
            if len(parts) != 3 or parts[1] not in (
                "title",
                "description",
                "category_id",
                "session_id",
                "course_id",
            ):
                raise ValueError(
                    "Usage: /edit ID title|description|category_id|session_id|course_id VALUE"
                )
            field, value = parts[1:]
            if field == "course_id":
                target = course(c, value)
                require(
                    c, actor, "resources", target["department_id"], target["level_id"]
                )
                value = target["id"]
            elif field in ("category_id", "session_id"):
                value = reference(
                    c,
                    "resource_categories"
                    if field == "category_id"
                    else "academic_sessions",
                    value,
                )["id"]
            else:
                value = clean(
                    value,
                    2 if field == "title" else 0,
                    200 if field == "title" else 2000,
                )
            c.execute(
                f"UPDATE resources SET {field}=%s,updated_at=now() WHERE id=%s",
                (value, r["id"]),
            )
        else:
            c.execute(
                "UPDATE resources SET status=%s,updated_at=now() WHERE id=%s",
                ("archived" if command == "/archive" else "published", r["id"]),
            )
        audit(c, actor, command[1:], "resources", r["id"])
        return answer("Resource updated. Original backup retained.")

    def upload(self, c, actor, text, document, state):
        step = state["step"]
        if step == "upload_document":
            if not document:
                raise ValueError("Please send a PDF, DOCX, or MP4 document.")
            if one(
                c,
                "SELECT id FROM resources WHERE file_unique_id=%s",
                (document["file_unique_id"],),
            ):
                raise ValueError(
                    "Likely duplicate: this file already exists. Use /search and edit or restore the existing resource."
                )
            if (
                not 0 < document["file_size"] <= MAX_UPLOAD
                or document["mime_type"] not in MIMES
            ):
                raise ValueError("Only PDF/DOCX/MP4 files up to 20 MB are permitted.")
            path = Path(document["backup_path"]).resolve()
            if not path.is_relative_to(self.backup_directory) or not path.is_file():
                raise ValueError(
                    "Original backup is missing. Please upload the document again."
                )
            state.update(document=document, step="upload_title")
            return answer("Enter the resource title:")
        if step == "upload_title":
            state.update(title=clean(text, 2, 200), step="upload_department")
            return self.choices(c, "departments", "Choose the department:")
        if step == "upload_department":
            state.update(
                department_id=reference(c, "departments", text)["id"],
                step="upload_level",
            )
            return self.choices(c, "academic_levels", "Choose the level:")
        if step == "upload_level":
            level = reference(c, "academic_levels", text)["id"]
            require(c, actor, "resources", state["department_id"], level)
            state.update(level_id=level, step="upload_semester")
            return self.choices(c, "semesters", "Choose the semester:")
        if step == "upload_semester":
            state.update(
                semester_id=reference(c, "semesters", text)["id"], step="upload_course"
            )
            found = rows(
                c,
                "SELECT id,code,title FROM courses WHERE department_id=%s AND level_id=%s AND semester_id=%s AND NOT archived ORDER BY code LIMIT 100",
                (state["department_id"], state["level_id"], state["semester_id"]),
            )
            return answer(
                "Choose the course:"
                if found
                else "No matching courses. /cancel, then ask an authorized administrator to add one using /course.",
                [
                    (r["code"] + " — " + r["title"], "input:" + str(r["id"]))
                    for r in found
                ],
            )
        if step == "upload_course":
            target = course(c, text)
            if any(
                target[k] != state[k]
                for k in ("department_id", "level_id", "semester_id")
            ):
                raise ValueError(
                    "Choose a course in the selected department, level, and semester."
                )
            require(c, actor, "resources", target["department_id"], target["level_id"])
            state.update(course_id=target["id"], step="upload_category")
            return self.choices(c, "resource_categories", "Choose a category:")
        if step == "upload_category":
            state.update(
                category_id=reference(c, "resource_categories", text)["id"],
                step="upload_session",
            )
            return self.choices(c, "academic_sessions", "Choose the academic session:")
        if step == "upload_session":
            state.update(
                session_id=reference(c, "academic_sessions", text)["id"],
                step="upload_description",
            )
            return answer("Enter a description (or - for none):")
        if step == "upload_description":
            state.update(
                description="" if text == "-" else clean(text, 1, 2000),
                step="upload_confirm",
            )
            target = course(c, state["course_id"])
            cat = reference(c, "resource_categories", state["category_id"])
            session = reference(c, "academic_sessions", state["session_id"])
            return answer(
                f"Confirm publication:\n{state['title']}\n{target['code']} — {target['title']}\n"
                f"Category: {cat['name']}\nSession: {session['name']}\n{state['description']}",
                [("Publish", "input:confirm"), ("Cancel", "/cancel")],
            )
        if text != "confirm":
            raise ValueError("Select Publish or /cancel.")
        target = course(c, state["course_id"])
        require(c, actor, "resources", target["department_id"], target["level_id"])
        reference(c, "resource_categories", state["category_id"])
        reference(c, "academic_sessions", state["session_id"])
        document = state["document"]
        path = Path(document["backup_path"]).resolve()
        if not path.is_relative_to(self.backup_directory) or not path.is_file():
            raise ValueError("Backup is missing. Cancel and upload again.")
        if (
            path.stat().st_size != document["file_size"]
            or hashlib.sha256(path.read_bytes()).hexdigest()
            != document["backup_sha256"]
        ):
            raise ValueError(
                "Backup integrity check failed. Cancel and upload the original again."
            )
        r = one(
            c,
            "INSERT INTO resources(course_id,category_id,session_id,title,description,file_id,file_unique_id,file_size,mime_type,backup_path,backup_sha256,uploaded_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                target["id"],
                state["category_id"],
                state["session_id"],
                state["title"],
                state["description"],
                document["file_id"],
                document["file_unique_id"],
                document["file_size"],
                document["mime_type"],
                document["backup_path"],
                document["backup_sha256"],
                actor,
            ),
        )
        audit(c, actor, "publish", "resources", r["id"])
        state.clear()
        return answer(f"Published resource #{r['id']}.", [("Open", f"/open {r['id']}")])

    def feedback_admin(self, c, actor, command, arg):
        if command == "/feedbackqueue":
            page = self.page_number(arg or "0")
            self.require_any(c, actor, "feedback")
            scope = self.scope_sql("f", "feedback")
            counts = {
                r["status"]: r["n"]
                for r in rows(
                    c,
                    "SELECT status,count(*) n FROM feedback f WHERE "
                    + scope
                    + " GROUP BY status",
                    (actor,),
                )
            }
            common = {
                r["kind"]: r["n"]
                for r in rows(
                    c,
                    "SELECT kind,count(*) n FROM feedback f WHERE "
                    + scope
                    + " GROUP BY kind",
                    (actor,),
                )
            }
            departments = {
                r["department_id"]: r["n"]
                for r in rows(
                    c,
                    "SELECT department_id,count(*) n FROM feedback f WHERE "
                    + scope
                    + " GROUP BY department_id",
                    (actor,),
                )
            }
            recent = [
                r["reference"]
                for r in rows(
                    c,
                    "SELECT reference FROM feedback f WHERE "
                    + scope
                    + " AND status='Resolved' ORDER BY updated_at DESC LIMIT 5",
                    (actor,),
                )
            ]
            selected = rows(
                c,
                "SELECT * FROM feedback f WHERE "
                + scope
                + " ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
                (actor, PAGE_SIZE + 1, page * PAGE_SIZE),
            )
            total = sum(counts.values())
            more = len(selected) > PAGE_SIZE
            selected = selected[:PAGE_SIZE]
            return answer(
                f"Your scope — Total: {total} · Unresolved: {counts.get('New', 0) + counts.get('Under Review', 0)}\n"
                f"Statuses: {counts}\nIssue counts: {common}\nDepartment IDs: {departments}\nRecently resolved: {', '.join(recent) or 'None'}\n"
                + "\n".join(
                    f"{f['reference']} — {f['kind']} · {f['status']}" for f in selected
                ),
                [(f["reference"], "/submission " + f["reference"]) for f in selected]
                + ([("Previous", f"/feedbackqueue {page - 1}")] if page else [])
                + ([("Next", f"/feedbackqueue {page + 1}")] if more else []),
            )
        parts = arg.split("|")
        ref = clean(parts[0], 6, 50).upper()
        f = one(c, "SELECT * FROM feedback WHERE reference=%s FOR UPDATE", (ref,))
        if not f:
            raise ValueError("Submission not found or unavailable.")
        if command == "/track":
            if f["profile_id"] != actor:
                raise Denied("Submission not found or unavailable.")
            return answer(
                f"{f['reference']} · {f['kind']}\nStatus: {f['status']}\nUpdated: {f['updated_at']:%Y-%m-%d}"
            )
        require(c, actor, "feedback", f["department_id"], f["level_id"])
        if command == "/submission":
            return answer(
                f"{f['reference']}\n{f['kind']} · {f['status']}\n{f['body']}\nAssigned admin: {f['assigned_to'] or 'Unassigned'}\n"
                "Update: /status REFERENCE|New/Under Review/Resolved/Declined|ADMIN_ID (optional)"
            )
        if len(parts) not in (2, 3) or parts[1].strip() not in STATUSES:
            raise ValueError(
                "Usage: /status REFERENCE|New/Under Review/Resolved/Declined|ADMIN_ID (optional)"
            )
        assigned = f["assigned_to"]
        if len(parts) == 3:
            assigned = identifier(parts[2].strip())
            require(c, assigned, "feedback", f["department_id"], f["level_id"])
        c.execute(
            "UPDATE feedback SET status=%s,assigned_to=%s,updated_at=now() WHERE id=%s",
            (parts[1].strip(), assigned, f["id"]),
        )
        audit(
            c,
            actor,
            "feedback_status",
            "feedback",
            f["id"],
            {"from": f["status"], "to": parts[1].strip(), "assigned_to": assigned},
        )
        return answer(f"{ref} updated to {parts[1].strip()}.")

    @staticmethod
    def manage_course(c, actor, arg):
        action, _, rest = arg.partition(" ")
        if action == "add":
            p = [v.strip() for v in rest.split("|")]
            if len(p) != 5:
                raise ValueError(
                    "Usage: /course add CODE|TITLE|DEPARTMENT_ID|LEVEL_ID|SEMESTER_ID"
                )
            code = clean(p[0].upper(), 5, 12)
            if not re.fullmatch("[A-Z]{2,8}[0-9]{3,4}", code):
                raise ValueError("Course code must resemble EEE311 (no spaces).")
            d = reference(c, "departments", p[2])["id"]
            level = reference(c, "academic_levels", p[3])["id"]
            s = reference(c, "semesters", p[4])["id"]
            require(c, actor, "courses", d, level)
            result = one(
                c,
                "INSERT INTO courses(code,title,department_id,level_id,semester_id) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (code, clean(p[1]), d, level, s),
            )
        elif action in ("edit", "archive", "restore"):
            values = rest.split(" ", 2)
            target = course(c, values[0], False)
            require(c, actor, "courses", target["department_id"], target["level_id"])
            if action == "edit":
                if len(values) != 3 or values[1] not in (
                    "code",
                    "title",
                    "department_id",
                    "level_id",
                    "semester_id",
                ):
                    raise ValueError(
                        "Usage: /course edit ID code|title|department_id|level_id|semester_id VALUE"
                    )
                field, value = values[1:]
                if field.endswith("_id"):
                    table = {
                        "department_id": "departments",
                        "level_id": "academic_levels",
                        "semester_id": "semesters",
                    }[field]
                    value = reference(c, table, value)["id"]
                    new = dict(target)
                    new[field] = value
                    require(c, actor, "courses", new["department_id"], new["level_id"])
                    # Moving a course also moves the scope of every existing resource.
                    if field in ("department_id", "level_id") and one(
                        c,
                        "SELECT id FROM resources WHERE course_id=%s LIMIT 1",
                        (target["id"],),
                    ):
                        require(c, actor, "roles")
                elif field == "code":
                    value = value.upper().strip()
                    if not re.fullmatch("[A-Z]{2,8}[0-9]{3,4}", value):
                        raise ValueError("Invalid course code.")
                else:
                    value = clean(value)
                c.execute(
                    f"UPDATE courses SET {field}=%s,updated_at=now() WHERE id=%s",
                    (value, target["id"]),
                )
            else:
                c.execute(
                    "UPDATE courses SET archived=%s,updated_at=now() WHERE id=%s",
                    (action == "archive", target["id"]),
                )
            result = target
        else:
            return answer(
                "Course management:\n/course add CODE|TITLE|DEPT_ID|LEVEL_ID|SEMESTER_ID\n"
                "/course edit ID FIELD VALUE\n/course archive ID\n/course restore ID\n/catalog for selection IDs."
            )
        audit(c, actor, "course_" + action, "courses", result["id"])
        return answer(f"Course #{result['id']} updated.")

    @staticmethod
    def manage_roles(c, actor, arg):
        require(c, actor, "roles")
        action, _, rest = arg.partition(" ")
        if action == "grant":
            p = rest.split()
            if len(p) != 5 or p[1] not in ("super", "executive", "resource_admin"):
                raise ValueError(
                    "Usage: /roles grant TELEGRAM_ID super|executive|resource_admin DEPT_ID|* LEVEL_ID|* permissions_csv"
                )
            target = identifier(p[0])
            require_student(c, target)
            d = None if p[2] == "*" else reference(c, "departments", p[2])["id"]
            level = None if p[3] == "*" else reference(c, "academic_levels", p[3])["id"]
            if p[1] == "resource_admin" and (d is None or level is None):
                raise ValueError(
                    "Resource administrators require a department and level."
                )
            permissions = p[4].split(",")
            if not set(permissions) <= {
                "resources",
                "feedback",
                "courses",
                "analytics",
                "audit",
                "reference",
                "roles",
            }:
                raise ValueError("Unknown permission.")
            r = one(
                c,
                "INSERT INTO admin_roles(profile_id,role,department_id,level_id,permissions) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (target, p[1], d, level, permissions),
            )
            audit(c, actor, "grant_role", "admin_roles", r["id"])
            return answer(f"Role #{r['id']} granted.")
        if action == "revoke":
            role = one(
                c,
                "SELECT * FROM admin_roles WHERE id=%s FOR UPDATE",
                (identifier(rest),),
            )
            if not role:
                raise ValueError("Role not found.")
            # Serializes super-admin revocation so at least one remains.
            c.execute("SELECT pg_advisory_xact_lock(887741002)")
            if role["role"] == "super" and role["active"]:
                count = one(
                    c,
                    "SELECT count(*) n FROM admin_roles WHERE role='super' AND active",
                )["n"]
                if count <= 1:
                    raise ValueError("Cannot revoke the last super administrator.")
            c.execute("UPDATE admin_roles SET active=false WHERE id=%s", (role["id"],))
            audit(c, actor, "revoke_role", "admin_roles", role["id"])
            return answer("Role revoked.")
        roles = rows(
            c,
            "SELECT id,profile_id,role,department_id,level_id,permissions FROM admin_roles WHERE active ORDER BY id LIMIT 50",
        )
        return answer(
            "Active roles:\n" + "\n".join(str(r) for r in roles) + "\n"
            "/roles grant TELEGRAM_ID ROLE DEPT_ID|* LEVEL_ID|* resources,feedback\n/roles revoke ROLE_ID"
        )

    @staticmethod
    def manage_reference(c, actor, arg):
        require(c, actor, "reference")
        parts = arg.split(" ", 2)
        if (
            len(parts) != 3
            or parts[0] not in ("add", "edit", "archive", "restore")
            or parts[1] not in REFERENCE_TABLES
        ):
            return answer(
                "Reference management:\n/reference add TABLE NAME (department: CODE|NAME)\n"
                "/reference edit TABLE ID|NAME (department: ID|CODE|NAME)\n/reference archive TABLE ID\n/reference restore TABLE ID\n/catalog"
            )
        action, table, value = parts
        if action == "add":
            if table == "departments":
                p = value.split("|", 1)
                if len(p) != 2:
                    raise ValueError("Department needs CODE|NAME.")
                result = one(
                    c,
                    "INSERT INTO departments(code,name) VALUES (%s,%s) RETURNING id",
                    (clean(p[0], 2, 20).upper(), clean(p[1], 2, 150)),
                )
            else:
                AcademicService.validate_reference(table, value)
                result = one(
                    c,
                    f"INSERT INTO {table}(name) VALUES (%s) RETURNING id",
                    (clean(value, 2, 80),),
                )
        elif action == "edit":
            p = value.split("|")
            target = identifier(p[0])
            if table == "departments" and len(p) == 3:
                result = one(
                    c,
                    "UPDATE departments SET code=%s,name=%s WHERE id=%s RETURNING id",
                    (clean(p[1], 2, 20).upper(), clean(p[2], 2, 150), target),
                )
            elif table != "departments" and len(p) == 2:
                AcademicService.validate_reference(table, p[1])
                result = one(
                    c,
                    f"UPDATE {table} SET name=%s WHERE id=%s RETURNING id",
                    (clean(p[1], 2, 80), target),
                )
            else:
                raise ValueError("Invalid reference edit format.")
        else:
            result = one(
                c,
                f"UPDATE {table} SET archived=%s WHERE id=%s RETURNING id",
                (action == "archive", identifier(value)),
            )
        if not result:
            raise ValueError("Reference not found.")
        audit(c, actor, action, table, result["id"])
        return answer(f"{table} #{result['id']} updated.")

    @staticmethod
    def validate_reference(table, value):
        if table == "academic_levels" and not re.fullmatch("[1-6]00L", value):
            raise ValueError("Level must be 100L–600L.")
        if table == "academic_sessions":
            if (
                not re.fullmatch("[0-9]{4}/[0-9]{4}", value)
                or int(value[5:]) != int(value[:4]) + 1
            ):
                raise ValueError(
                    "Session must be consecutive years, for example 2025/2026."
                )

    @staticmethod
    def analytics(c, actor):
        require(c, actor, "analytics")
        metrics = {
            "Registered students": "SELECT count(*) n FROM profiles WHERE full_name IS NOT NULL",
            "Students by department": "SELECT d.name,count(*) n FROM profiles p JOIN departments d ON d.id=p.department_id WHERE full_name IS NOT NULL GROUP BY d.name",
            "Students by level": "SELECT l.name,count(*) n FROM profiles p JOIN academic_levels l ON l.id=p.level_id WHERE full_name IS NOT NULL GROUP BY l.name",
            "Published resources": "SELECT count(*) n FROM resources WHERE status='published'",
            "Resources by department": "SELECT d.name,count(*) n FROM resources r JOIN courses c ON c.id=r.course_id JOIN departments d ON d.id=c.department_id WHERE r.status='published' GROUP BY d.name",
            "Resources by category": "SELECT cat.name,count(*) n FROM resources r JOIN resource_categories cat ON cat.id=r.category_id WHERE status='published' GROUP BY cat.name",
            "Confirmed deliveries (top 5)": "SELECT r.id,r.title,count(*) n FROM access_events a JOIN resources r ON r.id=a.resource_id GROUP BY r.id,r.title ORDER BY n DESC LIMIT 5",
            "Recent uploads": "SELECT id,title,uploaded_at FROM resources ORDER BY uploaded_at DESC LIMIT 5",
            "Feedback by status": "SELECT status,count(*) n FROM feedback GROUP BY status",
        }
        return answer(
            "\n".join(
                title + ": " + str(rows(c, sql)) for title, sql in metrics.items()
            )
        )

    @staticmethod
    def page_number(value):
        if not str(value).isdigit() or not 0 <= int(value) <= 10000:
            raise ValueError("Invalid page.")
        return int(value)

    def resume(self, c, state):
        step = state.get("step", "")
        choice_tables = {
            "register_department": "departments",
            "register_level": "academic_levels",
            "register_semester": "semesters",
            "upload_department": "departments",
            "upload_level": "academic_levels",
            "upload_semester": "semesters",
            "upload_category": "resource_categories",
            "upload_session": "academic_sessions",
            "browse_department": "departments",
            "browse_level": "academic_levels",
            "browse_semester": "semesters",
            "browse_category": "resource_categories",
        }
        if step in choice_tables:
            return self.choices(c, choice_tables[step], "Resume your saved selection:")
        if step == "feedback_kind":
            return answer(
                "Choose a feedback category:",
                [(kind, "input:" + kind) for kind in KINDS],
            )
        if step == "upload_confirm":
            return answer(
                f"Ready to publish: {state['title']}\n{state['description']}\nCourse ID: {state['course_id']} · Category ID: {state['category_id']} · Session ID: {state['session_id']}",
                [("Publish", "input:confirm"), ("Cancel", "/cancel")],
            )
        if step in ("upload_course", "browse_course"):
            scope = state if step == "upload_course" else state["filters"]
            choices = rows(
                c,
                "SELECT id,code,title FROM courses WHERE department_id=%s AND level_id=%s AND semester_id=%s AND NOT archived ORDER BY code LIMIT 100",
                (scope["department_id"], scope["level_id"], scope["semester_id"]),
            )
            return answer(
                "Choose a course:",
                [
                    (r["code"] + " — " + r["title"], "input:" + str(r["id"]))
                    for r in choices
                ],
            )
        prompts = {
            "register_name": "Enter your full name:",
            "upload_document": "Send the original PDF, DOCX, or MP4 as a document (up to 20 MB):",
            "upload_title": "Enter the resource title:",
            "upload_description": "Enter a description (or - for none):",
            "feedback_body": "Describe your feedback or request:",
            "search": "Enter a course code, course title, or resource title:",
        }
        return (
            answer(prompts[step], [("Cancel", "/cancel")])
            if step in prompts
            else self.menu()
        )

    @staticmethod
    def require_any(c, actor, permission):
        found = one(
            c,
            "SELECT id FROM admin_roles WHERE profile_id=%s AND active AND (role='super' OR %s=ANY(permissions)) LIMIT 1",
            (actor, permission),
        )
        if not found:
            raise Denied("You do not have permission for this administrative action.")

    @staticmethod
    def scope_sql(alias, permission):
        # Only called with internal constant identifiers and permission names.
        if alias not in ("c", "f") or permission not in ("resources", "feedback"):
            raise ValueError("Unknown scope query.")
        return (
            f"EXISTS(SELECT 1 FROM admin_roles ar WHERE ar.profile_id=%s AND ar.active AND "
            f"(ar.role='super' OR ('{permission}'=ANY(ar.permissions) AND "
            f"(ar.department_id IS NULL OR ar.department_id={alias}.department_id) AND "
            f"(ar.level_id IS NULL OR ar.level_id={alias}.level_id))))"
        )

    def record_delivery(self, actor, resource_id, update_id):
        with self.database.transaction() as c:
            require_student(c, actor)
            c.execute(
                "INSERT INTO access_events(profile_id,resource_id,update_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (actor, resource_id, update_id),
            )

    def delivery_resource(self, actor, resource_id):
        with self.database.transaction() as c:
            require_student(c, actor)
            r = resource(c, resource_id)
            course(c, r["course_id"])
            return {
                k: r[k]
                for k in (
                    "id",
                    "file_id",
                    "title",
                    "code",
                    "category",
                    "session",
                    "description",
                    "uploaded_at",
                )
            }
