import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PublicationGuardTests(unittest.TestCase):
    def run_submission(self, fail):
        workflow = (ROOT / '.github/workflows/update-data.yml').read_text()
        section = workflow.split('      - name: Commit data.json\n', 1)[1]
        script = textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / 'bin'
            bindir.mkdir()
            for command in ('git', 'python', 'cp', 'rm', 'mkdir', 'sleep'):
                path = bindir / command
                body = '#!/bin/sh\nprintf "%s\\n" "' + command + ' $*" >> "$COMMAND_LOG"\n'
                if command == 'python':
                    body += 'if [ "$1" = scripts/merge_history.py ] && [ "$FAIL_GUARD" = 1 ]; then exit 42; fi\n'
                if command == 'git':
                    body += 'if [ "$1" = diff ]; then exit 1; fi\n'
                path.write_text(body + 'exit 0\n')
                path.chmod(0o755)
            log = root / 'commands.log'
            env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH'],
                   'COMMAND_LOG': str(log), 'FAIL_GUARD': str(int(fail))}
            result = subprocess.run(['/bin/bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=root, env=env, capture_output=True, text=True)
            return result.returncode, log.read_text().splitlines()

    def test_failed_history_guard_stops_before_staging_or_pushing(self):
        code, commands = self.run_submission(True)
        self.assertEqual(code, 42)
        self.assertTrue(any('archive_snapshot.py' in command for command in commands))
        self.assertTrue(any('merge_history.py' in command for command in commands))
        self.assertFalse(any(command.startswith(('git add ', 'git commit ', 'git push')) for command in commands))

    def test_successful_guard_allows_normal_submission(self):
        code, commands = self.run_submission(False)
        self.assertEqual(code, 0)
        self.assertEqual(commands.count('git push'), 1)
        self.assertTrue(any(command.startswith('git commit ') for command in commands))

if __name__ == '__main__':
    unittest.main()
