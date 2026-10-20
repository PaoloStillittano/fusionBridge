"""End-to-end test of server + CLI with a fake 'main thread' instead of Fusion."""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'addin', 'FusionBridge'))
from fbridge import server  # noqa: E402

CLI = os.path.join(HERE, '..', 'cli', 'f360')


def fake_dispatch(command, args):
    if command == 'ping':
        return {'document': 'fake'}
    if command == 'exec':
        ns = {'result': None}
        exec(args['code'], ns)
        return {'ok': True, 'stdout': '', 'result': ns['result']}
    if command == 'slow':
        time.sleep(args.get('seconds', 1))
        return {}
    raise ValueError('Unknown command %r' % command)


class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls._old_home = os.environ.get('HOME')
        os.environ['HOME'] = cls.home
        cls.q = queue.Queue()
        cls.paused = threading.Event()
        cls.bridge = server.Bridge(cls.q.put, port=28360)
        cls.port = cls.bridge.start()

        def main_loop():
            while True:
                job_id = cls.q.get()
                if job_id is None:
                    return
                while cls.paused.is_set():
                    time.sleep(0.05)
                cls.bridge.run_job(job_id, fake_dispatch)
        cls.main = threading.Thread(target=main_loop, daemon=True)
        cls.main.start()

    @classmethod
    def tearDownClass(cls):
        cls.q.put(None)
        cls.bridge.stop()
        os.environ['HOME'] = cls._old_home

    def cli(self, *args):
        p = subprocess.run([sys.executable, CLI] + list(args), capture_output=True, text=True,
                           env=dict(os.environ, HOME=self.home))
        return p.returncode, p.stdout, p.stderr

    def test_config_written_private(self):
        path = os.path.join(self.home, '.fusion-bridge', 'connection.json')
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        with open(path) as f:
            self.assertEqual(json.load(f)['port'], self.port)

    def test_ping(self):
        code, out, _ = self.cli('ping')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {'document': 'fake', 'ok': True})

    def test_exec_result(self):
        code, out, _ = self.cli('exec', '-c', 'result = 6 * 7')
        self.assertEqual(code, 0)
        summary = json.loads(out.split('--- summary ---\n')[1])
        self.assertEqual(summary['result'], 42)

    def test_command_error_exit_1(self):
        code, out, _ = self.cli('exec', '-c', '1/0')
        self.assertEqual(code, 1)
        self.assertIn('ZeroDivisionError', out)

    def test_bad_token_rejected(self):
        req = urllib.request.Request('http://127.0.0.1:%d/ping' % self.port, data=b'{}',
                                     headers={'X-Bridge-Token': 'nope'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            opener.open(req)
        self.assertEqual(cm.exception.code, 401)

    def test_timeout_cancels_queued_job(self):
        self.paused.set()  # main thread "busy" (e.g. modal dialog)
        try:
            res = self.bridge.submit('ping', {}, timeout=0.3)
        finally:
            self.paused.clear()
        self.assertFalse(res['ok'])
        self.assertIn('never picked the job up', res['error'])

    def test_reentrant_job_is_deferred(self):
        order = []

        def dispatch(command, args):
            order.append(command)
            if command == 'outer':  # simulate adsk.doEvents() delivering the next event
                self.bridge.run_job(inner.id, dispatch)
                order.append('outer-done')
            return {}
        outer, inner = server.Job('outer', {}), server.Job('inner', {})
        self.bridge._jobs.update({outer.id: outer, inner.id: inner})
        self.bridge.run_job(outer.id, dispatch)
        self.assertEqual(order, ['outer', 'outer-done', 'inner'])
        self.assertTrue(inner.done.is_set())

    def test_not_running_exit_2(self):
        empty = tempfile.mkdtemp()
        p = subprocess.run([sys.executable, CLI, 'ping'], capture_output=True, text=True,
                           env=dict(os.environ, HOME=empty))
        self.assertEqual(p.returncode, 2)
        self.assertIn('not running', p.stderr)


if __name__ == '__main__':
    unittest.main()
