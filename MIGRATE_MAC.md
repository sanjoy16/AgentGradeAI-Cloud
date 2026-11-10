# Preserve the Docker app database when moving to the full Mac tool runner

Keep the original Docker app and its named volume. The full native Mac app uses
port 8502 and a separate local database path. The old app uses port 8501.

Before the first native launch, open Terminal in this upgraded project's folder.
Copy the old database with SQLite's backup API for a consistent snapshot:

    docker exec agentgrade-local python -c 'import sqlite3; source=sqlite3.connect("/data/agentgrade.db"); target=sqlite3.connect("/tmp/gradeai-backup.db"); source.backup(target); target.close(); source.close()'
    mkdir -p data
    docker cp agentgrade-local:/tmp/gradeai-backup.db data/agentgrade.db

Do this once, before new submissions are entered in the Mac app.
Do not overwrite a local database that already contains new submissions.
If the old container is stopped, start it first with docker start agentgrade-local.
If the old container was removed, recreate it with the existing agentgrade-data
volume before performing the backup. Keep the original named volume as a backup.

Existing reports retain their historical agent statuses. Submit a new attempt to
run the integrated tools. Approval of an old report does not rerun its analysis.
