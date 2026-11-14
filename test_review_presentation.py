"""Student-facing reporting keeps evidence honest and excludes raw debug dumps."""
from io import BytesIO
import ast
from pathlib import Path
import unittest
from pypdf import PdfReader
from reports import pdf_report
from review_report import agent_rows
import test_concise_report

class ReviewPresentationTests(unittest.TestCase):
    def test_compact_rows_preserve_all_statuses(self):
        result=test_concise_report.ConciseReportTests().fixture()
        rows=agent_rows(result)
        self.assertEqual(len(rows),len(result['agent_details']))
        self.assertEqual([x['Status'] for x in rows],[x['status'] for x in result['agent_details']])
        self.assertTrue(all(set(x)=={'Agent','Status','Finding / scope','Evidence'} for x in rows))

    def test_pdf_never_converts_unavailable_to_pass_or_exposes_logs(self):
        result=test_concise_report.ConciseReportTests().fixture()
        result['agent_details'][3].update(status='UNAVAILABLE',result='Worker unavailable.',raw_evidence=['PRIVATE DEBUG DUMP'])
        original=result['approved_score']
        reader=PdfReader(BytesIO(pdf_report('A<&','R1','Factorial <&>',result)))
        text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('UNAVAILABLE',text)
        self.assertIn('Worker unavailable.',text)
        self.assertNotIn('PRIVATE DEBUG DUMP',text)
        self.assertNotIn('Confidence:',text)
        self.assertEqual(result['approved_score'],original)
        self.assertIn('How to revise',text)

    def test_details_and_source_are_collapsed_by_default(self):
        tree=ast.parse(Path('app.py').read_text())
        labels=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='expander' and node.args and isinstance(node.args[0],ast.Constant):
                if node.args[0].value in ('Technical evidence and execution details','Submitted source code'):
                    self.assertTrue(any(k.arg=='expanded' and isinstance(k.value,ast.Constant) and k.value.value is False for k in node.keywords))
                    labels.append(node.args[0].value)
        self.assertEqual(len(labels),2)
