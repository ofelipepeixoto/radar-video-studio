"""Offline Dockerfile source/retry contracts; not an image build or media test."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


class DockerBaseTests(unittest.TestCase):
    def run_install(self, mirror, fail=False):
        source = DOCKERFILE.read_text()
        block = source.split('RUN set -u; ', 1)[1].split('\n\n# Copy only', 1)[0]
        script = 'set -u; ' + block.replace('\\\n', ' ')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('apt/sources.list.d', 'lists', 'bin'):
                (root / name).mkdir(parents=True)
            (root / 'apt/sources.list.d/debian.sources').write_text('original source')
            script = script.replace('/etc/apt', str(root / 'apt')).replace('/var/lib/apt/lists', str(root / 'lists'))
            (root / 'bin/apt-get').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit "$APT_RESULT"\n')
            (root / 'bin/sleep').write_text('#!/bin/sh\nexit 0\n')
            for p in (root / 'bin').iterdir():
                p.chmod(0o700)
            result = subprocess.run(['/bin/sh', '-c', script], capture_output=True, text=True, env={**os.environ, 'PATH': str(root/'bin') + ':' + os.environ['PATH'], 'DOCKER_BUILD_MIRROR': mirror, 'CALL_LOG': str(root/'calls'), 'APT_RESULT': str(int(fail))}, timeout=5)
            return result, (root/'apt/sources.list').read_text(), (root/'calls').read_text(), (root/'apt/sources.list.d/debian.sources').exists()

    def test_supported_base_keeps_python(self):
        text = DOCKERFILE.read_text()
        self.assertIn('FROM python:3.11-slim-bookworm', text)
        self.assertNotIn('bullseye', text)

    def test_default_sources_and_dependencies(self):
        result, sources, calls, old = self.run_install('default')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sources, 'deb https://deb.debian.org/debian bookworm main\ndeb https://deb.debian.org/debian bookworm-updates main\ndeb https://deb.debian.org/debian-security bookworm-security main\n')
        self.assertFalse(old)
        self.assertIn('install -y --no-install-recommends git ffmpeg', calls)

    def test_china_sources_preserved(self):
        result, sources, _, old = self.run_install('china')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://mirrors.aliyun.com/debian bookworm main', sources)
        self.assertFalse(old)

    def test_default_failure_stops_after_three_attempts(self):
        result, _, calls, _ = self.run_install('default', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count('update'), 3)
        self.assertNotIn('install', calls)

    def test_china_failure_uses_all_fallbacks_then_stops(self):
        result, sources, calls, _ = self.run_install('china', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count('update'), 5)
        self.assertIn('https://deb.debian.org/debian bookworm main', sources)


if __name__ == '__main__':
    unittest.main()
