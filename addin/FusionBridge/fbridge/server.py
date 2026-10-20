"""Localhost HTTP server that queues jobs for Fusion's main thread.

No adsk imports here, so the plumbing can be tested outside Fusion.

Protocol: POST /<command> with a JSON body and the X-Bridge-Token header.
The response is the JSON dict returned by the command, always with an "ok" key.
Port and token are written to ~/.fusion-bridge/connection.json (mode 0600) for the CLI.
"""
import hmac
import json
import os
import secrets
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 18360
PORT_RANGE = 10
DEFAULT_TIMEOUT = 120.0


def config_path():
    return os.path.join(os.path.expanduser('~'), '.fusion-bridge', 'connection.json')


class Job:
    def __init__(self, command, args):
        self.id = uuid.uuid4().hex
        self.command = command
        self.args = args
        self.done = threading.Event()
        self.started = False
        self.cancelled = False
        self.response = None


class Bridge:
    def __init__(self, post_to_main, port=DEFAULT_PORT):
        """post_to_main(job_id) must schedule run_job(job_id, ...) on the main thread."""
        self._post = post_to_main
        self._base_port = port
        self._jobs = {}
        self._lock = threading.Lock()
        self._busy = False
        self._deferred = []
        self._httpd = None
        self.token = None
        self.port = None

    # --- lifecycle (main thread) ---

    def start(self):
        self.token = secrets.token_hex(16)
        last_error = None
        for port in range(self._base_port, self._base_port + PORT_RANGE):
            try:
                self._httpd = ThreadingHTTPServer(('127.0.0.1', port), _Handler)
                break
            except OSError as e:
                last_error = e
        if self._httpd is None:
            raise RuntimeError('No free port in %d-%d: %s'
                               % (self._base_port, self._base_port + PORT_RANGE - 1, last_error))
        self._httpd.bridge = self
        self.port = self._httpd.server_address[1]
        self._write_config()
        threading.Thread(target=self._httpd.serve_forever, name='FusionBridgeHTTP', daemon=True).start()
        return self.port

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        with self._lock:
            for job in self._jobs.values():
                job.response = {'ok': False, 'error': 'FusionBridge stopped'}
                job.done.set()
        try:
            with open(config_path()) as f:
                if json.load(f).get('token') == self.token:
                    os.remove(config_path())
        except (OSError, ValueError):
            pass

    def _write_config(self):
        path = config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'port': self.port, 'token': self.token, 'pid': os.getpid()}, f)

    # --- HTTP threads ---

    def submit(self, command, args, timeout):
        job = Job(command, args)
        with self._lock:
            self._jobs[job.id] = job
        try:
            self._post(job.id)
            if job.done.wait(timeout):
                return job.response
            with self._lock:
                if not job.started:
                    job.cancelled = True
            if job.started:
                hint = 'the job is still running inside Fusion'
            else:
                hint = 'Fusion never picked the job up (modal dialog or active command?); job cancelled'
            return {'ok': False, 'error': 'Timed out after %gs: %s' % (timeout, hint)}
        finally:
            with self._lock:
                self._jobs.pop(job.id, None)

    # --- main thread ---

    def run_job(self, job_id, dispatch):
        # adsk.doEvents() inside a command can deliver the next custom event re-entrantly:
        # defer it until the current job is finished.
        if self._busy:
            self._deferred.append(job_id)
            return
        self._busy = True
        try:
            self._run_one(job_id, dispatch)
            while self._deferred:
                self._run_one(self._deferred.pop(0), dispatch)
        finally:
            self._busy = False

    def _run_one(self, job_id, dispatch):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.cancelled:
                return
            job.started = True
        try:
            res = dispatch(job.command, job.args)
            if not isinstance(res, dict):
                res = {'result': res}
            res.setdefault('ok', True)
        except Exception as e:
            res = {'ok': False, 'error': '%s: %s' % (type(e).__name__, e),
                   'traceback': traceback.format_exc()}
        job.response = res
        job.done.set()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        bridge = self.server.bridge
        if not hmac.compare_digest(self.headers.get('X-Bridge-Token', ''), bridge.token):
            return self._send(401, {'ok': False, 'error': 'invalid token'})
        try:
            length = int(self.headers.get('Content-Length') or 0)
            args = json.loads(self.rfile.read(length) or b'{}')
            timeout = float(args.pop('_timeout', DEFAULT_TIMEOUT))
        except (ValueError, AttributeError) as e:
            return self._send(400, {'ok': False, 'error': 'bad request body: %s' % e})
        self._send(200, bridge.submit(self.path.strip('/'), args, timeout))

    def _send(self, code, obj):
        body = json.dumps(obj, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # sys.stderr may be None inside Fusion
