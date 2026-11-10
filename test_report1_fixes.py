from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from verification import harness, main_io_model, classify_klee, UNWIND_BOUND
from reports import normalize_result
from knowledge import enrich

SOURCE = Path(__file__).with_name("examples").joinpath("factorial_main_ull.c").read_text()


class ReportCorrections(unittest.TestCase):
    def test_external_scanf_cannot_be_completed(self):
        log = ("KLEE: WARNING: undefined reference to function: __isoc99_scanf\n"
               "KLEE: done: completed paths = 1\n"
               "KLEE: done: partially completed paths = 0")
        self.assertEqual(classify_klee(log, [], True)[0], "INCONCLUSIVE")

    def test_harness_abstracts_both_scan_and_print(self):
        self.assertEqual(main_io_model(SOURCE), "integer_tokens")
        for tool in ("klee", "cbmc"):
            code = harness("main", tool, SOURCE)
            self.assertIn("#define scanf gradeai_scanf", code)
            self.assertIn("#define printf gradeai_printf", code)
            self.assertIn("status >= -1", code)
            self.assertIn("status <= 1", code)
            self.assertIn("*target = value", code)
        self.assertEqual(main_io_model('scanf("%f",&x);'), "unsupported")
        self.assertEqual(main_io_model('scanf(format,&x);'), "unsupported")
        self.assertEqual(main_io_model('scanf("%d %d",&x,&y);'), "unsupported")

    def test_bound_and_unsigned_notes(self):
        self.assertGreaterEqual(UNWIND_BOUND, 21)
        _, _, notes = enrich(SOURCE, "Factorial", [], [])
        ids = {n["id"] for n in notes}
        self.assertIn("unsigned-factorial-range", ids)
        self.assertNotIn("integer-range", ids)

    def test_existing_report_is_reinterpreted_without_changing_marks(self):
        raw = dict(score=74, provisional_score=74, report_schema_version=3, source=SOURCE,
                   agent_details=[dict(key="symbolic", name="KLEE", status="COMPLETED",
                     result="Previous claim", outputs=[], evidence_ids=["TOOL-SYMBOLIC"],
                     raw_evidence=["KLEE: WARNING: undefined reference to function: __isoc99_scanf"])],
                   evidence_log=[dict(id="TOOL-SYMBOLIC", fact="Previous claim")],
                   retrieved_notes=[])
        reviewed = normalize_result(raw)
        self.assertEqual(reviewed["agent_details"][0]["status"], "INCONCLUSIVE")
        self.assertEqual(reviewed["score"], 74)
        self.assertEqual(raw["agent_details"][0]["status"], "COMPLETED")
        self.assertTrue(reviewed["report_corrections"])
        self.assertEqual(reviewed, normalize_result(reviewed))

    def test_harness_c_syntax_and_factorial_reference_cases(self):
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC is unavailable for this syntax smoke test.")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "submission.c").write_text(SOURCE)
            header = root / "klee"
            header.mkdir()
            (header / "klee.h").write_text(
                "#include <stddef.h>\nvoid klee_make_symbolic(void *,size_t,const char *);\n"
                "void klee_assume(unsigned long);\n")
            for backend in ("klee", "cbmc"):
                (root / "harness.c").write_text(harness("main", backend, SOURCE))
                run = subprocess.run([compiler, "-fsyntax-only", "-I", folder, str(root / "harness.c")],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            exe = root / "example"
            subprocess.run([compiler, str(root / "submission.c"), "-o", str(exe)], check=True)
            for value, expected in [("0\n", "Factorial of 0 = 1"),
                                    ("5\n", "Factorial of 5 = 120"),
                                    ("20\n", "Factorial of 20 = 2432902008176640000"),
                                    ("21\n", "Please enter a number between 0 and 20."),
                                    ("x\n", "Invalid input.")]:
                run = subprocess.run([str(exe)], input=value, capture_output=True, text=True, timeout=2)
                self.assertIn(expected, run.stdout)


if __name__ == "__main__":
    unittest.main()
