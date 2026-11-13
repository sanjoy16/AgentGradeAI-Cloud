"""Input-model regression tests; native execution validates the adapter, not a student program."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import verification as v

SOURCE = '''#include <stdio.h>
int main(void) {
    char buf[64]; int n, mark;
    if (scanf("%63s", buf) != 1) return 1;
    if (scanf("%d %d", &n, &mark) != 2) return 1;
    return 0;
}'''


class InputModelTests(unittest.TestCase):
    def test_formats_in_comments_and_strings_are_ignored(self):
        source = '// scanf("%f", &x);\nchar *s = "scanf(fake)"; /* scanf(x); */'
        self.assertEqual(v.main_io_model(source), 'symbolic_bytes')
        self.assertEqual(v.main_io_model(source + '\n' + SOURCE), 'bounded_tokens')
        self.assertEqual(v.main_io_model('scanf("%d %d", &a, &b);'), 'integer_tokens')

    def test_unsupported_formats_stay_explicit(self):
        for fmt in ('%s', '%f', '%257s', '%0s', '%*d', '%d%d', '%ld', '%[a-z]'):
            with self.subTest(fmt=fmt):
                self.assertEqual(v.main_io_model('scanf("' + fmt + '", p);'), 'unsupported')
        self.assertEqual(v.main_io_model('scanf(format, p);'), 'unsupported')

    def test_both_backends_accept_bounded_string_harness_in_strict_c(self):
        gcc = shutil.which('gcc')
        if not gcc:
            self.skipTest('GCC not installed')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'submission.c').write_text(SOURCE)
            (root/'klee').mkdir()
            (root/'klee/klee.h').write_text('#include <stddef.h>\nvoid klee_make_symbolic(void*,size_t,const char*);\nvoid klee_assume(unsigned long);\n')
            for backend in ('cbmc', 'klee'):
                with self.subTest(backend=backend):
                    code = v.harness('main', backend, SOURCE)
                    self.assertIn('target[length] = 0;', code)
                    (root/'harness.c').write_text(code)
                    run = subprocess.run([gcc, '-std=c11', '-Werror', '-fsyntax-only', '-I',folder,str(root/'harness.c')],capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stderr)

    def test_actual_adapter_assignments_failure_eof_partial_and_terminator(self):
        gcc = shutil.which('gcc')
        if not gcc:
            self.skipTest('GCC not installed')
        # Declare call sites to select formats without executing a submitted main.
        source = 'void unused(void) { int a; char b[64]; scanf("%d %63s", &a,b); }'
        driver = r'''
#include <assert.h>
static int values[80], pos;
int gradeai_nondet_int(void) { return values[pos++]; }
void __CPROVER_assume(_Bool x) { assert(x); }
void __CPROVER_assert(_Bool x, const char *s) { (void)s; assert(x); }
int main(void) {
    int a=99; struct { char b[64]; unsigned char guard; } out;
    memset(out.b,'X',64); out.guard=123;
    values[0]=0; pos=0;
    assert(gradeai_scanf("%d %63s", &a,out.b)==0 && a==99 && out.b[0]=='X');
    values[0]=-1; pos=0;
    assert(gradeai_scanf("%d %63s", &a,out.b)==-1 && a==99 && out.b[0]=='X');
    values[0]=1; values[1]=7; pos=0;
    assert(gradeai_scanf("%d %63s", &a,out.b)==1 && a==7 && out.b[0]=='X');
    values[0]=2; values[1]=8; values[2]=3;
    values[3]='A'; values[4]='B'; values[5]='C'; pos=0;
    assert(gradeai_scanf("%d %63s", &a,out.b)==2 && a==8);
    assert(strcmp(out.b,"ABC")==0 && out.guard==123);
    values[2]=63; for(int i=3;i<66;i++) values[i]='Z'; pos=0;
    assert(gradeai_scanf("%d %63s", &a,out.b)==2);
    assert(strlen(out.b)==63 && out.b[63]==0 && out.guard==123);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'submission.c').write_text(source)
            (root/'harness.c').write_text(v.harness('main','cbmc',source)+driver)
            build=subprocess.run([gcc,'-std=c11','-Werror',str(root/'harness.c'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_string_profile_dispatches_verifiers_and_adjusts_unwind(self):
        commands=[]
        def run(args,cwd=None,timeout=60):
            commands.append(args)
            if args[:2]==['docker','run']:
                out=Path(next(args[i+1][:-5] for i,a in enumerate(args) if a=='-v' and args[i+1].endswith(':/out')))
                (out/'program.ll').write_text('define i32 @main() {\n ret i32 0\n}')
                (out/'klee.exit').write_text('0')
                (out/'klee.log').write_text('KLEE: done: partially completed paths = 0')
                (out/'klee-output').mkdir();(out/'klee-output/test.smt2').write_text('(check-sat)')
            return dict(exit_code=0,timed_out=False,log='sat\nVERIFICATION SUCCESSFUL')
        with patch('verification.shutil.which',return_value='/fixture/tool'),patch('verification.command',side_effect=run):
            records,artifacts=v.execute(SOURCE,'main')
        self.assertEqual(artifacts['input_model'],'bounded_tokens')
        self.assertTrue(all(x['status']=='COMPLETED' for x in records.values()))
        cbmc=next(x for x in commands if x[0]=='cbmc')
        self.assertEqual(cbmc[cbmc.index('--unwind')+1],'64')
        self.assertIn('--unsigned-overflow-check', cbmc)
        self.assertIn('stream persistence',records['verification']['outputs'][-1])

    def test_unsupported_input_does_not_disable_llvm(self):
        def run(args,cwd=None,timeout=60):
            self.assertNotEqual(args[0],'cbmc')
            if args[:2]==['docker','run']:
                out=Path(next(args[i+1][:-5] for i,a in enumerate(args) if a=='-v' and args[i+1].endswith(':/out')))
                (out/'program.ll').write_text('define i32 @main() {\n ret i32 0\n}')
                self.assertNotIn('klee --max-time',args[-1])
            return dict(exit_code=0,timed_out=False,log='fixture')
        with patch('verification.shutil.which',return_value='/fixture/tool'),patch('verification.command',side_effect=run):
            records,_=v.execute('int main(void){float x;scanf("%f",&x);return 0;}','main')
        self.assertEqual(records['llvm']['status'],'COMPLETED')
        for key in ('symbolic','smt','verification'):
            self.assertEqual(records[key]['status'],'BLOCKED')
            self.assertTrue(records[key]['result'])


if __name__=='__main__':
    unittest.main()
