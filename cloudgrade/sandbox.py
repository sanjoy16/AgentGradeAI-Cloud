"""Only the worker imports this adapter. No host execution fallback exists."""
import json
import os
import subprocess
import uuid

class DockerSandbox:
    def run(self, source, action, tests=None, harness=''):
        name = 'agentgrade-' + uuid.uuid4().hex
        command = ['docker', 'run', '--rm', '-i', '--name', name,
                   '--network=none', '--read-only', '--cap-drop=ALL',
                   '--security-opt=no-new-privileges', '--pids-limit=32',
                   '--memory=256m', '--memory-swap=256m', '--cpus=0.5',
                   '--ulimit', 'nofile=64:64', '--ulimit', 'fsize=1048576:1048576',
                   '--tmpfs', '/work:rw,noexec,nosuid,size=32m,uid=65534,gid=65534',
                   '--tmpfs', '/tmp:rw,exec,nosuid,size=32m,uid=65534,gid=65534',
                   '--env', 'HTTP_PROXY=', '--env', 'HTTPS_PROXY=',
                   '--env', 'ALL_PROXY=', '--env', 'http_proxy=', '--env', 'https_proxy=']
        # /tmp permits execution of compiler output; /work is source-only.
        runtime = os.environ.get('SANDBOX_RUNTIME', 'runsc')
        if runtime:
            command += ['--runtime', runtime]
        image = os.environ.get('SANDBOX_' + action.upper() + '_IMAGE') or os.environ.get('SANDBOX_IMAGE', 'agentgrade-sandbox:1')
        command += [image]
        try:
            result = subprocess.run(command, input=json.dumps(dict(source=source, action=action,
                tests=tests or [], harness=harness)), text=True, capture_output=True, timeout=75,
                env={k: v for k, v in os.environ.items() if k not in ('OPENAI_API_KEY', 'SECRET_KEY', 'DATABASE_URL')})
            if result.returncode:
                raise RuntimeError('Sandbox unavailable or failed: ' + result.stderr[:600])
            data = json.loads(result.stdout)
            if not isinstance(data, dict):
                raise ValueError('Invalid sandbox response')
            return data
        except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
            raise RuntimeError('Sandbox job did not return valid evidence') from exc
        finally:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15)
