import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from silence_cutter import (
    APP_VERSION,
    CutterOptions,
    _format_bytes,
    _format_duration,
    build_batch_jobs,
    count_audio_streams,
    cut_video,
    cut_video_batch,
    default_ffmpeg_path,
    load_presets,
    parse_duration,
)

APP_DIR = Path(__file__).resolve().parent
WEB_HOST = "127.0.0.1"
WEB_PORT = 8765

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _new_job_id() -> str:
    return f"job_{int(time.time() * 1000)}_{os.getpid()}"


class EncutHTTPHandler(BaseHTTPRequestHandler):
    server_version = f"Encut/{APP_VERSION}"

    def log_message(self, format, *args):
        pass

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/" or route == "/index.html":
            self._send_file(APP_DIR / "encut_static/index.html", "text/html; charset=utf-8")
        elif route == "/style.css":
            self._send_file(APP_DIR / "encut_static/style.css", "text/css; charset=utf-8")
        elif route == "/app.js":
            self._send_file(APP_DIR / "encut_static/app.js", "application/javascript; charset=utf-8")
        elif route == "/api/status":
            self._send_json({"version": APP_VERSION, "ffmpeg": default_ffmpeg_path()})
        elif route == "/api/presets":
            self._send_json(load_presets())
        elif route.startswith("/api/probe/"):
            self._handle_probe(urllib.parse.unquote(route[len("/api/probe/"):]))
        elif route.startswith("/api/job/"):
            self._handle_job_status(route[len("/api/job/"):])
        elif route == "/api/jobs":
            with _jobs_lock:
                self._send_json({k: {"status": v["status"], "progress": v.get("progress", 0)} for k, v in _jobs.items()})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/start":
            self._handle_start()
        elif route == "/api/cancel/":
            self._handle_cancel(urllib.parse.unquote(parsed.path[len("/api/cancel/"):]))
        else:
            self.send_error(404)

    def _handle_probe(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            self._send_json({"error": "Arquivo nao encontrado"}, 404)
            return
        ffmpeg = default_ffmpeg_path()
        try:
            duration = parse_duration(ffmpeg, p)
            streams = count_audio_streams(ffmpeg, p)
            size = p.stat().st_size
            self._send_json({
                "path": str(p),
                "name": p.name,
                "duration": duration,
                "duration_formatted": _format_duration(duration),
                "size": size,
                "size_formatted": _format_bytes(size),
                "audio_streams": streams,
            })
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _handle_start(self) -> None:
        body = json.loads(self._read_body())
        input_paths = [Path(p) for p in body.get("inputs", [])]
        output = body.get("output", "")
        if not input_paths or not output:
            self._send_json({"error": "Entrada e saida sao obrigatorias"}, 400)
            return

        ffmpeg_path = body.get("ffmpeg") or default_ffmpeg_path()
        options = {
            "threshold_db": float(body.get("threshold_db", -35)),
            "min_silence": float(body.get("min_silence", 0.45)),
            "padding": float(body.get("padding", 0.12)),
            "min_keep": float(body.get("min_keep", 0.18)),
            "detection_mode": body.get("detection_mode", "speech"),
            "mode": body.get("mode", "reencode"),
            "ignore_ranges": body.get("ignore_ranges", ""),
            "video_use_transcript": body.get("video_use_transcript", ""),
        }

        job_id = _new_job_id()
        log_lines: list[str] = []
        cancel_event = threading.Event()

        def log_fn(text: str) -> None:
            log_lines.append(text)

        def worker() -> None:
            with _jobs_lock:
                _jobs[job_id] = {"status": "running", "progress": 0, "log": log_lines, "cancel": cancel_event}
            try:
                template = CutterOptions(
                    input_path=input_paths[0],
                    output_path=Path(output),
                    ffmpeg_path=ffmpeg_path,
                    **options,
                )
                if len(input_paths) == 1:
                    cut_video(template, log=log_fn)
                else:
                    jobs = build_batch_jobs(input_paths, Path(output), template)
                    cut_video_batch(jobs, log=log_fn)
                with _jobs_lock:
                    _jobs[job_id]["status"] = "done"
                    _jobs[job_id]["progress"] = 100
            except Exception as exc:
                log_fn(f"ERRO: {exc}")
                with _jobs_lock:
                    _jobs[job_id]["status"] = "error"
                    _jobs[job_id]["error"] = str(exc)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        with _jobs_lock:
            _jobs[job_id] = {"status": "starting", "progress": 0, "log": log_lines, "cancel": cancel_event}

        self._send_json({"job_id": job_id})

    def _handle_job_status(self, job_id: str) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
        if not job:
            self._send_json({"error": "Job nao encontrado"}, 404)
            return
        self._send_json({
            "status": job["status"],
            "progress": job.get("progress", 0),
            "log": job.get("log", []),
            "error": job.get("error", ""),
        })

    def _handle_cancel(self, job_id: str) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
        if not job:
            self._send_json({"error": "Job nao encontrado"}, 404)
            return
        job["cancel"].set()
        self._send_json({"ok": True})


def start_web_server(open_browser: bool = True) -> ThreadingHTTPServer:
    (APP_DIR / "encut_static").mkdir(exist_ok=True)
    server = ThreadingHTTPServer((WEB_HOST, WEB_PORT), EncutHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    print(f"Encut web server running at {url}")
    if open_browser:
        webbrowser.open(url)
    return server


if __name__ == "__main__":
    server = start_web_server()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
