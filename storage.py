"""Persistent submissions and faculty approval, including legacy database migration."""
import json
import secrets
import sqlite3
from datetime import datetime, timezone


def connect(path):
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(path):
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, roll TEXT NOT NULL,
            title TEXT NOT NULL, source TEXT NOT NULL, result_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', approved_score INTEGER,
            faculty_note TEXT, submitted_at TEXT NOT NULL)""")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(submissions)")}
        if "approved_at" not in columns:
            conn.execute("ALTER TABLE submissions ADD COLUMN approved_at TEXT")


def submit(path, name, roll, title, source, result):
    sid = secrets.token_urlsafe(18)
    with connect(path) as conn:
        # Serialize history read and attempt insert so simultaneous submissions see consistent counts.
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute(
            "SELECT status,approved_score,result_json FROM submissions WHERE roll=? AND title=? ORDER BY submitted_at",
            (roll, title)).fetchall()
        if result.get("report_schema_version", 0) >= 3:
            details = result["agent_details"]
            approved_scores = [r["approved_score"] for r in prior if r["status"] == "approved"]
            concepts = {}
            for record in prior:
                old = json.loads(record["result_json"])
                for note in old.get("retrieved_notes", []):
                    key = note["concept"]
                    concepts[key] = concepts.get(key, 0) + 1
            analytics = next(a for a in details if a["key"] == "analytics")
            analytics.update(
                status="COMPLETED",
                inputs=[f"Earlier attempts for this roll and assignment: {len(prior)}",
                        "Approved marks and previously retrieved concepts from SQLite."],
                steps=["Read matching attempt history inside the submission transaction.",
                       "Count previous attempts and approved results.",
                       "Count course concepts retrieved in previous attempts."],
                outputs=[f"Attempt number: {len(prior) + 1}",
                         f"Previous approved scores: {approved_scores}",
                         f"Historical concept counts: {concepts}"],
                result="Recorded a descriptive history summary. These counts are not a measure of learning gains.",
                evidence_ids=["TOOL-ANALYTICS"])
            result["evidence_log"].append({
                "id": "TOOL-ANALYTICS", "agent": "Learning Analytics Agent",
                "authority": "SQLite attempt history",
                "fact": f"Attempt {len(prior) + 1}; earlier approved scores: {approved_scores}",
                "raw": json.dumps(concepts)})
        if result.get("report_schema_version", 0) >= 3:
            coordinator = next(a for a in result["agent_details"] if a["key"] == "coordinator")
            coordinator["outputs"] = [
                item for item in coordinator["outputs"] if not item.startswith("Evidence records:")]
            coordinator["outputs"].append(f'Evidence records: {len(result["evidence_log"])}')
        conn.execute("""INSERT INTO submissions
            (id,name,roll,title,source,result_json,submitted_at)
            VALUES (?,?,?,?,?,?,?)""",
            (sid, name, roll, title, source, json.dumps(result),
             datetime.now(timezone.utc).isoformat()))
    return sid


def get_submission(path, sid):
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    return dict(row) if row else None


def pending_submissions(path):
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM submissions WHERE status='pending' ORDER BY submitted_at DESC")]


def approve(path, sid, score, note):
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("Approved score must be an integer between 0 and 100.")
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pending = conn.execute(
            "SELECT result_json FROM submissions WHERE id=? AND status='pending'", (sid,)).fetchone()
        if not pending:
            return False
        raw = json.loads(pending["result_json"])
        provisional = raw.get("provisional_score", raw.get("score", 0))
        if score != provisional and not str(note).strip():
            raise ValueError("A faculty score adjustment requires a recorded reason.")
        changed = conn.execute("""UPDATE submissions
            SET status='approved',approved_score=?,faculty_note=?,approved_at=?
            WHERE id=? AND status='pending'""",
            (score, note, datetime.now(timezone.utc).isoformat(), sid)).rowcount
    return changed == 1


def approved_payload(path, sid):
    row = get_submission(path, sid)
    if not row or row["status"] != "approved":
        raise PermissionError("Faculty approval is required before releasing marks or PDF.")
    result = json.loads(row["result_json"])
    result.setdefault("provisional_score", result.get("score", 0))
    result.update(
        score=row["approved_score"], approval_status="approved",
        approved_score=row["approved_score"], faculty_note=row["faculty_note"] or "",
        approved_at=row.get("approved_at") or "Legacy approval - timestamp unavailable",
        submitted_at=row["submitted_at"], submission_id=row["id"], source=row["source"],
    )
    return row, result
