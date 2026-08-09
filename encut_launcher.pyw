import os
import subprocess
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent
script_path = base_dir / "silence_cutter.py"
pythonw = base_dir / "runtime" / "python" / "pythonw.exe"

env = os.environ.copy()
ffmpeg_bin = base_dir / "runtime" / "ffmpeg" / "bin"
if ffmpeg_bin.exists():
    env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")

cmd = [str(pythonw), str(script_path), "--gui"] if pythonw.exists() else [sys.executable, str(script_path), "--gui"]
subprocess.Popen(cmd, cwd=str(base_dir), env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
