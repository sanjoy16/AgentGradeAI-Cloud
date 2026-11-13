"""Regressions for missing tools and the submitted factorial boundary."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import doctor
import verification as v

class RuntimePreflightTests(unittest.TestCase):
    def test_missing_dependency_prevents_full_launch(self):
        health = dict.fromkeys(('gcc','cppcheck','cbmc','z3','docker','docker_engine','klee_image'), True)
        health['z3'] = False
        with patch('doctor.tool_health', return_value=health), patch('sys.argv', ['doctor.py','--require-all']), patch('builtins.print'):
            self.assertEqual(doctor.main(), 1)

    def test_healthy_preflight_succeeds(self):
        with patch('doctor.tool_health', return_value={'ready': True}), patch('sys.argv', ['doctor.py','--require-all']), patch('builtins.print'):
            self.assertEqual(doctor.main(), 0)

    def test_daemon_and_image_have_distinct_remedies(self):
        health = {'docker':True,'docker_engine':False}
        self.assertIn('Open Docker Desktop', ' '.join(v.dependency_guidance(health)))
        health['docker_engine'] = True
        advice = ' '.join(v.dependency_guidance(health))
        self.assertIn('docker pull --platform linux/amd64', advice)
        self.assertNotIn('Open Docker Desktop', advice)

    @unittest.skipUnless(shutil.which('gcc'), 'GCC unavailable')
    def test_corrected_factorial_boundaries_and_failed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = str(Path(tmp)/'factorial')
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','examples/factorial_main_ull.c','-o',binary],check=True,capture_output=True)
            for token, answer in [('0','1'),('1','1'),('5','120'),('20','2432902008176640000')]:
                run = subprocess.run([binary],input=token+'\n',text=True,capture_output=True,timeout=2)
                self.assertEqual(run.returncode,0)
                self.assertIn('= '+answer+'\n',run.stdout)
            for token in ['-1','21','x','']:
                run = subprocess.run([binary],input=token,text=True,capture_output=True,timeout=2)
                self.assertNotEqual(run.returncode,0)

if __name__ == '__main__':
    unittest.main()
