"""Loopback-only WAV A/B trial UI; independent of PowerfulTS live services."""
import base64
import json
import threading
import io
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
import torch
import torchaudio.functional as audio_functional
from urllib.parse import urlparse

from experiment import Engines, ROOT, read_audio, save

ENGINES = Engines()
LOCK = threading.Lock()
REFERENCES = OrderedDict()
PAGE = Path(__file__).with_name('index.html').read_bytes()
PORT = 18186


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.respond(PAGE, 'text/html; charset=utf-8')
        if path == '/report':
            report = ROOT / 'report.json'
            return self.respond(report.read_bytes() if report.exists() else b'{}', 'application/json')
        if path.startswith('/audio/'):
            # Only basenames from the dedicated lab output directory are served.
            name = path.removeprefix('/audio/')
            if Path(name).name != name or not name.endswith('.wav'):
                return self.send_error(404)
            file = ROOT / 'samples' / name
            if file.is_file():
                return self.respond(file.read_bytes(), 'audio/wav')
        self.send_error(404)

    def do_POST(self):
        if self.path == '/pcm':
            return self.process_pcm()
        if self.path != '/process':
            return self.send_error(404)
        # Local page only: reject cross-origin submissions and oversized clips.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{PORT}':
            return self.send_error(403)
        size = int(self.headers.get('Content-Length', '0'))
        if size < 1 or size > 16 * 1024 * 1024:
            return self.send_error(413)
        if not LOCK.acquire(blocking=False):
            return self.respond(b'{"error":"An experiment is already running"}', 'application/json', 409)
        try:
            request = json.loads(self.rfile.read(size))
            mode = request['mode']
            if mode not in ('deepfilter', 'spex'):
                raise ValueError('Unknown mode')
            folder = ROOT / 'samples'
            folder.mkdir(parents=True, exist_ok=True)
            input_path = folder / 'custom-input.wav'
            input_path.write_bytes(base64.b64decode(request['input'], validate=True))
            rate = 48000 if mode == 'deepfilter' else 8000
            samples = read_audio(input_path, rate)
            if samples.shape[-1] > rate * 30:
                raise ValueError('Maximum input duration is 30 seconds')
            reference = None
            if mode == 'spex':
                reference_path = folder / 'custom-reference.wav'
                reference_path.write_bytes(base64.b64decode(request['reference'], validate=True))
                reference = read_audio(reference_path, rate)
                if not 2 * rate <= reference.shape[-1] <= 15 * rate:
                    raise ValueError('Reference must be 2–15 seconds of solo speech')
            started = time.perf_counter()
            result = ENGINES.deepfilter(samples) if mode == 'deepfilter' else ENGINES.extract(samples, reference)
            elapsed = time.perf_counter() - started
            output_path = folder / 'custom-output.wav'
            save(output_path, result, rate)
            self.respond(json.dumps({'url': '/audio/custom-output.wav', 'seconds': elapsed,
                                     'duration': samples.shape[-1] / rate}).encode(), 'application/json')
        except Exception as error:
            self.respond(json.dumps({'error': str(error)}).encode(), 'application/json', 400)
        finally:
            LOCK.release()

    def respond(self, content, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def process_pcm(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 1 <= size <= 5 * 1024 * 1024:
            return self.send_error(413)
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{PORT}':
            return self.send_error(403)
        if not LOCK.acquire(blocking=False):
            return self.respond(b'{"error":"Model busy"}', 'application/json', 429)
        try:
            request = json.loads(self.rfile.read(size))
            mode = request['mode']
            if mode not in ('deepfilter', 'spex', 'combined'):
                raise ValueError('Unknown mode')
            pcm = np.frombuffer(base64.b64decode(request['pcm'], validate=True), dtype='<f4').copy()
            if not 24000 <= len(pcm) <= 144000 or not np.isfinite(pcm).all():
                raise ValueError('PCM must be 0.5–3 seconds at 48 kHz')
            samples = torch.from_numpy(pcm).unsqueeze(0)
            if mode in ('spex', 'combined'):
                key = request.get('referenceKey', '')
                if 'reference' in request:
                    reference = np.frombuffer(base64.b64decode(request['reference'], validate=True), dtype='<f4').copy()
                    if not 96000 <= len(reference) <= 720000 or not np.isfinite(reference).all():
                        raise ValueError('Reference must be 2–15 seconds at 48 kHz')
                    reference = audio_functional.resample(torch.from_numpy(reference).unsqueeze(0), 48000, 8000)
                    if key:
                        REFERENCES[key] = reference
                        REFERENCES.move_to_end(key)
                        while len(REFERENCES) > 32:
                            REFERENCES.popitem(last=False)
                else:
                    reference = REFERENCES.get(key)
                    if reference is None:
                        raise ValueError('Reference expired; resend enrollment')
                samples8 = audio_functional.resample(samples, 48000, 8000)
                samples = audio_functional.resample(ENGINES.extract(samples8, reference), 8000, 48000)
            if mode in ('deepfilter', 'combined'):
                samples = ENGINES.deepfilter(samples)
            data = samples.flatten().numpy()[:len(pcm)]
            if not np.isfinite(data).all():
                raise ValueError('Invalid model output')
            peak = float(np.max(np.abs(data)))
            if peak > 0.95:
                data = data * (0.95 / peak)
            self.respond(data.astype('<f4').tobytes(), 'application/octet-stream')
        except Exception as error:
            self.respond(json.dumps({'error': str(error)}).encode(), 'application/json', 400)
        finally:
            LOCK.release()


if __name__ == '__main__':
    print(f'Audio lab: http://127.0.0.1:{PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
