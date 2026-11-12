import os
import pytest
from cloudgrade.sandbox import DockerSandbox

pytestmark = pytest.mark.skipif(os.environ.get('RUN_SANDBOX_TESTS') != '1', reason='Requires locally built sandbox image and Docker.')

def test_real_compilation_testing_and_isolation(monkeypatch):
    monkeypatch.setenv('SANDBOX_RUNTIME', os.environ.get('TEST_SANDBOX_RUNTIME', ''))
    sandbox = DockerSandbox()
    good = '#include <stdio.h>\nint main(void){int a,b;if(scanf("%d%d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}'
    assert sandbox.run(good, 'compile')['code'] == 0
    result = sandbox.run(good, 'tests', [{'stdin': '2 3\n', 'expected': '5\n'}, {'stdin': '-3 3\n', 'expected': '0\n'}])
    assert all(c['passed'] for c in result['cases'])
    assert sandbox.run('int main( {', 'compile')['code'] != 0
    failed = sandbox.run('int main(void){return 1;}', 'tests', [{'stdin': '', 'expected': ''}])
    assert not failed['cases'][0]['passed']
    infinite = sandbox.run('int main(void){while(1){} }', 'tests', [{'stdin': '', 'expected': ''}])
    assert not infinite['cases'][0]['passed']
    # No host paths/secrets or network interfaces other than loopback are present.
    probe = '#include <stdio.h>\n#include <stdlib.h>\nint main(void){printf("%d %d",fopen("/var/run/docker.sock","r")!=0,getenv("SECRET_KEY")!=0);return 0;}'
    result = sandbox.run(probe, 'tests', [{'stdin': '', 'expected': '0 0'}])
    assert result['cases'][0]['passed']
