import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

def main():
    base_dir = Path(__file__).resolve().parent
    script_path = base_dir / "silence_cutter.py"
    pythonw = base_dir / "runtime" / "python" / "pythonw.exe"

    if not script_path.exists():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Encut", f"Arquivo nao encontrado: {script_path}")
        root.destroy()
        return

    executable = str(pythonw) if pythonw.exists() else sys.executable
    cmd = [executable, str(script_path), "--gui"]

    env = os.environ.copy()
    ffmpeg_bin = base_dir / "runtime" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")

    try:
        subprocess.Popen(
            cmd,
            cwd=str(base_dir),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Encut", f"Erro ao iniciar: {exc}")
        root.destroy()

if __name__ == "__main__":
    main()
