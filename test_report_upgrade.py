import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from reports import normalize_result, pdf_report, PIPELINE
from storage import initialize, submit, approve, approved_payload

RAW = {
    "score": 61,
    "agents": [
        {"name": "Compilation Agent", "score": 35, "max": 35, "analysis": "GCC syntax check passed.",
         "improvement": "Check edge cases.", "evidence": "No compiler errors."},
        {"name": "Testing Agent", "score": 0, "max": 15, "analysis": "Not evaluated.",
         "improvement": "Supply trusted tests."},
        {"name": "Design Quality Agent", "score": 9, "max": 15, "analysis": "Heuristic function count.",
         "improvement": "Name variables clearly."},
        {"name": "Complexity Agent", "score": 17, "max": 20, "analysis": "Keyword counts only.",
         "improvement": "Inspect nested loops."},
        {"name": "Optimization Agent", "score": 0, "max": 15,
         "analysis": "Cppcheck did not complete successfully.", "improvement": "Review manually."},
        {"name": "Security Agent (diagnostic)", "score": 0, "max": 0,
         "analysis": "Potentially unsafe API patterns: none found.", "improvement": "Validate input."},
    ],
}
SOURCE = '#include <stdio.h>\nint main(void) { printf("<example> & data\\n"); return 0; }\n'


class ReportUpgradeTests(unittest.TestCase):
    def test_stage_coverage_and_inactive_tools(self):
        result = normalize_result(RAW, SOURCE, "Maximum")
        self.assertEqual(len(result["agent_details"]), 14)
        for stage in result["agent_details"]:
            self.assertTrue(stage["inputs"])
            self.assertTrue(stage["steps"])
            self.assertTrue(stage["outputs"])
            self.assertTrue(stage["result"])
            if stage["key"] in {"llvm", "symbolic", "smt", "verification", "knowledge", "graphrag", "analytics"}:
                self.assertEqual(stage["status"], "NOT RUN")
        self.assertEqual(result["provisional_score"], 61)
        self.assertEqual(result, normalize_result(result, SOURCE, "Maximum"))

    def test_unapproved_pdf_is_blocked(self):
        with self.assertRaises(PermissionError):
            pdf_report("Student", "001", "Maximum", RAW)

    def test_legacy_migration_approval_and_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / "legacy.db")
            with sqlite3.connect(db) as conn:
                conn.execute("""CREATE TABLE submissions (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,roll TEXT NOT NULL,
                    title TEXT NOT NULL,source TEXT NOT NULL,result_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',approved_score INTEGER,
                    faculty_note TEXT,submitted_at TEXT NOT NULL)""")
            initialize(db)
            sid = submit(db, "Test Student", "001", "Maximum <&>", SOURCE, RAW)
            with self.assertRaises(PermissionError):
                approved_payload(db, sid)
            self.assertTrue(approve(db, sid, 72, "Manual review completed <&>."))
            self.assertFalse(approve(db, sid, 90, "Duplicate approval"))
            row, result = approved_payload(db, sid)
            self.assertEqual(result["score"], 72)
            self.assertTrue(result["approved_at"])
            data = pdf_report(row["name"], row["roll"], row["title"], result)
            from pypdf import PdfReader
            from io import BytesIO
            contents = "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
            self.assertIn("72/100", contents)
            self.assertIn("61/100", contents)
            self.assertIn("Manual review completed", contents)
            for _, name, _ in PIPELINE:
                self.assertIn(name, contents)
            self.assertIn("Source SHA-256", contents)
            self.assertIn("How each agent analysed your code", contents)
            self.assertIn("NOT RUN", contents)

    def test_score_validation(self):
        for score in [-1, 101, True, 42.5]:
            with self.assertRaises(ValueError):
                approve("unused.db", "sid", score, "")


if __name__ == "__main__":
    unittest.main()
