from io import BytesIO
import unittest

from pypdf import PdfReader
from reports import pdf_report
from detailed_report import proposed_tests, recorded_inputs
import test_concise_report


class DetailedReportTests(unittest.TestCase):
    def test_tsp_guidance_distinguishes_advice_from_executed_tests(self):
        result = test_concise_report.ConciseReportTests().fixture()
        result["source"] = "int main() { int mask, n; return mask == (1 << n) - 1; }"
        title = "Program to implement travelling salesman problem"
        data = pdf_report("Student", "001", title, result)
        reader = PdfReader(BytesIO(data))
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertLessEqual(len(reader.pages), 7)
        for phrase in ["How to revise", "Tests to run after revision", "unverified credit",
                       "not been executed", "Minimum round-trip cost 80",
                       "Submitted source and review map"]:
            self.assertIn(phrase, text)

    def test_ktest_examples_prefer_matching_error_ids(self):
        result = {"tool_artifacts": {
            "klee_errors": ["test000002.assert.err\nAssertion failed"],
            "klee_test_inputs": (
                "ktest file : '/out/test000001.ktest'\nobject 0: name: 'a'\nobject 0: int : 9\n"
                "ktest file : '/out/test000002.ktest'\nobject 0: name: 'a'\nobject 0: int : 5\n"
                "object 1: name: 'b'\nobject 1: int : 5\n")}}
        self.assertEqual(recorded_inputs(result), ["test000002 - a=5, b=5"])

    def test_unsigned_factorial_test_plan(self):
        tests = proposed_tests("unsigned long long factorial;", "Factorial")
        self.assertTrue(any(value == "n=20" for _, value, _ in tests))


if __name__ == "__main__":
    unittest.main()
