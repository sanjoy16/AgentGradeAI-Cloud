import unittest
from student_guidance import repair_cards, agent_help, readable

class StudentGuidanceTests(unittest.TestCase):
    def test_factorial_actions_are_concrete_and_advisory(self):
        result={'source':'int main() {\n scanf("%d", &n);\n unsigned long long factorial=1;\n}', 'agents':[{'evidence':'submission.c:2: warning variableScope'}]}
        cards=repair_cards(result)
        self.assertEqual(len(cards),4)
        self.assertTrue(all(c['change'] and c['example'] and c['test'] for c in cards))
        self.assertIn('Source-review advice',cards[2]['why'])
        self.assertIn('21',cards[2]['test'])

    def test_checked_scan_is_not_reported_as_unchecked(self):
        cards=repair_cards({'source':'int main(void) { if (scanf("%d", &n) != 1) return 1; }'})
        self.assertFalse(any(c['title']=='Check whether input was read' for c in cards))

    def test_missing_tool_is_not_a_student_code_defect(self):
        _,action=agent_help({'key':'verification','status':'UNAVAILABLE'})
        self.assertIn('Do not change code solely',action)

    def test_temp_paths_are_not_student_feedback(self):
        self.assertEqual(readable('/var/folders/abc/tmp123/submission.c:3:9: warning'),'submission.c:3:9: warning')
