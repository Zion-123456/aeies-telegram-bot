-- Retain existing access paths but cover archived/inactive children too.
-- Avoid adding redundant full-prefix indexes alongside these partial indexes.
DROP INDEX aeies.admin_roles_profile;
CREATE INDEX admin_roles_profile ON aeies.admin_roles(profile_id);
DROP INDEX aeies.courses_browse;
CREATE INDEX courses_browse ON aeies.courses(department_id,level_id,semester_id);
DROP INDEX aeies.resources_browse;
CREATE INDEX resources_browse ON aeies.resources(course_id,category_id,uploaded_at DESC);

-- Student department/level analytics and reference-integrity checks.
CREATE INDEX profiles_department_fk ON aeies.profiles(department_id);
CREATE INDEX profiles_level_fk ON aeies.profiles(level_id);
CREATE INDEX profiles_semester_fk ON aeies.profiles(semester_id);
-- Scope assignment lookup and department/level integrity checks.
CREATE INDEX admin_roles_department_fk ON aeies.admin_roles(department_id);
CREATE INDEX admin_roles_level_fk ON aeies.admin_roles(level_id);
-- Standalone level/semester course filters (department already leads courses_browse).
CREATE INDEX courses_level_fk ON aeies.courses(level_id);
CREATE INDEX courses_semester_fk ON aeies.courses(semester_id);
-- Category analytics, session selection, uploader accountability.
CREATE INDEX resources_category_fk ON aeies.resources(category_id);
CREATE INDEX resources_session_fk ON aeies.resources(session_id);
CREATE INDEX resources_uploader_fk ON aeies.resources(uploaded_by);
-- Reverse bookmark lookup; the primary key already covers the student prefix.
CREATE INDEX bookmarks_resource_fk ON aeies.bookmarks(resource_id);
-- Student submission lookup, level queues and assigned-administrator queues.
CREATE INDEX feedback_profile_fk ON aeies.feedback(profile_id);
CREATE INDEX feedback_level_fk ON aeies.feedback(level_id);
CREATE INDEX feedback_assignee_fk ON aeies.feedback(assigned_to);
-- Resource reports, actor audit lookup and student delivery records.
CREATE INDEX resource_reports_resource_fk ON aeies.resource_reports(resource_id);
CREATE INDEX audit_logs_actor_fk ON aeies.audit_logs(actor_id);
CREATE INDEX access_events_profile_fk ON aeies.access_events(profile_id);
