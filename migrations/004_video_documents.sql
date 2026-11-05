-- Educational videos are uploaded as Telegram documents, with the same 20 MB policy.
ALTER TABLE aeies.resources DROP CONSTRAINT resources_mime_type_check;
ALTER TABLE aeies.resources ADD CONSTRAINT resources_mime_type_check CHECK(mime_type IN (
 'application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','video/mp4'
));
