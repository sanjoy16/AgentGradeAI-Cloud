import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import verification
from engine import evaluate
from knowledge import enrich
from reports import normalize_result
from storage import initialize, submit, get_submission, approve
from test_report_upgrade import RAW, SOURCE


class IntegrationTests(unittest.TestCase):
    def test_contract_harnesses_have_identical_domains(self):
        for backend in ("klee", "cbmc"):
            f = verification.harness("factorial", backend)
            self.assertIn("n >= 0", f)
            self.assertIn("n <= 12", f)
            self.assertIn("factorial(n) == expected", f)
            m = verification.harness("maximum", backend)
            self.assertIn("a >= -100", m)
            self.assertIn("b <= 100", m)
            self.assertIn("maximum(a, b)", m)
            self.assertIn("#define main gradeai_student_main", m)

    def test_missing_dependencies_are_not_successes(self):
        with patch("verification.shutil.which", return_value=None):
            records, artifacts = verification.execute(SOURCE, "main")
        self.assertEqual(records["llvm"]["status"], "UNAVAILABLE")
        self.assertEqual(records["symbolic"]["status"], "BLOCKED")
        self.assertEqual(records["verification"]["status"], "UNAVAILABLE")
        self.assertEqual(records["smt"]["status"], "UNAVAILABLE")
        self.assertIn("klee_harness.c", artifacts)

    def test_klee_partial_and_error_paths(self):
        self.assertEqual(verification.classify_klee(
            "KLEE: done: partially completed paths = 0", [], True)[0], "COMPLETED")
        self.assertEqual(verification.classify_klee(
            "KLEE: done: partially completed paths = 2", [], True)[0], "INCONCLUSIVE")
        self.assertEqual(verification.classify_klee("", ["test000001.assert.err\nassertion failed"], True)[0], "VIOLATED")
        self.assertEqual(verification.classify_klee("", [], False)[0], "INCONCLUSIVE")
        self.assertEqual(verification.classify_klee(
            "", ["test000001.exec.err\nunsupported instruction"], True)[0], "INCONCLUSIVE")

    def test_cbmc_timeout_tool_error_and_bound(self):
        base = dict(exit_code=0, timed_out=False, log="VERIFICATION SUCCESSFUL")
        self.assertEqual(verification.classify_cbmc(base)[0], "COMPLETED")
        self.assertEqual(verification.classify_cbmc(
            {**base, "exit_code": 10, "log": "VERIFICATION FAILED: unwinding assertion FAILURE"} )[0], "REVIEW REQUIRED")
        self.assertEqual(verification.classify_cbmc(
            {**base, "exit_code": 10, "log": "VERIFICATION FAILED"} )[0], "VIOLATED")
        self.assertEqual(verification.classify_cbmc(
            {**base, "exit_code": 6, "log": "PARSING ERROR"} )[0], "INCONCLUSIVE")
        self.assertEqual(verification.classify_cbmc(
            {**base, "timed_out": True} )[0], "INCONCLUSIVE")

    def test_graph_retrieval_is_cited_and_relevant(self):
        records = [{"status": "VIOLATED", "inputs": ["Function contract factorial"]}]
        evidence = [{"id": "E1", "agent": "KLEE"}]
        stages, graph, notes = enrich("int factorial(int n);", "Factorial", records, evidence)
        self.assertTrue(graph["triples"])
        self.assertTrue(any(n["id"] == "function-contract" for n in notes))
        self.assertTrue(all(n["source"] for n in notes))
        self.assertTrue(all(s["status"] == "COMPLETED" for s in stages))

    def test_analytics_retrieves_approved_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "data.db")
            initialize(path)
            old = submit(path, "Student", "R1", "Factorial", SOURCE, RAW)
            approve(path, old, 70, "Reviewed")
            result = normalize_result(RAW, SOURCE, "Factorial")
            result["report_schema_version"] = 3
            result["retrieved_notes"] = []
            sid = submit(path, "Student", "R1", "Factorial", SOURCE, result)
            stored = json.loads(get_submission(path, sid)["result_json"])
            analytics = next(s for s in stored["agent_details"] if s["key"] == "analytics")
            self.assertEqual(analytics["status"], "COMPLETED")
            self.assertIn("Attempt number: 2", analytics["outputs"])
            self.assertIn("Previous approved scores: [70]", analytics["outputs"])
            self.assertEqual(stored, normalize_result(stored, SOURCE, "Factorial"))

    def test_mocked_worker_artifacts_are_parsed(self):
        def fake_run(args, cwd=None, timeout=60):
            if args[:2] == ["docker", "run"]:
                target = next(args[i + 1] for i, a in enumerate(args)
                              if a == "-v" and args[i + 1].endswith(":/out"))
                out = Path(target[:-5])
                (out / "program.ll").write_text('define i32 @main() {\n br label %end\n}\n')
                (out / "klee.exit").write_text("0")
                (out / "klee.log").write_text("KLEE: done: partially completed paths = 0")
                q = out / "klee-output"
                q.mkdir()
                (q / "test000001.smt2").write_text("(check-sat)")
                return dict(exit_code=0, timed_out=False, log="fixture Docker worker")
            if args[0] == "z3":
                return dict(exit_code=0, timed_out=False, log="sat")
            return dict(exit_code=0, timed_out=False, log="VERIFICATION SUCCESSFUL")
        with patch("verification.shutil.which", return_value="/fixture/bin/tool"), patch("verification.command", side_effect=fake_run):
            records, artifacts = verification.execute("int maximum(int a,int b){return a>b?a:b;}", "maximum")
        self.assertTrue(all(s["status"] == "COMPLETED" for s in records.values()))
        self.assertEqual(len(artifacts["z3_queries"]), 1)
        self.assertIn("not a grading verdict", records["smt"]["result"])

    def test_actual_z3_binary_executes_queries(self):
        import shutil
        if not shutil.which("z3"):
            self.skipTest("Z3 binary is not installed.")
        with tempfile.TemporaryDirectory() as folder:
            q = Path(folder) / "actual.smt2"
            q.write_text("(set-logic QF_BV)\n(declare-const a (_ BitVec 32))\n"
                         "(assert (distinct (bvadd a #x00000001) a))\n(check-sat)\n")
            run = verification.command(["z3", str(q)])
            self.assertEqual(run["exit_code"], 0, run["log"])
            self.assertIn("sat", run["log"])

    def test_failed_tools_cannot_award_contract_credit(self):
        with patch("verification.shutil.which", return_value=None):
            result = evaluate("int maximum(int a,int b){return b+1;}", "Maximum", "maximum")
        self.assertEqual(result["agents"][1]["score"], 0)
        self.assertEqual(result["report_schema_version"], 4)
        self.assertTrue(result["review_required"])
        keys = {s["key"]: s for s in result["agent_details"]}
        self.assertEqual(keys["knowledge"]["status"], "COMPLETED")
        self.assertEqual(keys["graphrag"]["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
