from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader
from reports import normalize_result, pdf_report, PIPELINE
from student_report import deductions
from storage import initialize, submit, approve, get_submission
from test_report_upgrade import RAW


SOURCE = """#include <stdio.h>

int main() {
    int n, i;
    unsigned long long factorial = 1;
    if (scanf("%d", &n) != 1) return 1;
    if (n < 0 || n > 20) return 1;
    for (i = 2; i <= n; i++) factorial *= i;
    printf("%llu", factorial);
    return 0;
}
"""


class ConciseReportTests(unittest.TestCase):
    def fixture(self):
        raw = deepcopy(RAW)
        raw["agents"][0].update(
            score=32,
            evidence="submission.c:3:9: warning: a function declaration without a prototype",
            analysis="GCC syntax check passed.")
        raw["agents"][2].update(score=7, analysis="One function, no comments.")
        raw["agents"][3].update(score=20)
        raw["agents"][4].update(score=15, analysis="Cppcheck reported approximately 0 issue(s).")
        raw["score"] = 74
        raw = normalize_result(raw, SOURCE, "Factorial")
        raw.update(approval_status="approved", approved_score=74, approved_at="Test approval",
                   faculty_note="Reviewed.", assignment_profile="main",
                   submission_id="CONCISE-TEST")
        return raw

    def test_report_has_summary_and_all_agents(self):
        result = self.fixture()
        reader = PdfReader(BytesIO(pdf_report("Test Student", "001", "Factorial", result)))
        self.assertLessEqual(len(reader.pages), 7)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("74/100", text)
        self.assertIn("Line 3", text)
        self.assertIn("int main(void)", text)
        self.assertIn("4 points for missing comments", text)
        self.assertIn("4 points from the function-count bonus", text)
        self.assertIn("unverified credit", text)
        for _, name, _ in PIPELINE:
            self.assertIn(name, text)

    def test_deductions_sum_and_withheld_testing(self):
        issues = deductions(self.fixture())
        self.assertEqual(sum(item["lost"] for item in issues), 26)
        testing = next(item for item in issues if item["criterion"] == "Testing Agent")
        self.assertEqual(testing["kind"], "Withheld")
        self.assertIn("contract", testing["where"])

    def test_long_fields_are_bounded_and_raw_logs_are_not_printed(self):
        result = self.fixture()
        result["faculty_note"] = "<unsafe> & text " * 2000
        for a in result["agent_details"]:
            a["result"] = "Very long diagnostic " * 2000
            a["raw_evidence"] = ["Full log " * 10000]
        result["source"] = SOURCE + "\n/* " + "long comment " * 10000 + " */"
        data = pdf_report("Long Name " * 100, "123" * 100, "Long title " * 1000, result)
        reader = PdfReader(BytesIO(data))
        self.assertLessEqual(len(reader.pages), 8)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertNotIn("Full log Full log", text)
        self.assertIn("excerpt; full evidence in application", text)

    def test_moderated_score_requires_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / "test.db")
            initialize(db)
            result = self.fixture()
            sid = submit(db, "Test", "001", "Factorial", SOURCE, result)
            with self.assertRaises(ValueError):
                approve(db, sid, 80, "")
            self.assertEqual(get_submission(db, sid)["status"], "pending")
            self.assertTrue(approve(db, sid, 80, "Manual review added six points."))


if __name__ == "__main__":
    unittest.main()
