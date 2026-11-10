"""Optional Streamlit smoke test with tool execution mocked as unavailable."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class InterfaceTests(unittest.TestCase):
    def test_faculty_approval_and_student_pdf(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Install Streamlit to run the interface test.")
        from engine import evaluate
        from storage import initialize, submit, get_submission
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / "ui.db")
            with patch.dict(os.environ, {"AGENTGRADE_DB": db, "FACULTY_PASSWORD": "test-only-password"}):
                initialize(db)
                with patch("verification.shutil.which", return_value=None):
                    result = evaluate("int factorial(int n){return n;}", "Factorial", "factorial")
                sid = submit(db, "Test Student", "001", "Factorial", "int factorial(int n){return n;}", result)
                at = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()
                self.assertFalse(at.exception)
                # Pending submission lookup must not expose a download.
                next(w for w in at.text_input if w.label == "Private submission ID").input(sid)
                next(w for w in at.button if w.label == "Check result").click()
                at.run()
                self.assertEqual(len(at.get("download_button")), 0)
                next(w for w in at.text_input if w.label == "Faculty password").input("test-only-password")
                at.run()
                self.assertFalse(at.exception)
                next(w for w in at.button if w.label == "Approve and publish marks and PDF").click()
                at.run()
                self.assertEqual(get_submission(db, sid)["status"], "approved")
                next(w for w in at.button if w.label == "Check result").click()
                at.run()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.get("download_button")), 1)


if __name__ == "__main__":
    unittest.main()
