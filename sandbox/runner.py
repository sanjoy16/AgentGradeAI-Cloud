"""Container entrypoint; never import this module in the web or worker service."""
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(args, stdin='', timeout=12):
    # File-backed capture bounds memory even for malicious infinite output.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            p = subprocess.run(args, input=stdin.encode(), stdout=out, stderr=err,
                               timeout=timeout, preexec_fn=limits, env={'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': '/tmp'})
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = -124
        out.seek(0)
        err.seek(0)
        return {'code': code, 'stdout': out.read(16000).decode('utf-8', 'replace'),
                'stderr': err.read(16000).decode('utf-8', 'replace')}


def main(p):
    Path('/work/submission.c').write_text(p['source'])
    action = p['action']
    if action == 'compile':
        return run(['gcc', '-std=c17', '-Wall', '-Wextra', '-Wpedantic', '-fsyntax-only', '/work/submission.c'])
    if action == 'static':
        return run(['cppcheck', '--enable=all', '--inconclusive', '--template=gcc', '--quiet', '/work/submission.c'])
    if action == 'security':
        return run(['clang', '--analyze', '-Xanalyzer', '-analyzer-output=text', '/work/submission.c', '-o', '/tmp/analysis.plist'])
    if action == 'tests':
        compiled = run(['gcc', '-std=c17', '-O0', '-g', '-fsanitize=undefined', '/work/submission.c', '-o', '/tmp/program'])
        if compiled['code']:
            return dict(compile=compiled, cases=[])
        cases = []
        for i, test in enumerate(p['tests']):
            r = run(['/tmp/program'], test['stdin'], timeout=3)
            cases.append(dict(index=i + 1, passed=r['code'] == 0 and not r['stderr'] and
                              r['stdout'].strip() == test['expected'].strip(), **r))
        return dict(compile=compiled, cases=cases)
    if action in ('formal', 'symbolic'):
        if not p.get('harness'):
            return dict(unavailable='No faculty-authored function harness configured.')
        tool = 'cbmc' if action == 'formal' else 'klee'
        if not shutil.which(tool):
            return dict(unavailable=f'{tool} is not installed in this sandbox image.')
        Path('/work/contract.c').write_text(p['source'] + '\n' + p['harness'])
        if action == 'formal':
            return run(['cbmc', '/work/contract.c', '--function', 'harness', '--unwind', '32',
                        '--unwinding-assertions', '--bounds-check', '--pointer-check',
                        '--signed-overflow-check'], timeout=45)
        c = run([os.environ.get('KLEE_CLANG', 'clang'), '-DAGENTGRADE_KLEE', '-emit-llvm', '-c', '-g', '-O0', '-Xclang', '-disable-O0-optnone',
                 '/work/contract.c', '-o', '/tmp/contract.bc'])
        if c['code']:
            return c
        result = run(['klee', '--entry-point=harness', '--max-time=30s', '--max-memory=128',
                      '--output-dir=/tmp/klee-output', '/tmp/contract.bc'], timeout=40)
        errors = list(Path('/tmp/klee-output').glob('*.err'))
        result['errors'] = [e.read_text()[:2000] for e in errors[:10]]
        return result
    raise ValueError('Unknown action')

try:
    payload = json.loads(sys.stdin.read(200000))
    print(json.dumps(main(payload)))
except Exception as exc:
    print(json.dumps({'unavailable': f'Sandbox analysis error: {type(exc).__name__}'}))
