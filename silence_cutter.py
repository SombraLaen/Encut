import argparse
import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover - CLI still works without Tk.
    tk = None
    filedialog = None
    messagebox = None
    simpledialog = None
    ttk = None


SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")
TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
DEFAULT_APP_VERSION = "1.1.7"
PRESETS_FILENAME = "presets_ajustes.json"
UPDATE_CONFIG_FILENAME = "update_config.json"
DEFAULT_UPDATE_ENDPOINT_URL = "https://key-flow-core.base44.app/functions/update"
DEFAULT_DOWNLOAD_URL = "http://key-flow-core.base44.com/functions/downloadLatest"
VERSION_TRACKED_FILES = (
    "silence_cutter.py",
    "README.md",
    "iniciar.bat",
    "instalar.bat",
    "desinstalar.bat",
    "instalar.ps1",
    "desinstalar.ps1",
    "launcher/Iniciar.cs",
    "launcher/Iniciar.csproj",
    "installer/EncutSetup.csproj",
    "installer/Program.cs",
)


def ensure_app_version() -> str:
    base_dir = Path(__file__).resolve().parent
    version_path = base_dir / "VERSION"
    state_path = base_dir / ".version_state.json"
    changelog_path = base_dir / "CHANGELOG.md"
    version = _read_version(version_path)
    current_files = _tracked_file_snapshot(base_dir)
    state = _read_version_state(state_path)

    if state:
        changed_files = _changed_tracked_files(state.get("files", {}), current_files)
        if changed_files:
            previous_version = version
            version = _bump_patch_version(version)
            _write_version(version_path, version)
            _append_changelog(changelog_path, version, previous_version, changed_files)
    else:
        _write_version(version_path, version)
        if not changelog_path.exists():
            _append_changelog(changelog_path, version, None, ["controle de versao iniciado"])

    _write_version_state(state_path, version, current_files)
    return version


def _read_version(version_path: Path) -> str:
    if version_path.exists():
        value = version_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return DEFAULT_APP_VERSION


def _write_version(version_path: Path, version: str) -> None:
    version_path.write_text(version + "\n", encoding="utf-8")


def _read_version_state(state_path: Path) -> dict[str, object]:
    if not state_path.exists():
        return {}
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_version_state(state_path: Path, version: str, files: dict[str, dict[str, object]]) -> None:
    state = {
        "version": version,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _tracked_file_snapshot(base_dir: Path) -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for relative_path in VERSION_TRACKED_FILES:
        path = base_dir / relative_path
        if not path.exists() or not path.is_file():
            continue
        data = path.read_bytes()
        stat = path.stat()
        snapshot[relative_path] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    return snapshot


def _changed_tracked_files(
    previous_files: object,
    current_files: dict[str, dict[str, object]],
) -> list[str]:
    if not isinstance(previous_files, dict):
        return []
    changed = []
    for relative_path, current in current_files.items():
        previous = previous_files.get(relative_path)
        if not isinstance(previous, dict) or previous.get("sha256") != current.get("sha256"):
            changed.append(relative_path)
    for relative_path in previous_files:
        if relative_path not in current_files:
            changed.append(f"{relative_path} removido")
    return changed


def _bump_patch_version(version: str) -> str:
    parts = version.split(".")
    numbers = []
    for part in parts[:3]:
        try:
            numbers.append(int(part))
        except ValueError:
            numbers.append(0)
    while len(numbers) < 3:
        numbers.append(0)
    numbers[2] += 1
    return ".".join(str(number) for number in numbers)


def _append_changelog(
    changelog_path: Path,
    version: str,
    previous_version: Optional[str],
    changed_files: list[str],
) -> None:
    heading = "# Log de alteracoes\n\n"
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
    else:
        existing = heading
    if not existing.startswith("# Log de alteracoes"):
        existing = heading + existing

    date_text = datetime.now().isoformat(timespec="seconds")
    previous_text = f" de {previous_version}" if previous_version else ""
    lines = [
        f"## v{version} - {date_text}",
        f"- Versao atualizada automaticamente{previous_text} para {version}.",
        "- Mudancas detectadas:",
    ]
    lines.extend(f"  - {changed_file}" for changed_file in changed_files)
    lines.append("")
    lines.append("")
    changelog_path.write_text(existing.rstrip() + "\n\n" + "\n".join(lines), encoding="utf-8")


APP_VERSION = ensure_app_version()

HELP_TEXTS = {
    "videos": (
        "Escolhe um ou varios videos de entrada. Cada video sera analisado, tera os silencios removidos "
        "e sera exportado separadamente. Em lote, a ferramenta cria um arquivo final para cada entrada."
    ),
    "output": (
        "Define onde salvar o resultado. Com um unico video, e o arquivo final .mp4. Com varios videos, "
        "e uma pasta de saida; cada resultado recebe o sufixo _sem_silencio. Se um arquivo final ja existir, "
        "a versao anterior vai para backups antes de gerar a nova."
    ),
    "ffmpeg": (
        "Aponta para o ffmpeg.exe usado para detectar silencio, cortar trechos, mesclar faixas de audio "
        "e exportar o video final. Se o ffmpeg estiver no PATH, este campo pode ficar vazio."
    ),
    "video_use_transcript": (
        "Opcional. Usa um JSON de transcricao do browser-use/video-use ou ElevenLabs Scribe com timestamps "
        "por palavra. No modo Video Use, o Encut monta os trechos de fala por limite de palavra e gera "
        "takes_packed.md e EDL compativeis no relatorio. Em lote, informe uma pasta com um JSON por video."
    ),
    "ignore_ranges": (
        "Protege intervalos do video contra cortes internos. Use formatos como 01:30-03:00, "
        "01:30 ate 03:00 ou varios separados por ponto e virgula. Esses trechos ficam inteiros no resultado "
        "mesmo que o detector encontre silencio neles."
    ),
    "threshold": (
        "Volume abaixo do qual o audio e considerado silencio. Valores mais altos, como -25 dB, cortam "
        "pausas mais facilmente. Valores mais baixos, como -45 dB, sao mais conservadores e preservam "
        "ruidos baixos ou respiracoes."
    ),
    "min_silence": (
        "Tempo minimo, em segundos, que o audio precisa ficar abaixo do limite para virar um corte. "
        "Valores pequenos removem pausas curtas; valores maiores removem apenas pausas longas."
    ),
    "padding": (
        "Margem preservada antes e depois de cada fala. Aumente se os cortes ficarem secos demais ou "
        "comerem o comeco/fim das palavras. Diminua para deixar o video mais enxuto."
    ),
    "min_keep": (
        "Menor trecho com som que ainda sera mantido. Isso evita criar fragmentos muito curtos entre "
        "silencios. Aumentar limpa micro-ruidos; diminuir preserva sons muito breves."
    ),
    "mode": (
        "Controla como o video final e exportado. O modo preciso recodifica para cortar exatamente. "
        "O modo rapido tenta copiar o video para acelerar, mas pode cortar perto dos keyframes."
    ),
    "detection": (
        "Controla como a ferramenta decide o que deve ficar. O modo fala procura trechos com voz humana "
        "em blocos pequenos. O modo silencio usa a deteccao tradicional de pausas abaixo do limite de dB."
    ),
    "detection_speech": (
        "Analisa o audio em janelas curtas depois de filtrar a faixa mais importante da voz. Usa histerese "
        "para achar comeco e fim de fala com mais precisao, preservando pausas curtas dentro da mesma frase."
    ),
    "detection_silence": (
        "Usa o filtro silencedetect do ffmpeg. E mais simples e pode ser util em audio limpo, mas tende a "
        "confundir ruido de fundo, musica baixa ou respiracoes com fala."
    ),
    "detection_video_use": (
        "Usa um transcript JSON compativel com browser-use/video-use ou ElevenLabs Scribe. Os cortes sao "
        "montados a partir dos timestamps de palavras, evitando cortar no meio de falas. O JSON pode ser "
        "selecionado manualmente ou ficar em edit/transcripts com o mesmo nome do video."
    ),
    "mode_reencode": (
        "Recodifica video e audio. E mais lento, mas faz cortes mais precisos e consistentes, indicado "
        "quando a qualidade dos pontos de corte importa."
    ),
    "mode_copy": (
        "Copia o video quando possivel, acelerando a exportacao. Os cortes podem cair perto dos keyframes. "
        "Se houver varias faixas de audio, o audio ainda sera recodificado para mesclar as faixas."
    ),
    "presets": (
        "Guarda combinacoes dos ajustes de corte: limite em dB, silencio minimo, margem, trecho minimo "
        "modo de deteccao e modo de exportacao. Presets nao salvam caminhos de videos, pasta de saida nem ffmpeg."
    ),
    "preset_load": (
        "Aplica o preset selecionado nos campos de ajustes. Isso troca os valores da tela, mas nao inicia "
        "o processamento automaticamente."
    ),
    "preset_save": (
        "Salva os ajustes atuais com um nome. Se o nome ja existir, o preset sera atualizado com os "
        "valores que estao na tela."
    ),
    "preset_delete": (
        "Remove o preset selecionado do arquivo de presets. Isso nao altera videos, backups, relatorios "
        "nem os ajustes que ja estao preenchidos na tela."
    ),
    "start": (
        "Inicia o processamento com os videos e ajustes atuais. Durante o processo, o log mostra progresso, "
        "estimativa, backups criados, relatorios gerados e erros, se acontecerem."
    ),
    "clear_log": (
        "Limpa apenas o texto visivel do log na tela. Nao remove videos, backups, relatorios nem historico "
        "de versoes salvo em disco."
    ),
}


@dataclass
class CutterOptions:
    input_path: Path
    output_path: Path
    ffmpeg_path: str = "ffmpeg"
    threshold_db: float = -35.0
    min_silence: float = 0.45
    padding: float = 0.12
    min_keep: float = 0.18
    detection_mode: str = "speech"
    ignore_ranges: str = ""
    video_use_transcript: str = ""
    mode: str = "reencode"


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class VideoUseTranscriptData:
    path: Path
    words: list[dict[str, object]]
    phrases: list[dict[str, object]]


@dataclass
class UpdateInfo:
    version: str
    zip_url: str = ""
    setup_url: str = ""
    sha256: str = ""
    notes: str = ""
def log_noop(_: str) -> None:
    return None


def clone_options(options: CutterOptions, input_path: Path, output_path: Path) -> CutterOptions:
    return CutterOptions(
        input_path=input_path,
        output_path=output_path,
        ffmpeg_path=options.ffmpeg_path,
        threshold_db=options.threshold_db,
        min_silence=options.min_silence,
        padding=options.padding,
        min_keep=options.min_keep,
        detection_mode=options.detection_mode,
        ignore_ranges=options.ignore_ranges,
        video_use_transcript=options.video_use_transcript,
        mode=options.mode,
    )


def _hidden_subprocess_options() -> dict[str, object]:
    if os.name != "nt":
        return {}

    options: dict[str, object] = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        options["startupinfo"] = startupinfo
    return options


def _run_process(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, **kwargs, **_hidden_subprocess_options())


def _popen_process(cmd: list[str], **kwargs: object) -> subprocess.Popen[str]:
    return subprocess.Popen(cmd, **kwargs, **_hidden_subprocess_options())



def app_base_dir() -> Path:
    return Path(__file__).resolve().parent


def default_ffmpeg_path() -> str:
    local = app_base_dir() / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"



def update_config_path() -> Path:
    return app_base_dir() / UPDATE_CONFIG_FILENAME


def default_update_config() -> dict[str, object]:
    return {
        "enabled": True,
        "check_on_startup": True,
        "manifest_url": DEFAULT_UPDATE_ENDPOINT_URL,
    }


def load_update_config(path: Optional[Path] = None) -> dict[str, object]:
    path = path or update_config_path()
    config = default_update_config()
    if not path.exists():
        return config
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if not isinstance(data, dict):
        return config
    config.update({key: data[key] for key in config if key in data})
    return config


def _version_key(value: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", str(value))[:4]]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def is_newer_version(remote_version: str, local_version: str = APP_VERSION) -> bool:
    return _version_key(remote_version) > _version_key(local_version)


def _fetch_update_payload(update_url: str, timeout: int) -> object:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"Encut/{APP_VERSION}",
    }
    attempts: list[tuple[str, Optional[bytes]]] = [("GET", None), ("POST", b"{}")]
    last_error: Optional[Exception] = None

    for method, body in attempts:
        request_headers = dict(headers)
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(update_url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(4 * 1024 * 1024)
            break
        except urllib.error.URLError as exc:
            last_error = exc
    else:
        raise RuntimeError(f"Nao foi possivel consultar atualizacao: {last_error}")

    text = raw.decode("utf-8-sig", errors="replace").strip()
    if text.startswith("<"):
        raise RuntimeError("Endpoint de atualizacao retornou HTML em vez de JSON publico.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Resposta de atualizacao invalida. O endpoint precisa retornar JSON.") from exc

    if isinstance(payload, str):
        nested = payload.strip()
        if nested.startswith(("{", "[")):
            try:
                return json.loads(nested)
            except json.JSONDecodeError:
                pass
    return payload


def _candidate_value(data: dict[str, object], names: tuple[str, ...]) -> str:
    lowered = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is None or isinstance(value, (dict, list)):
            continue
        return str(value).strip()
    return ""


def _normalize_download_url(download_url: str) -> str:
    if not download_url:
        return ""
    if "api.base44.com/api/apps/6a0a893b79eb8fdc64346940/functions/downloadLatest" in download_url:
        return DEFAULT_DOWNLOAD_URL
    return download_url

def _update_from_dict(data: dict[str, object], base_url: str) -> Optional[UpdateInfo]:
    version = _candidate_value(data, ("version", "app_version", "appVersion", "latest_version", "latestVersion", "versao"))
    zip_url = _candidate_value(data, ("zip_url", "zipUrl", "package_url", "packageUrl", "package", "zip", "arquivo_zip"))
    setup_url = _candidate_value(data, ("setup_url", "setupUrl", "installer_url", "installerUrl", "setup", "installer", "setup_exe"))
    download_url = _candidate_value(data, ("download_url", "downloadUrl", "file_url", "fileUrl", "url", "href", "download", "link"))

    if not zip_url and not setup_url:
        download_url = _normalize_download_url(download_url)
        if not download_url:
            download_url = DEFAULT_DOWNLOAD_URL
        if download_url.lower().endswith(".exe"):
            setup_url = download_url
        else:
            zip_url = download_url

    if not version or (not zip_url and not setup_url):
        return None

    if zip_url:
        zip_url = urllib.parse.urljoin(base_url, zip_url)
    if setup_url:
        setup_url = urllib.parse.urljoin(base_url, setup_url)

    return UpdateInfo(
        version=version,
        zip_url=zip_url,
        setup_url=setup_url,
        sha256=_candidate_value(data, ("sha256", "sha_256", "hash", "checksum")).lower(),
        notes=_candidate_value(data, ("notes", "changelog", "description", "descricao")),
    )


def _collect_update_candidates(payload: object, base_url: str) -> list[UpdateInfo]:
    candidates: list[UpdateInfo] = []
    if isinstance(payload, dict):
        update = _update_from_dict(payload, base_url)
        if update is not None:
            candidates.append(update)
        for value in payload.values():
            candidates.extend(_collect_update_candidates(value, base_url))
    elif isinstance(payload, list):
        for value in payload:
            candidates.extend(_collect_update_candidates(value, base_url))
    elif isinstance(payload, str):
        nested = payload.strip()
        if nested.startswith(("{", "[")):
            try:
                candidates.extend(_collect_update_candidates(json.loads(nested), base_url))
            except json.JSONDecodeError:
                pass
    return candidates


def check_for_update(manifest_url: str, timeout: int = 20) -> Optional[UpdateInfo]:
    manifest_url = manifest_url.strip()
    if not manifest_url:
        raise RuntimeError("URL do manifesto de atualizacao nao configurada.")

    payload = _fetch_update_payload(manifest_url, timeout)
    candidates = [candidate for candidate in _collect_update_candidates(payload, manifest_url) if is_newer_version(candidate.version)]
    if not candidates:
        return None

    candidates.sort(key=lambda candidate: _version_key(candidate.version), reverse=True)
    return candidates[0]

def install_update(update: UpdateInfo, log: Callable[[str], None] = log_noop) -> None:
    with tempfile.TemporaryDirectory(prefix="encut-update-") as temp_dir:
        temp_path = Path(temp_dir)
        if update.setup_url:
            download_path = temp_path / "EncutSetup.exe"
            log(f"Baixando instalador v{update.version}...")
            _download_update_file(update.setup_url, download_path)
            setup_path = download_path
        else:
            download_path = temp_path / f"Encut_{update.version}.zip"
            log(f"Baixando pacote v{update.version}...")
            _download_update_file(update.zip_url, download_path)
            setup_path = _extract_setup_from_update_zip(download_path, temp_path)

        if update.sha256:
            actual_hash = _sha256_file(download_path)
            if actual_hash.lower() != update.sha256.lower():
                raise RuntimeError("Hash SHA256 do pacote de atualizacao nao confere.")

        log("Executando instalador da atualizacao...")
        proc = _run_process(
            [str(setup_path), "/silent"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError("Instalador da atualizacao falhou." + (f"\n{detail}" if detail else ""))


def _download_update_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"Encut/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _extract_setup_from_update_zip(zip_path: Path, target_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        candidates = [name for name in archive.namelist() if Path(name).name.lower() == "encutsetup.exe"]
        if not candidates:
            raise RuntimeError("Pacote de atualizacao nao contem EncutSetup.exe.")
        setup_name = candidates[0]
        setup_path = target_dir / "EncutSetup.exe"
        with archive.open(setup_name) as source, setup_path.open("wb") as output:
            shutil.copyfileobj(source, output)
    return setup_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
def require_ffmpeg(ffmpeg_path: str) -> None:
    try:
        _run_process(
            [ffmpeg_path, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "ffmpeg nao encontrado. Rode o instalador para baixar as dependencias ou informe o caminho do ffmpeg.exe."
        ) from exc


def parse_duration(ffmpeg_path: str, input_path: Path) -> float:
    ffprobe_path = _guess_ffprobe_path(ffmpeg_path)
    if ffprobe_path:
        cmd = [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        proc = _run_process(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            return float((proc.stdout or "").strip())
        except ValueError:
            pass

    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-i",
        str(input_path),
    ]
    proc = _run_process(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    text = proc.stderr or ""
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def count_audio_streams(ffmpeg_path: str, input_path: Path) -> int:
    ffprobe_path = _guess_ffprobe_path(ffmpeg_path)
    if ffprobe_path:
        cmd = [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(input_path),
        ]
        proc = _run_process(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if proc.returncode == 0:
            return len([line for line in (proc.stdout or "").splitlines() if line.strip()])

    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-i",
        str(input_path),
    ]
    proc = _run_process(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return sum(1 for line in (proc.stderr or "").splitlines() if "Stream #" in line and "Audio:" in line)


def _guess_ffprobe_path(ffmpeg_path: str) -> Optional[str]:
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name.lower() in {"ffmpeg.exe", "ffmpeg"} and ffmpeg.parent != Path("."):
        candidate = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def detect_silences(
    options: CutterOptions,
    audio_stream_count: int,
    duration: float,
    log: Callable[[str], None] = log_noop,
) -> tuple[list[Segment], float]:
    log("Analisando audio para encontrar silencios...")
    cmd = [
        options.ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(options.input_path),
    ]
    if audio_stream_count > 1:
        cmd += [
            "-filter_complex",
            _audio_mix_filter(
                audio_stream_count,
                output_label="detectaudio",
                tail_filter=f"silencedetect=noise={options.threshold_db}dB:d={options.min_silence}",
            ),
            "-map",
            "[detectaudio]",
        ]
    else:
        cmd += [
            "-af",
            f"silencedetect=noise={options.threshold_db}dB:d={options.min_silence}",
        ]
    cmd += ["-f", "null", "-"]
    proc = _popen_process(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        universal_newlines=True,
    )

    silences: list[Segment] = []
    current_start: Optional[float] = None
    started_at = time.monotonic()
    last_progress_log = 0.0
    assert proc.stderr is not None
    for line in proc.stderr:
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = SILENCE_END_RE.search(line)
        if end_match and current_start is not None:
            silences.append(Segment(current_start, float(end_match.group(1))))
            current_start = None

        time_match = TIME_RE.search(line)
        if duration and time_match:
            seen = _time_match_to_seconds(time_match)
            percent = min(100.0, seen / duration * 100)
            now = time.monotonic()
            if now - last_progress_log >= 2 or percent >= 100:
                elapsed = now - started_at
                log(_progress_line("Analisando", percent, elapsed))
                last_progress_log = now

    code = proc.wait()
    if code != 0:
        raise RuntimeError("O ffmpeg falhou durante a deteccao de silencio.")

    if current_start is not None and duration:
        silences.append(Segment(current_start, duration))

    if not duration:
        last_silence = silences[-1].end if silences else 0.0
        duration = last_silence

    return silences, duration


def _time_match_to_seconds(match: re.Match[str]) -> float:
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _audio_mix_filter(audio_stream_count: int, output_label: str, tail_filter: Optional[str] = None) -> str:
    inputs = "".join(f"[0:a:{index}]" for index in range(audio_stream_count))
    filters = [
        f"{inputs}amix=inputs={audio_stream_count}:duration=longest:normalize=0",
        "alimiter=limit=0.95",
    ]
    if tail_filter:
        filters.append(tail_filter)
    return ",".join(filters) + f"[{output_label}]"


def detect_speech_segments(
    options: CutterOptions,
    audio_stream_count: int,
    duration: float,
    log: Callable[[str], None] = log_noop,
) -> tuple[list[Segment], float]:
    log("Analisando fala com detector de voz...")
    sample_rate = 16000
    frame_ms = 20
    frame_bytes = int(sample_rate * frame_ms / 1000) * 2
    start_threshold = options.threshold_db
    end_threshold = options.threshold_db - 6.0

    cmd = [
        options.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(options.input_path),
    ]
    speech_filter = _speech_filter_chain(sample_rate)
    if audio_stream_count > 1:
        cmd += [
            "-filter_complex",
            _audio_mix_filter(audio_stream_count, output_label="speechaudio", tail_filter=speech_filter),
            "-map",
            "[speechaudio]",
        ]
    else:
        cmd += ["-map", "0:a:0?", "-af", speech_filter]
    cmd += ["-vn", "-f", "s16le", "-"]

    proc = _popen_process(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert proc.stdout is not None
    segments: list[Segment] = []
    current_start: Optional[float] = None
    last_voice_end: Optional[float] = None
    processed_frames = 0
    buffer = b""
    started_at = time.monotonic()
    last_progress_log = 0.0

    while True:
        chunk = proc.stdout.read(frame_bytes * 100)
        if not chunk:
            break
        buffer += chunk
        usable = len(buffer) // frame_bytes * frame_bytes
        frames_data = buffer[:usable]
        buffer = buffer[usable:]

        for offset in range(0, len(frames_data), frame_bytes):
            frame = frames_data[offset : offset + frame_bytes]
            frame_start = processed_frames * frame_ms / 1000
            frame_end = frame_start + frame_ms / 1000
            processed_frames += 1

            db = _pcm16le_rms_db(frame)
            threshold = end_threshold if current_start is not None else start_threshold
            has_voice = db >= threshold
            if has_voice:
                if current_start is None:
                    current_start = frame_start
                last_voice_end = frame_end
            elif current_start is not None and last_voice_end is not None:
                if frame_end - last_voice_end >= options.min_silence:
                    _append_speech_segment(segments, current_start, last_voice_end, options.min_keep)
                    current_start = None
                    last_voice_end = None

            if duration:
                now = time.monotonic()
                if now - last_progress_log >= 2:
                    percent = min(100.0, frame_end / duration * 100)
                    log(_progress_line("Analisando fala", percent, now - started_at))
                    last_progress_log = now

    code = proc.wait()
    stderr = b""
    if proc.stderr is not None:
        stderr = proc.stderr.read() or b""
    if code != 0:
        tail = stderr.decode("utf-8", errors="replace").splitlines()[-8:]
        detail = "\n".join(tail).strip()
        raise RuntimeError("O ffmpeg falhou durante a deteccao de fala." + (f"\n{detail}" if detail else ""))

    detected_duration = processed_frames * frame_ms / 1000
    if current_start is not None and last_voice_end is not None:
        _append_speech_segment(segments, current_start, last_voice_end, options.min_keep)

    if not duration:
        duration = detected_duration
    if duration:
        log(_progress_line("Analisando fala", 100.0, time.monotonic() - started_at))

    return _merge_close_segments(segments, gap=0.03), duration


def detect_video_use_segments(
    options: CutterOptions,
    duration: float,
    log: Callable[[str], None] = log_noop,
) -> tuple[list[Segment], float, dict[str, object]]:
    transcript_path = resolve_video_use_transcript_path(options)
    transcript = load_video_use_transcript(transcript_path)
    spoken_words = [word for word in transcript.words if _is_spoken_transcript_word(word)]
    if not spoken_words:
        raise RuntimeError("A transcricao Video Use nao contem palavras com timestamps validos.")

    if not duration:
        duration = max(_word_end(word) for word in spoken_words)

    gap = max(0.05, float(options.min_silence))
    segments = _speech_segments_from_transcript_words(spoken_words, duration, gap, options.min_keep)
    if not segments:
        raise RuntimeError("Nenhum trecho de fala foi encontrado no transcript Video Use.")

    log(f"Transcricao Video Use: {transcript.path}")
    log(f"Palavras analisadas: {len(spoken_words)} | frases agrupadas: {len(transcript.phrases)}")
    info: dict[str, object] = {
        "enabled": True,
        "source": "browser-use/video-use transcript",
        "transcript_path": str(transcript.path),
        "word_count": len(spoken_words),
        "phrase_count": len(transcript.phrases),
        "gap_seconds": gap,
        "_words": transcript.words,
        "_phrases": transcript.phrases,
    }
    return _merge_close_segments(segments, gap=0.03), duration, info


def resolve_video_use_transcript_path(options: CutterOptions) -> Path:
    explicit = (options.video_use_transcript or "").strip()
    candidates = _video_use_transcript_candidates(options.input_path, explicit)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    if explicit:
        checked = ", ".join(str(candidate) for candidate in candidates)
        raise RuntimeError(f"Transcript Video Use nao encontrado. Caminhos verificados: {checked}")

    auto = options.input_path.parent / "edit" / "transcripts" / f"{options.input_path.stem}.json"
    raise RuntimeError(
        "Modo Video Use selecionado, mas nenhum transcript JSON foi encontrado. "
        f"Informe o JSON na interface ou salve em {auto}."
    )


def _video_use_transcript_candidates(input_path: Path, configured: str) -> list[Path]:
    stem = input_path.stem
    if configured:
        base = Path(configured).expanduser()
        if not base.is_absolute():
            base = base.resolve()
        if base.suffix.lower() == ".json":
            return [base]
        return [
            base / f"{stem}.json",
            base / "transcripts" / f"{stem}.json",
            base / "edit" / "transcripts" / f"{stem}.json",
        ]

    return [
        input_path.parent / "edit" / "transcripts" / f"{stem}.json",
        input_path.parent / "transcripts" / f"{stem}.json",
        app_base_dir() / "relatorios" / "transcricoes" / f"{stem}.json",
    ]


def load_video_use_transcript(path: Path) -> VideoUseTranscriptData:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Transcript Video Use invalido: {path}") from exc

    words = _find_video_use_words(data)
    if not words:
        raise RuntimeError("O JSON informado nao parece conter palavras com start/end/text.")
    words.sort(key=lambda word: (_word_start(word), _word_end(word)))
    phrases = _group_video_use_phrases(words, silence_threshold=0.5)
    return VideoUseTranscriptData(path=path.resolve(), words=words, phrases=phrases)


def _find_video_use_words(data: object) -> list[dict[str, object]]:
    best: list[dict[str, object]] = []

    def walk(node: object) -> None:
        nonlocal best
        if isinstance(node, list):
            candidate = []
            for item in node:
                if isinstance(item, dict):
                    normalized = _normalize_transcript_word(item)
                    if normalized is not None:
                        candidate.append(normalized)
            if len(candidate) > len(best):
                best = candidate
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(data)
    return best


def _normalize_transcript_word(entry: dict[str, object]) -> Optional[dict[str, object]]:
    start = _coerce_float(_first_value(entry, ("start", "start_time", "startTime", "from")))
    end = _coerce_float(_first_value(entry, ("end", "end_time", "endTime", "to")))
    if start is None or end is None or end < start:
        return None

    kind = str(_first_value(entry, ("type", "kind")) or "word").strip().lower() or "word"
    text = str(_first_value(entry, ("text", "word", "content", "value")) or "").strip()
    if kind != "spacing" and not text:
        return None

    speaker = _first_value(entry, ("speaker_id", "speaker", "speakerId"))
    return {
        "start": float(start),
        "end": float(end),
        "text": text,
        "type": kind,
        "speaker_id": speaker,
    }


def _first_value(entry: dict[str, object], names: tuple[str, ...]) -> object:
    lowered = {str(key).lower(): value for key, value in entry.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def _coerce_float(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _is_spoken_transcript_word(word: dict[str, object]) -> bool:
    if str(word.get("type", "word")).lower() == "spacing":
        return False
    return _word_end(word) > _word_start(word) and bool(str(word.get("text", "")).strip())


def _word_start(word: dict[str, object]) -> float:
    value = word.get("start", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _word_end(word: dict[str, object]) -> float:
    value = word.get("end", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _speech_segments_from_transcript_words(
    words: list[dict[str, object]],
    duration: float,
    gap: float,
    min_keep: float,
) -> list[Segment]:
    segments: list[Segment] = []
    current_start: Optional[float] = None
    current_end: Optional[float] = None

    for word in words:
        start = max(0.0, min(duration, _word_start(word))) if duration else max(0.0, _word_start(word))
        end = max(start, min(duration, _word_end(word))) if duration else max(start, _word_end(word))
        if current_start is None or current_end is None:
            current_start = start
            current_end = end
            continue
        if start - current_end >= gap:
            _append_speech_segment(segments, current_start, current_end, min_keep)
            current_start = start
        current_end = max(current_end, end)

    if current_start is not None and current_end is not None:
        _append_speech_segment(segments, current_start, current_end, min_keep)
    return segments


def _group_video_use_phrases(words: list[dict[str, object]], silence_threshold: float) -> list[dict[str, object]]:
    phrases: list[dict[str, object]] = []
    current: list[dict[str, object]] = []
    current_speaker: object = None
    previous_end: Optional[float] = None

    def flush() -> None:
        nonlocal current, current_speaker
        spoken = [word for word in current if _is_spoken_transcript_word(word)]
        if not spoken:
            current = []
            current_speaker = None
            return
        text = _clean_transcript_text(" ".join(str(word.get("text", "")).strip() for word in spoken))
        phrases.append(
            {
                "start": _word_start(spoken[0]),
                "end": _word_end(spoken[-1]),
                "speaker_id": current_speaker,
                "text": text,
            }
        )
        current = []
        current_speaker = None

    for word in words:
        if not _is_spoken_transcript_word(word):
            continue
        start = _word_start(word)
        speaker = word.get("speaker_id")
        speaker_changed = current_speaker is not None and speaker is not None and speaker != current_speaker
        long_gap = previous_end is not None and start - previous_end >= silence_threshold
        if current and (speaker_changed or long_gap):
            flush()
        if not current:
            current_speaker = speaker
        current.append(word)
        previous_end = _word_end(word)

    flush()
    return phrases


def _clean_transcript_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        " ,": ",",
        " .": ".",
        " ?": "?",
        " !": "!",
        " ;": ";",
        " :": ":",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _attach_video_use_artifacts(
    info: dict[str, object],
    options: CutterOptions,
    keep_segments: list[Segment],
    duration: float,
) -> None:
    words = info.pop("_words", [])
    phrases = info.pop("_phrases", [])
    if isinstance(phrases, list) and phrases:
        info["_takes_packed_content"] = _render_video_use_packed_transcript(
            options.input_path.stem,
            duration,
            phrases,
            silence_threshold=0.5,
        )
    if isinstance(words, list):
        info["_edl_json"] = _build_video_use_edl(options, keep_segments, words)


def _render_video_use_packed_transcript(
    source_name: str,
    duration: float,
    phrases: list[dict[str, object]],
    silence_threshold: float,
) -> str:
    lines = [
        "# Packed transcripts",
        "",
        f"Phrase-level, grouped on silences >= {silence_threshold:.1f}s or speaker change.",
        "Use [start-end] ranges to review cuts or build an EDL.",
        "",
        f"## {source_name}  (duration: {_format_duration(duration)}, {len(phrases)} phrases)",
    ]
    for phrase in phrases:
        speaker = phrase.get("speaker_id")
        speaker_label = ""
        if speaker is not None:
            speaker_text = str(speaker)
            if speaker_text.startswith("speaker_"):
                speaker_text = speaker_text[len("speaker_"):]
            speaker_label = f" S{speaker_text}"
        lines.append(
            f"  [{float(phrase.get('start', 0.0)):06.2f}-{float(phrase.get('end', 0.0)):06.2f}]"
            f"{speaker_label} {phrase.get('text', '')}"
        )
    lines.append("")
    return "\n".join(lines)


def _build_video_use_edl(
    options: CutterOptions,
    keep_segments: list[Segment],
    words: list[dict[str, object]],
) -> dict[str, object]:
    source_name = _safe_filename(options.input_path.stem)
    ranges = []
    output_cursor = 0.0
    for index, segment in enumerate(keep_segments, start=1):
        entry = {
            "source": source_name,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "start_in_output": round(output_cursor, 3),
            "duration": round(segment.duration, 3),
            "beat": f"encut_keep_{index:03d}",
            "reason": "Mantido pelo Encut a partir da transcricao Video Use.",
        }
        quote = _quote_for_video_use_segment(words, segment.start, segment.end)
        if quote:
            entry["quote"] = quote
        ranges.append(entry)
        output_cursor += segment.duration

    return {
        "schema": "video-use-edl",
        "schema_version": 1,
        "generated_by": f"Encut v{APP_VERSION}",
        "generated_at": _now_iso(),
        "sources": {source_name: str(options.input_path)},
        "ranges": ranges,
        "total_duration": round(output_cursor, 3),
        "grade": "none",
        "overlays": [],
    }


def _quote_for_video_use_segment(words: list[dict[str, object]], start: float, end: float, max_chars: int = 180) -> str:
    parts = []
    for word in words:
        if not _is_spoken_transcript_word(word):
            continue
        if _word_end(word) <= start or _word_start(word) >= end:
            continue
        parts.append(str(word.get("text", "")).strip())
    text = _clean_transcript_text(" ".join(part for part in parts if part))
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def _speech_filter_chain(sample_rate: int) -> str:
    return (
        "highpass=f=90,"
        "lowpass=f=7500,"
        f"aresample={sample_rate},"
        "aformat=sample_fmts=s16:channel_layouts=mono"
    )


def _pcm16le_rms_db(frame: bytes) -> float:
    sample_count = len(frame) // 2
    if sample_count == 0:
        return -120.0

    total = 0
    for index in range(0, sample_count * 2, 2):
        sample = int.from_bytes(frame[index : index + 2], "little", signed=True)
        total += sample * sample
    rms = math.sqrt(total / sample_count)
    if rms <= 0:
        return -120.0
    return 20 * math.log10(rms / 32768.0)


def _append_speech_segment(segments: list[Segment], start: float, end: float, min_keep: float) -> None:
    segment = Segment(max(0.0, start), max(0.0, end))
    if segment.duration >= min_keep:
        segments.append(segment)


def build_keep_segments(
    silences: Iterable[Segment],
    duration: float,
    padding: float,
    min_keep: float,
) -> list[Segment]:
    keep: list[Segment] = []
    cursor = 0.0

    for silence in silences:
        start = max(0.0, silence.start - padding)
        end = min(duration, silence.end + padding)
        if start > cursor:
            segment = Segment(cursor, start)
            if segment.duration >= min_keep:
                keep.append(segment)
        cursor = max(cursor, end)

    if duration > cursor:
        segment = Segment(cursor, duration)
        if segment.duration >= min_keep:
            keep.append(segment)

    return _merge_close_segments(keep, gap=0.03)


def build_keep_segments_from_speech(
    speech_segments: Iterable[Segment],
    duration: float,
    padding: float,
    min_keep: float,
) -> list[Segment]:
    keep = []
    for segment in speech_segments:
        expanded = Segment(max(0.0, segment.start - padding), min(duration, segment.end + padding))
        if expanded.duration >= min_keep:
            keep.append(expanded)
    return _merge_close_segments(keep, gap=0.03)


def parse_ignore_ranges(text: str, duration: float = 0.0) -> list[Segment]:
    text = (text or "").strip()
    if not text:
        return []

    tokens = re.findall(r"\d+(?::\d{1,2}){0,2}(?:[\.,]\d+)?", text)
    if not tokens:
        raise ValueError("Informe os intervalos protegidos no formato 01:30-03:00.")
    if len(tokens) % 2:
        raise ValueError("Cada intervalo protegido precisa ter inicio e fim, por exemplo 01:30-03:00.")

    ranges = []
    for index in range(0, len(tokens), 2):
        start = _parse_time_value(tokens[index])
        end = _parse_time_value(tokens[index + 1])
        if end <= start:
            raise ValueError(f"Intervalo protegido invalido: {tokens[index]}-{tokens[index + 1]}.")
        if duration > 0:
            if start >= duration:
                continue
            end = min(end, duration)
        ranges.append(Segment(max(0.0, start), end))

    return _merge_close_segments(sorted(ranges, key=lambda segment: segment.start), gap=0.001)


def _parse_time_value(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"Tempo invalido: {value}")


def apply_protected_ranges(keep_segments: list[Segment], protected_ranges: list[Segment], duration: float) -> list[Segment]:
    if not protected_ranges:
        return keep_segments

    merged = list(keep_segments)
    for segment in protected_ranges:
        start = max(0.0, segment.start)
        end = min(duration, segment.end) if duration > 0 else segment.end
        if end > start:
            merged.append(Segment(start, end))
    return _merge_close_segments(sorted(merged, key=lambda segment: segment.start), gap=0.03)


def _merge_close_segments(segments: list[Segment], gap: float) -> list[Segment]:
    if not segments:
        return []
    merged = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        if segment.start - previous.end <= gap:
            previous.end = max(previous.end, segment.end)
        else:
            merged.append(segment)
    return merged


def cut_video(options: CutterOptions, log: Callable[[str], None] = log_noop) -> dict[str, object]:
    workflow_started_at = time.monotonic()
    started_at_iso = _now_iso()
    require_ffmpeg(options.ffmpeg_path)
    options.input_path = options.input_path.expanduser().resolve()
    options.output_path = options.output_path.expanduser().resolve()

    if not options.input_path.exists():
        raise FileNotFoundError(f"Video nao encontrado: {options.input_path}")
    options.output_path.parent.mkdir(parents=True, exist_ok=True)
    if options.input_path == options.output_path:
        raise RuntimeError("O arquivo de saida nao pode ser o mesmo arquivo de entrada.")

    original_size = options.input_path.stat().st_size
    original_duration = parse_duration(options.ffmpeg_path, options.input_path)
    protected_ranges = parse_ignore_ranges(options.ignore_ranges, original_duration)
    backup_info = backup_existing_output(options.output_path, log)
    log(
        "Video original: "
        f"{_format_duration(original_duration)} | {_format_bytes(original_size)}"
    )
    if protected_ranges:
        log(f"Trechos protegidos sem corte: {len(protected_ranges)}")

    audio_stream_count = count_audio_streams(options.ffmpeg_path, options.input_path)
    if audio_stream_count == 0:
        raise RuntimeError("Nenhuma faixa de audio foi encontrada no video.")
    if audio_stream_count == 1:
        log("Faixas de audio encontradas: 1")
    else:
        log(f"Faixas de audio encontradas: {audio_stream_count}. Mesclando em uma faixa antes dos cortes.")
        if options.mode == "copy":
            log("Modo rapido: o video sera copiado, mas o audio sera recodificado para permitir a mescla.")

    video_use_info: Optional[dict[str, object]] = None
    if options.detection_mode == "video_use":
        detected_segments, duration, video_use_info = detect_video_use_segments(options, original_duration, log)
        keep_segments = build_keep_segments_from_speech(
            speech_segments=detected_segments,
            duration=duration,
            padding=options.padding,
            min_keep=options.min_keep,
        )
        detected_label = "Trechos Video Use identificados"
    elif options.detection_mode == "speech":
        detected_segments, duration = detect_speech_segments(options, audio_stream_count, original_duration, log)
        keep_segments = build_keep_segments_from_speech(
            speech_segments=detected_segments,
            duration=duration,
            padding=options.padding,
            min_keep=options.min_keep,
        )
        detected_label = "Trechos de fala identificados"
    else:
        detected_segments, duration = detect_silences(options, audio_stream_count, original_duration, log)
        keep_segments = build_keep_segments(
            silences=detected_segments,
            duration=duration,
            padding=options.padding,
            min_keep=options.min_keep,
        )
        detected_label = "Silencios encontrados"

    keep_segments = apply_protected_ranges(keep_segments, protected_ranges, duration)
    if not keep_segments:
        if options.detection_mode == "speech":
            raise RuntimeError("Nenhum trecho de fala foi encontrado com esses ajustes.")
        raise RuntimeError("Nenhum trecho com som foi encontrado com esses ajustes.")

    estimated_final_duration = sum(segment.duration for segment in keep_segments)
    removed = max(0.0, duration - estimated_final_duration)
    log(f"{detected_label}: {len(detected_segments)}")
    log(f"Trechos mantidos: {len(keep_segments)}")
    log(f"Tempo removido estimado: {_format_seconds(removed)}")

    with tempfile.TemporaryDirectory(prefix=".silence-cutter-", dir=str(options.output_path.parent)) as temp_dir:
        temp_path = Path(temp_dir)
        list_path = temp_path / "segments.txt"
        part_paths = []

        for index, segment in enumerate(keep_segments, start=1):
            part_path = temp_path / f"part_{index:05d}.mp4"
            part_paths.append(part_path)
            elapsed = time.monotonic() - workflow_started_at
            percent = (index - 1) / len(keep_segments) * 100
            log(
                f"Cortando trecho {index}/{len(keep_segments)} "
                f"({_format_seconds(segment.start)} -> {_format_seconds(segment.end)}) | "
                f"{_progress_line('Progresso', percent, elapsed)}"
            )
            _extract_segment(options, segment, part_path, audio_stream_count, index, len(keep_segments))

        with list_path.open("w", encoding="utf-8") as handle:
            for part_path in part_paths:
                safe = str(part_path).replace("\\", "/").replace("'", "'\\''")
                handle.write(f"file '{safe}'\n")

        log("Juntando trechos finais...")
        concat_cmd = [
            options.ffmpeg_path,
            "-hide_banner",
            "-y",
            "-fflags",
            "+genpts",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-max_muxing_queue_size",
            "9999",
            "-c",
            "copy",
            str(options.output_path),
        ]
        _run_checked(concat_cmd, context="Juntando os trechos finais")

    final_size = options.output_path.stat().st_size
    final_duration = parse_duration(options.ffmpeg_path, options.output_path) or estimated_final_duration
    final_elapsed = time.monotonic() - workflow_started_at
    reduced_duration = max(0.0, duration - final_duration)
    reduced_size = original_size - final_size

    log("")
    log("Resumo final:")
    log(f"Original: {_format_duration(duration)} | {_format_bytes(original_size)}")
    log(f"Final: {_format_duration(final_duration)} | {_format_bytes(final_size)}")
    log(f"Tempo reduzido: {_format_seconds(reduced_duration)} ({_format_percent(reduced_duration, duration)})")
    log(f"Tamanho: {_format_size_delta(reduced_size, original_size)}")
    log(f"Tempo total decorrido: {_format_seconds(final_elapsed)}")
    log(f"Pronto: {options.output_path}")
    if video_use_info is not None:
        _attach_video_use_artifacts(video_use_info, options, keep_segments, duration)
    report = _build_video_report(
        options=options,
        status="concluido",
        started_at=started_at_iso,
        elapsed=final_elapsed,
        original_duration=duration,
        original_size=original_size,
        final_duration=final_duration,
        final_size=final_size,
        audio_stream_count=audio_stream_count,
        detected_segment_count=len(detected_segments),
        keep_segments=keep_segments,
        protected_ranges=protected_ranges,
        estimated_final_duration=estimated_final_duration,
        reduced_duration=reduced_duration,
        reduced_size=reduced_size,
        video_use_info=video_use_info,
        backup_info=backup_info,
    )
    report_paths = save_report(report, reports_path(), options.output_path.stem)
    log(f"Relatorio TXT: {report_paths['txt']}")
    log(f"Relatorio JSON: {report_paths['json']}")
    return report


def cut_video_batch(jobs: list[CutterOptions], log: Callable[[str], None] = log_noop) -> tuple[int, int]:
    if not jobs:
        raise ValueError("Nenhum video foi informado para o lote.")

    started_at = time.monotonic()
    started_at_iso = _now_iso()
    successes = 0
    failures = 0
    reports: list[dict[str, object]] = []
    log(f"Iniciando lote com {len(jobs)} video(s).")

    for index, job in enumerate(jobs, start=1):
        video_started_at = time.monotonic()
        video_started_at_iso = _now_iso()
        log("")
        log(f"Lote {index}/{len(jobs)}: {job.input_path}")
        try:
            report = cut_video(job, log=log)
        except Exception as exc:
            failures += 1
            report = _build_error_report(job, exc, video_started_at_iso, time.monotonic() - video_started_at)
            try:
                report_paths = save_report(report, reports_path(), job.output_path.stem)
                log(f"Relatorio de erro TXT: {report_paths['txt']}")
                log(f"Relatorio de erro JSON: {report_paths['json']}")
            except Exception as report_exc:
                log(f"Nao foi possivel salvar o relatorio de erro: {report_exc}")
            reports.append(report)
            log(f"ERRO no video {index}/{len(jobs)}: {exc}")
        else:
            successes += 1
            reports.append(report)

    log("")
    log("Resumo do lote:")
    log(f"Concluidos: {successes}")
    log(f"Com erro: {failures}")
    elapsed = time.monotonic() - started_at
    log(f"Tempo total do lote: {_format_seconds(elapsed)}")
    batch_report = _build_batch_report(
        jobs=jobs,
        reports=reports,
        started_at=started_at_iso,
        elapsed=elapsed,
        successes=successes,
        failures=failures,
    )
    report_paths = save_report(batch_report, reports_path(), "relatorio_lote")
    log(f"Relatorio do lote TXT: {report_paths['txt']}")
    log(f"Relatorio do lote JSON: {report_paths['json']}")
    return successes, failures


def backup_existing_output(output_path: Path, log: Callable[[str], None] = log_noop) -> Optional[dict[str, object]]:
    if not output_path.exists():
        return None
    if output_path.is_dir():
        raise RuntimeError(f"O caminho de saida existe e e uma pasta: {output_path}")

    backup_dir = output_path.parent / "backups" / output_path.stem
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = _unique_path(backup_dir / f"{output_path.stem}_backup_{timestamp}{output_path.suffix}")
    original_size = output_path.stat().st_size
    shutil.move(str(output_path), str(backup_path))

    info = {
        "created_at": _now_iso(),
        "original_path": str(output_path),
        "backup_path": str(backup_path),
        "size_bytes": original_size,
        "size": _format_bytes(original_size),
    }
    log(f"Backup automatico da versao anterior: {backup_path}")
    return info


def _build_video_report(
    options: CutterOptions,
    status: str,
    started_at: str,
    elapsed: float,
    original_duration: float,
    original_size: int,
    final_duration: float,
    final_size: int,
    audio_stream_count: int,
    detected_segment_count: int,
    keep_segments: list[Segment],
    protected_ranges: list[Segment],
    estimated_final_duration: float,
    reduced_duration: float,
    reduced_size: int,
    video_use_info: Optional[dict[str, object]],
    backup_info: Optional[dict[str, object]],
) -> dict[str, object]:
    return {
        "type": "video",
        "app_version": APP_VERSION,
        "status": status,
        "generated_at": _now_iso(),
        "started_at": started_at,
        "completed_at": _now_iso(),
        "elapsed_seconds": round(elapsed, 3),
        "elapsed": _format_seconds(elapsed),
        "settings": _settings_report(options),
        "input": {
            "path": str(options.input_path),
            "duration_seconds": round(original_duration, 3),
            "duration": _format_duration(original_duration),
            "size_bytes": original_size,
            "size": _format_bytes(original_size),
        },
        "output": {
            "path": str(options.output_path),
            "duration_seconds": round(final_duration, 3),
            "duration": _format_duration(final_duration),
            "size_bytes": final_size,
            "size": _format_bytes(final_size),
        },
        "audio": {
            "stream_count": audio_stream_count,
            "merged": audio_stream_count > 1,
        },
        "analysis": {
            "detection_mode": options.detection_mode,
            "detected_segment_count": detected_segment_count,
            "silence_count": detected_segment_count if options.detection_mode == "silence" else None,
            "speech_segment_count": detected_segment_count if options.detection_mode == "speech" else None,
            "video_use_segment_count": detected_segment_count if options.detection_mode == "video_use" else None,
            "protected_range_count": len(protected_ranges),
            "kept_segment_count": len(keep_segments),
            "estimated_final_duration_seconds": round(estimated_final_duration, 3),
            "estimated_final_duration": _format_duration(estimated_final_duration),
        },
        "reduction": {
            "duration_seconds": round(reduced_duration, 3),
            "duration": _format_seconds(reduced_duration),
            "duration_percent": _percent_number(reduced_duration, original_duration),
            "size_bytes": reduced_size,
            "size": _format_bytes(reduced_size),
            "size_change": _format_size_delta(reduced_size, original_size),
            "size_percent": _percent_number(reduced_size, original_size),
        },
        "backup": backup_info,
        "video_use": video_use_info or {},
    }


def _build_error_report(
    options: CutterOptions,
    error: Exception,
    started_at: str,
    elapsed: float,
) -> dict[str, object]:
    return {
        "type": "video",
        "app_version": APP_VERSION,
        "status": "erro",
        "generated_at": _now_iso(),
        "started_at": started_at,
        "completed_at": _now_iso(),
        "elapsed_seconds": round(elapsed, 3),
        "elapsed": _format_seconds(elapsed),
        "settings": _settings_report(options),
        "input": {"path": str(options.input_path)},
        "output": {"path": str(options.output_path)},
        "error": str(error),
    }


def _build_batch_report(
    jobs: list[CutterOptions],
    reports: list[dict[str, object]],
    started_at: str,
    elapsed: float,
    successes: int,
    failures: int,
) -> dict[str, object]:
    return {
        "type": "batch",
        "app_version": APP_VERSION,
        "status": "concluido" if failures == 0 else "concluido_com_erros",
        "generated_at": _now_iso(),
        "started_at": started_at,
        "completed_at": _now_iso(),
        "elapsed_seconds": round(elapsed, 3),
        "elapsed": _format_seconds(elapsed),
        "total_videos": len(jobs),
        "successes": successes,
        "failures": failures,
        "summary": _batch_summary(reports),
        "videos": reports,
    }


def _batch_summary(reports: list[dict[str, object]]) -> dict[str, object]:
    successful = [report for report in reports if report.get("status") == "concluido"]
    original_size = sum(_nested_number(report, "input", "size_bytes") for report in successful)
    final_size = sum(_nested_number(report, "output", "size_bytes") for report in successful)
    original_duration = sum(_nested_number(report, "input", "duration_seconds") for report in successful)
    final_duration = sum(_nested_number(report, "output", "duration_seconds") for report in successful)
    reduced_size = original_size - final_size
    reduced_duration = max(0.0, original_duration - final_duration)
    return {
        "original_duration_seconds": round(original_duration, 3),
        "original_duration": _format_duration(original_duration),
        "final_duration_seconds": round(final_duration, 3),
        "final_duration": _format_duration(final_duration),
        "duration_reduced_seconds": round(reduced_duration, 3),
        "duration_reduced": _format_seconds(reduced_duration),
        "duration_reduced_percent": _percent_number(reduced_duration, original_duration),
        "original_size_bytes": int(original_size),
        "original_size": _format_bytes(int(original_size)),
        "final_size_bytes": int(final_size),
        "final_size": _format_bytes(int(final_size)),
        "size_reduced_bytes": int(reduced_size),
        "size_reduced": _format_bytes(int(reduced_size)),
        "size_change": _format_size_delta(int(reduced_size), int(original_size)),
        "size_reduced_percent": _percent_number(reduced_size, original_size),
    }


def save_report(report: dict[str, object], report_dir: Path, stem: str) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    base = f"{_safe_filename(stem)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    report_folder = _unique_path(report_dir / base)
    report_folder.mkdir(parents=True, exist_ok=True)
    txt_path = report_folder / f"{base}.txt"
    json_path = report_folder / f"{base}.json"
    report["report_files"] = {
        "folder": str(report_folder),
        "txt": str(txt_path),
        "json": str(json_path),
    }

    _save_video_use_artifacts(report, report_folder, base)
    txt_path.write_text(_render_report_text(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_version_history(report_dir / "historico_versoes.json", report, txt_path, json_path)
    return {"txt": str(txt_path), "json": str(json_path)}


def _save_video_use_artifacts(report: dict[str, object], report_folder: Path, base: str) -> None:
    video_use = report.get("video_use")
    if not isinstance(video_use, dict) or not video_use:
        return

    packed_content = video_use.pop("_takes_packed_content", "")
    if isinstance(packed_content, str) and packed_content.strip():
        packed_path = report_folder / f"{base}_takes_packed.md"
        packed_path.write_text(packed_content, encoding="utf-8")
        video_use["takes_packed_path"] = str(packed_path)

    edl_payload = video_use.pop("_edl_json", None)
    if isinstance(edl_payload, dict):
        edl_path = report_folder / f"{base}_video_use_edl.json"
        edl_path.write_text(json.dumps(edl_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        video_use["edl_path"] = str(edl_path)


def app_base_dir() -> Path:
    return Path(__file__).resolve().parent


def reports_path() -> Path:
    return app_base_dir() / "relatorios"


def _settings_report(options: CutterOptions) -> dict[str, object]:
    return {
        "ffmpeg_path": options.ffmpeg_path,
        "threshold_db": options.threshold_db,
        "min_silence_seconds": options.min_silence,
        "padding_seconds": options.padding,
        "min_keep_seconds": options.min_keep,
        "detection_mode": options.detection_mode,
        "ignore_ranges": options.ignore_ranges,
        "video_use_transcript": options.video_use_transcript,
        "mode": options.mode,
    }


def _render_report_text(report: dict[str, object]) -> str:
    if report.get("type") == "batch":
        return _render_batch_report_text(report)
    return _render_video_report_text(report)


def _render_video_report_text(report: dict[str, object]) -> str:
    lines = [
        "Relatorio de corte de silencio",
        "=" * 31,
        f"Versao da ferramenta: {report.get('app_version', '')}",
        f"Status: {report.get('status', '')}",
        f"Gerado em: {report.get('generated_at', '')}",
        f"Inicio: {report.get('started_at', '')}",
        f"Fim: {report.get('completed_at', '')}",
        f"Tempo decorrido: {report.get('elapsed', '')}",
        "",
    ]

    settings = report.get("settings", {})
    input_data = report.get("input", {})
    output_data = report.get("output", {})
    audio = report.get("audio", {})
    analysis = report.get("analysis", {})
    reduction = report.get("reduction", {})
    backup = report.get("backup", {})
    video_use = report.get("video_use", {})

    lines += [
        "Arquivos",
        "- Entrada: " + str(_dict_get(input_data, "path")),
        "- Saida: " + str(_dict_get(output_data, "path")),
        "",
        "Original",
        "- Duracao: " + str(_dict_get(input_data, "duration", "indisponivel")),
        "- Tamanho: " + str(_dict_get(input_data, "size", "indisponivel")),
        "",
        "Final",
        "- Duracao: " + str(_dict_get(output_data, "duration", "indisponivel")),
        "- Tamanho: " + str(_dict_get(output_data, "size", "indisponivel")),
        "",
        "Reducao",
        "- Tempo reduzido: "
        + str(_dict_get(reduction, "duration", "indisponivel"))
        + " ("
        + _format_optional_percent(_dict_get(reduction, "duration_percent"))
        + ")",
        "- Tamanho: "
        + str(_dict_get(reduction, "size_change", "indisponivel")),
        "",
        "Audio",
        "- Faixas encontradas: " + str(_dict_get(audio, "stream_count", "indisponivel")),
        "- Faixas mescladas: " + ("sim" if _dict_get(audio, "merged") else "nao"),
        "",
        "Ajustes",
        "- ffmpeg: " + str(_dict_get(settings, "ffmpeg_path")),
        "- Silencio abaixo de dB: " + str(_dict_get(settings, "threshold_db")),
        "- Silencio minimo: " + str(_dict_get(settings, "min_silence_seconds")) + "s",
        "- Margem: " + str(_dict_get(settings, "padding_seconds")) + "s",
        "- Trecho minimo: " + str(_dict_get(settings, "min_keep_seconds")) + "s",
        "- Deteccao: " + _detection_mode_label(str(_dict_get(settings, "detection_mode", "speech"))),
        "- Trechos protegidos: " + (str(_dict_get(settings, "ignore_ranges")) or "nenhum"),
        "- Transcript Video Use: " + (str(_dict_get(settings, "video_use_transcript")) or "auto"),
        "- Modo: " + str(_dict_get(settings, "mode")),
        "",
    ]

    if backup:
        lines += [
            "Backup automatico",
            "- Arquivo anterior: " + str(_dict_get(backup, "original_path")),
            "- Backup salvo em: " + str(_dict_get(backup, "backup_path")),
            "- Tamanho do backup: " + str(_dict_get(backup, "size", "indisponivel")),
            "- Criado em: " + str(_dict_get(backup, "created_at", "indisponivel")),
            "",
        ]
    else:
        lines += [
            "Backup automatico",
            "- Nenhuma versao anterior foi encontrada para este caminho de saida.",
            "",
        ]

    if report.get("status") == "erro":
        lines += ["Erro", str(report.get("error", "")), ""]
        return "\n".join(lines)

    lines += [
        "Analise",
        "- Modo de deteccao: " + _detection_mode_label(str(_dict_get(analysis, "detection_mode", "speech"))),
        "- " + _detected_count_label(str(_dict_get(analysis, "detection_mode", "speech"))) + ": " + str(_dict_get(analysis, "detected_segment_count", 0)),
        "- Trechos protegidos sem corte: " + str(_dict_get(analysis, "protected_range_count", 0)),
        "- Trechos mantidos: " + str(_dict_get(analysis, "kept_segment_count", 0)),
        "- Duracao final estimada: " + str(_dict_get(analysis, "estimated_final_duration", "indisponivel")),
        "",
    ]

    if isinstance(video_use, dict) and video_use:
        lines += [
            "Video Use",
            "- Transcript: " + str(_dict_get(video_use, "transcript_path", "indisponivel")),
            "- Palavras analisadas: " + str(_dict_get(video_use, "word_count", 0)),
            "- Frases agrupadas: " + str(_dict_get(video_use, "phrase_count", 0)),
            "- takes_packed.md: " + str(_dict_get(video_use, "takes_packed_path", "nao gerado")),
            "- EDL: " + str(_dict_get(video_use, "edl_path", "nao gerado")),
            "",
        ]
    return "\n".join(lines)


def _render_batch_report_text(report: dict[str, object]) -> str:
    summary = report.get("summary", {})
    lines = [
        "Relatorio de lote - corte de silencio",
        "=" * 36,
        f"Versao da ferramenta: {report.get('app_version', '')}",
        f"Status: {report.get('status', '')}",
        f"Gerado em: {report.get('generated_at', '')}",
        f"Inicio: {report.get('started_at', '')}",
        f"Fim: {report.get('completed_at', '')}",
        f"Tempo decorrido: {report.get('elapsed', '')}",
        f"Videos no lote: {report.get('total_videos', 0)}",
        f"Concluidos: {report.get('successes', 0)}",
        f"Com erro: {report.get('failures', 0)}",
        "",
        "Totais dos videos concluidos",
        "- Duracao original: " + str(_dict_get(summary, "original_duration", "indisponivel")),
        "- Duracao final: " + str(_dict_get(summary, "final_duration", "indisponivel")),
        "- Tempo reduzido: "
        + str(_dict_get(summary, "duration_reduced", "indisponivel"))
        + " ("
        + _format_optional_percent(_dict_get(summary, "duration_reduced_percent"))
        + ")",
        "- Tamanho original: " + str(_dict_get(summary, "original_size", "indisponivel")),
        "- Tamanho final: " + str(_dict_get(summary, "final_size", "indisponivel")),
        "- Tamanho reduzido: "
        + str(_dict_get(summary, "size_change", "indisponivel")),
        "",
        "Videos",
    ]

    for index, video in enumerate(report.get("videos", []), start=1):
        input_data = _dict_get(video, "input", {})
        output_data = _dict_get(video, "output", {})
        reduction = _dict_get(video, "reduction", {})
        lines += [
            f"{index}. {video.get('status', '')}",
            "   Entrada: " + str(_dict_get(input_data, "path")),
            "   Saida: " + str(_dict_get(output_data, "path")),
            "   Tempo reduzido: "
            + str(_dict_get(reduction, "duration", "indisponivel"))
            + " ("
            + _format_optional_percent(_dict_get(reduction, "duration_percent"))
            + ")",
            "   Tamanho: "
            + str(_dict_get(reduction, "size_change", "indisponivel")),
        ]
        if video.get("status") == "erro":
            lines.append("   Erro: " + str(video.get("error", "")))
        backup = _dict_get(video, "backup", {})
        if backup:
            lines.append("   Backup anterior: " + str(_dict_get(backup, "backup_path")))
        report_files = _dict_get(video, "report_files", {})
        if report_files:
            lines.append("   Relatorio TXT: " + str(_dict_get(report_files, "txt")))
            lines.append("   Relatorio JSON: " + str(_dict_get(report_files, "json")))
        lines.append("")

    return "\n".join(lines)


def _append_version_history(history_path: Path, report: dict[str, object], txt_path: Path, json_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    else:
        history = []

    if not isinstance(history, list):
        history = []

    history.append(_history_entry(report, txt_path, json_path))
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def _history_entry(report: dict[str, object], txt_path: Path, json_path: Path) -> dict[str, object]:
    entry: dict[str, object] = {
        "app_version": APP_VERSION,
        "type": report.get("type"),
        "status": report.get("status"),
        "generated_at": report.get("generated_at"),
        "report_txt": str(txt_path),
        "report_json": str(json_path),
    }
    if report.get("type") == "batch":
        entry.update(
            {
                "total_videos": report.get("total_videos"),
                "successes": report.get("successes"),
                "failures": report.get("failures"),
            }
        )
    else:
        entry.update(
            {
                "input": _dict_get(_dict_get(report, "input", {}), "path"),
                "output": _dict_get(_dict_get(report, "output", {}), "path"),
                "backup": _dict_get(_dict_get(report, "backup", {}), "backup_path", None),
            }
        )
    return entry


def _detection_mode_label(value: str) -> str:
    if value == "silence":
        return "silencio tradicional"
    if value == "video_use":
        return "Video Use por palavra"
    return "fala"


def _detected_count_label(value: str) -> str:
    if value == "silence":
        return "Silencios encontrados"
    if value == "video_use":
        return "Trechos Video Use identificados"
    return "Trechos de fala identificados"


def _dict_get(value: object, key: str, default: object = "") -> object:
    if isinstance(value, dict):
        return value.get(key, default)
    return default


def _nested_number(report: dict[str, object], section: str, key: str) -> float:
    value = _dict_get(_dict_get(report, section, {}), key, 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _format_optional_percent(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    return "indisponivel"


def _percent_number(value: float, total: float) -> Optional[float]:
    if total <= 0:
        return None
    return round(value / total * 100, 3)


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "relatorio"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _extract_segment(
    options: CutterOptions,
    segment: Segment,
    part_path: Path,
    audio_stream_count: int,
    segment_index: int,
    total_segments: int,
) -> None:
    cmd = [
        options.ffmpeg_path,
        "-hide_banner",
        "-y",
        "-nostdin",
        "-fflags",
        "+genpts",
        "-ss",
        f"{segment.start:.3f}",
        "-t",
        f"{segment.duration:.3f}",
        "-i",
        str(options.input_path),
    ]

    if audio_stream_count > 1:
        cmd += [
            "-filter_complex",
            _audio_mix_filter(audio_stream_count, output_label="mixedaudio"),
            "-map",
            "0:v:0?",
            "-map",
            "[mixedaudio]",
        ]
        if options.mode == "copy":
            cmd += [
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-max_muxing_queue_size",
                "9999",
                "-avoid_negative_ts",
                "make_zero",
            ]
        else:
            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-max_muxing_queue_size",
                "9999",
                "-avoid_negative_ts",
                "make_zero",
                "-movflags",
                "+faststart",
            ]
    elif options.mode == "copy":
        cmd += [
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-max_muxing_queue_size",
            "9999",
            "-avoid_negative_ts",
            "make_zero",
        ]
    else:
        cmd += [
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-max_muxing_queue_size",
            "9999",
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
        ]

    cmd.append(str(part_path))
    _run_checked(
        cmd,
        context=(
            f"Cortando trecho {segment_index}/{total_segments} "
            f"({_format_seconds(segment.start)} -> {_format_seconds(segment.end)})"
        ),
    )


def _run_checked(cmd: list[str], context: str = "Executando ffmpeg") -> None:
    proc = _run_process(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        log_path = _save_ffmpeg_error_log(context, cmd, proc.stderr or "")
        detail = _summarize_ffmpeg_error(proc.stderr or "")
        raise RuntimeError(
            f"{context}\n"
            f"O ffmpeg falhou. Detalhe provavel:\n{detail}\n\n"
            f"Log completo: {log_path}"
        )


def _summarize_ffmpeg_error(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "sem mensagem detalhada do ffmpeg"

    noise_patterns = (
        r"^\[libx264",
        r"^frame=",
        r"^video:",
        r"^audio:",
        r"^subtitle:",
        r"^Input #",
        r"^Output #",
        r"^Stream mapping:",
        r"^Press \[q\]",
        r"^Conversion failed!?$",
    )
    useful = [
        line
        for line in lines
        if not any(re.search(pattern, line) for pattern in noise_patterns)
    ]

    error_keywords = (
        "error",
        "failed",
        "invalid",
        "no space",
        "permission",
        "denied",
        "could not",
        "non-monotonous",
        "too many packets",
        "muxing",
        "encoder",
        "decoder",
        "unable",
        "impossible",
    )
    priority = [
        line
        for line in useful
        if any(keyword in line.lower() for keyword in error_keywords)
    ]
    selected = priority[-8:] if priority else useful[-8:]
    return "\n".join(selected) if selected else "\n".join(lines[-8:])


def _save_ffmpeg_error_log(context: str, cmd: list[str], stderr: str) -> Path:
    log_dir = reports_path() / "erros_ffmpeg"
    log_dir.mkdir(parents=True, exist_ok=True)
    base = f"ffmpeg_erro_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_path = _unique_path(log_dir / f"{base}.log")
    content = [
        f"Contexto: {context}",
        f"Gerado em: {_now_iso()}",
        "",
        "Comando:",
        " ".join(_quote_arg(part) for part in cmd),
        "",
        "Saida de erro do ffmpeg:",
        stderr or "(vazio)",
    ]
    log_path.write_text("\n".join(content), encoding="utf-8")
    return log_path


def _quote_arg(value: str) -> str:
    if re.search(r"\s", value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _format_seconds(value: float) -> str:
    value = max(0.0, value)
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def _format_duration(value: float) -> str:
    if value <= 0:
        return "duracao desconhecida"
    return _format_seconds(value)


def _format_bytes(size: int) -> str:
    value = float(abs(size))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    sign = "-" if size < 0 else ""
    if unit == "B":
        return f"{sign}{int(value)} {unit}"
    return f"{sign}{value:.2f} {unit}"


def _format_percent(value: float, total: float) -> str:
    if total <= 0:
        return "percentual indisponivel"
    return f"{value / total * 100:.1f}%"


def _format_size_delta(reduced_size: int, original_size: int) -> str:
    if reduced_size >= 0:
        return f"reduzido {_format_bytes(reduced_size)} ({_format_percent(reduced_size, original_size)})"
    return f"aumentou {_format_bytes(abs(reduced_size))} ({_format_percent(abs(reduced_size), original_size)})"


def _progress_line(label: str, percent: float, elapsed: float) -> str:
    return (
        f"{label}: {percent:5.1f}% | "
        f"decorrido {_format_seconds(elapsed)} | "
        f"estimado restante {_format_eta(elapsed, percent)}"
    )


def _format_eta(elapsed: float, percent: float) -> str:
    if percent <= 0:
        return "calculando"
    remaining = elapsed * (100 - percent) / percent
    return _format_seconds(remaining)


def build_batch_jobs(
    input_paths: list[Path],
    output_dir: Path,
    template: CutterOptions,
    suffix: str = "_sem_silencio",
) -> list[CutterOptions]:
    output_dir = output_dir.expanduser()
    used_outputs: set[Path] = set()
    jobs: list[CutterOptions] = []

    for input_path in input_paths:
        output_path = _unique_batch_output(input_path, output_dir, suffix, used_outputs)
        jobs.append(clone_options(template, input_path, output_path))

    return jobs


def _unique_batch_output(input_path: Path, output_dir: Path, suffix: str, used_outputs: set[Path]) -> Path:
    base_name = f"{input_path.stem}{suffix}.mp4"
    candidate = output_dir / base_name
    counter = 2
    while candidate in used_outputs or candidate.exists():
        candidate = output_dir / f"{input_path.stem}{suffix}_{counter}.mp4"
        counter += 1
    used_outputs.add(candidate)
    return candidate


def presets_path() -> Path:
    return app_base_dir() / PRESETS_FILENAME


def default_presets() -> dict[str, dict[str, object]]:
    return {
        "Padrao": {
            "threshold_db": -35.0,
            "min_silence": 0.45,
            "padding": 0.12,
            "min_keep": 0.18,
            "detection_mode": "speech",
            "mode": "reencode",
        }
    }


def load_presets(path: Optional[Path] = None) -> dict[str, dict[str, object]]:
    path = path or presets_path()
    if not path.exists():
        return default_presets()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_presets()

    raw_presets = data.get("presets") if isinstance(data, dict) else None
    if not isinstance(raw_presets, dict):
        return default_presets()

    presets: dict[str, dict[str, object]] = {}
    for name, values in raw_presets.items():
        if not isinstance(name, str) or not isinstance(values, dict):
            continue
        normalized = normalize_preset(values)
        if normalized:
            presets[name] = normalized
    return presets


def save_presets(presets: dict[str, dict[str, object]], path: Optional[Path] = None) -> None:
    path = path or presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "updated_at": _now_iso(),
        "presets": presets,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_preset(values: dict[str, object]) -> dict[str, object]:
    try:
        mode = str(values.get("mode", "reencode"))
        if mode not in {"reencode", "copy"}:
            mode = "reencode"
        detection_mode = str(values.get("detection_mode", "speech"))
        if detection_mode not in {"speech", "silence", "video_use"}:
            detection_mode = "speech"
        return {
            "threshold_db": float(values.get("threshold_db", -35.0)),
            "min_silence": float(values.get("min_silence", 0.45)),
            "padding": float(values.get("padding", 0.12)),
            "min_keep": float(values.get("min_keep", 0.18)),
            "detection_mode": detection_mode,
            "mode": mode,
        }
    except (TypeError, ValueError):
        return {}


class HoverTip:
    def __init__(self, widget: object, text: str, delay_ms: int = 350) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip_window: Optional[object] = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._after_id = None
        if self._tip_window is not None:
            return

        x = self.widget.winfo_rootx() + 22
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip_window = tk.Toplevel(self.widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self._tip_window,
            text=self.text,
            justify="left",
            wraplength=360,
            background="#ffffe0",
            foreground="#111111",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
        )
        label.pack()

    def _hide(self, _event: object = None) -> None:
        self._cancel()
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None


class SilenceCutterApp:
    def __init__(self) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter nao esta disponivel neste Python.")

        self.root = tk.Tk()
        self.root.title(f"Encut v{APP_VERSION}")
        self.root.geometry("820x620")
        self.root.minsize(760, 560)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.update_worker: Optional[threading.Thread] = None
        self.input_paths: list[Path] = []
        self.presets = load_presets()

        ffmpeg_default = default_ffmpeg_path()
        ffmpeg_found = "" if ffmpeg_default == "ffmpeg" else ffmpeg_default
        self.ffmpeg_var = tk.StringVar(value=ffmpeg_found)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.ignore_ranges_var = tk.StringVar()
        self.video_use_transcript_var = tk.StringVar()
        self.threshold_var = tk.DoubleVar(value=-35.0)
        self.min_silence_var = tk.DoubleVar(value=0.45)
        self.padding_var = tk.DoubleVar(value=0.12)
        self.min_keep_var = tk.DoubleVar(value=0.18)
        self.detection_mode_var = tk.StringVar(value="speech")
        self.mode_var = tk.StringVar(value="reencode")
        self.preset_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Selecione um ou mais videos para comecar.")

        self._build_ui()
        self.root.after(100, self._drain_events)
        self.root.after(1200, self._check_updates_on_startup)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(12, weight=1)

        title = ttk.Label(main, text="Encut - cortes de silencio para videos grandes", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self._file_row(main, 1, "Videos", self.input_var, self._pick_input, HELP_TEXTS["videos"])
        self._file_row(main, 2, "Saida / pasta", self.output_var, self._pick_output, HELP_TEXTS["output"])
        self._file_row(main, 3, "ffmpeg.exe", self.ffmpeg_var, self._pick_ffmpeg, HELP_TEXTS["ffmpeg"])
        self._file_row(main, 4, "Transcript Video Use", self.video_use_transcript_var, self._pick_video_use_transcript, HELP_TEXTS["video_use_transcript"])
        self._text_row(main, 5, "Ignorar cortes", self.ignore_ranges_var, HELP_TEXTS["ignore_ranges"])

        settings = ttk.LabelFrame(main, text="Ajustes")
        settings.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        for col in range(4):
            settings.columnconfigure(col, weight=1)

        self._number_field(settings, 0, "Silencio abaixo de (dB)", self.threshold_var, HELP_TEXTS["threshold"])
        self._number_field(settings, 1, "Silencio minimo (s)", self.min_silence_var, HELP_TEXTS["min_silence"])
        self._number_field(settings, 2, "Margem antes/depois (s)", self.padding_var, HELP_TEXTS["padding"])
        self._number_field(settings, 3, "Trecho minimo (s)", self.min_keep_var, HELP_TEXTS["min_keep"])

        detection_frame = ttk.Frame(main)
        detection_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        self._label_with_help(detection_frame, "Deteccao", HELP_TEXTS["detection"]).pack(side="left")
        self._radio_with_help(detection_frame, "Fala precisa", self.detection_mode_var, "speech", HELP_TEXTS["detection_speech"], padx=(16, 0))
        self._radio_with_help(detection_frame, "Video Use", self.detection_mode_var, "video_use", HELP_TEXTS["detection_video_use"], padx=(16, 0))
        self._radio_with_help(detection_frame, "Silencio tradicional", self.detection_mode_var, "silence", HELP_TEXTS["detection_silence"], padx=(16, 0))

        mode_frame = ttk.Frame(main)
        mode_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 10))
        self._label_with_help(mode_frame, "Modo", HELP_TEXTS["mode"]).pack(side="left")
        self._radio_with_help(mode_frame, "Preciso (re-encode)", self.mode_var, "reencode", HELP_TEXTS["mode_reencode"], padx=(16, 0))
        self._radio_with_help(mode_frame, "Rapido (sem re-encode)", self.mode_var, "copy", HELP_TEXTS["mode_copy"], padx=(16, 0))

        presets_frame = ttk.Frame(main)
        presets_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        presets_frame.columnconfigure(1, weight=1)
        self._label_with_help(presets_frame, "Preset", HELP_TEXTS["presets"]).grid(row=0, column=0, sticky="w")
        self.preset_combo = ttk.Combobox(presets_frame, textvariable=self.preset_var, state="readonly", width=28)
        self.preset_combo.grid(row=0, column=1, sticky="ew", padx=8)
        self._preset_button(presets_frame, 2, "Carregar", self._load_selected_preset, HELP_TEXTS["preset_load"])
        self._preset_button(presets_frame, 3, "Salvar", self._save_current_preset, HELP_TEXTS["preset_save"])
        self._preset_button(presets_frame, 4, "Excluir", self._delete_selected_preset, HELP_TEXTS["preset_delete"])
        self._refresh_preset_combo()

        actions = ttk.Frame(main)
        actions.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(2, 12))
        start_group = ttk.Frame(actions)
        start_group.pack(side="left")
        self.start_button = ttk.Button(start_group, text="Cortar silencio", command=self._start)
        self.start_button.pack(side="left")
        self._help_icon(start_group, HELP_TEXTS["start"]).pack(side="left", padx=(4, 0))

        clear_group = ttk.Frame(actions)
        clear_group.pack(side="left", padx=8)
        ttk.Button(clear_group, text="Limpar log", command=self._clear_log).pack(side="left")
        self._help_icon(clear_group, HELP_TEXTS["clear_log"]).pack(side="left", padx=(4, 0))

        update_group = ttk.Frame(actions)
        update_group.pack(side="left")
        self.update_button = ttk.Button(update_group, text="Atualizar", command=lambda: self._check_updates(auto=False))
        self.update_button.pack(side="left")
        self._help_icon(update_group, "Verifica no site configurado se existe uma versao nova do Encut. Se houver, baixa o pacote, confere o SHA256 quando informado e executa o instalador automaticamente.").pack(side="left", padx=(4, 0))

        ttk.Label(main, textvariable=self.status_var).grid(row=11, column=0, columnspan=3, sticky="w")

        self.log_text = tk.Text(main, height=12, wrap="word")
        self.log_text.grid(row=12, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.log_text.configure(state="disabled")

    def _file_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, command: Callable[[], None], help_text: str) -> None:
        self._label_with_help(parent, label, help_text).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Selecionar", command=command).grid(row=row, column=2, sticky="e", pady=4)

    def _text_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, help_text: str) -> None:
        self._label_with_help(parent, label, help_text).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)

    def _number_field(self, parent: ttk.LabelFrame, column: int, label: str, var: tk.DoubleVar, help_text: str) -> None:
        frame = ttk.Frame(parent, padding=8)
        frame.grid(row=0, column=column, sticky="ew")
        self._label_with_help(frame, label, help_text).pack(anchor="w")
        ttk.Entry(frame, textvariable=var, width=12).pack(anchor="w", pady=(4, 0))

    def _label_with_help(self, parent: object, label: str, help_text: str) -> ttk.Frame:
        frame = ttk.Frame(parent)
        ttk.Label(frame, text=label).pack(side="left")
        self._help_icon(frame, help_text).pack(side="left", padx=(4, 0))
        return frame

    def _help_icon(self, parent: object, help_text: str) -> ttk.Label:
        icon = ttk.Label(parent, text="?", cursor="question_arrow")
        HoverTip(icon, help_text)
        return icon

    def _radio_with_help(self, parent: object, text: str, variable: tk.StringVar, value: str, help_text: str, padx: tuple[int, int]) -> None:
        frame = ttk.Frame(parent)
        frame.pack(side="left", padx=padx)
        ttk.Radiobutton(frame, text=text, variable=variable, value=value).pack(side="left")
        self._help_icon(frame, help_text).pack(side="left", padx=(4, 0))

    def _preset_button(self, parent: object, column: int, text: str, command: Callable[[], None], help_text: str) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="e", padx=(0, 6))
        ttk.Button(frame, text=text, command=command).pack(side="left")
        self._help_icon(frame, help_text).pack(side="left", padx=(4, 0))

    def _refresh_preset_combo(self, select_name: Optional[str] = None) -> None:
        names = sorted(self.presets)
        self.preset_combo.configure(values=names)
        if select_name and select_name in self.presets:
            self.preset_var.set(select_name)
        elif self.preset_var.get() not in self.presets:
            self.preset_var.set(names[0] if names else "")

    def _current_preset_values(self) -> dict[str, object]:
        return normalize_preset(
            {
                "threshold_db": self.threshold_var.get(),
                "min_silence": self.min_silence_var.get(),
                "padding": self.padding_var.get(),
                "min_keep": self.min_keep_var.get(),
                "detection_mode": self.detection_mode_var.get(),
                "mode": self.mode_var.get(),
            }
        )

    def _apply_preset_values(self, values: dict[str, object]) -> None:
        normalized = normalize_preset(values)
        if not normalized:
            raise ValueError("Preset invalido.")
        self.threshold_var.set(float(normalized["threshold_db"]))
        self.min_silence_var.set(float(normalized["min_silence"]))
        self.padding_var.set(float(normalized["padding"]))
        self.min_keep_var.set(float(normalized["min_keep"]))
        self.detection_mode_var.set(str(normalized["detection_mode"]))
        self.mode_var.set(str(normalized["mode"]))

    def _load_selected_preset(self) -> None:
        name = self.preset_var.get().strip()
        if not name or name not in self.presets:
            messagebox.showerror("Preset", "Selecione um preset para carregar.")
            return
        try:
            self._apply_preset_values(self.presets[name])
        except ValueError as exc:
            messagebox.showerror("Preset invalido", str(exc))
            return
        self.status_var.set(f"Preset carregado: {name}")
        self._append_log(f"Preset carregado: {name}")

    def _save_current_preset(self) -> None:
        if simpledialog is None:
            messagebox.showerror("Preset", "Dialogo de texto indisponivel neste Python.")
            return
        suggested = self.preset_var.get().strip() or "Meu preset"
        name = simpledialog.askstring("Salvar preset", "Nome do preset:", initialvalue=suggested, parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Preset", "Informe um nome para o preset.")
            return
        values = self._current_preset_values()
        if not values:
            messagebox.showerror("Preset", "Confira os valores dos ajustes antes de salvar.")
            return
        self.presets[name] = values
        save_presets(self.presets)
        self._refresh_preset_combo(name)
        self.status_var.set(f"Preset salvo: {name}")
        self._append_log(f"Preset salvo: {name}")

    def _delete_selected_preset(self) -> None:
        name = self.preset_var.get().strip()
        if not name or name not in self.presets:
            messagebox.showerror("Preset", "Selecione um preset para excluir.")
            return
        if not messagebox.askyesno("Excluir preset", f"Excluir o preset '{name}'?"):
            return
        del self.presets[name]
        save_presets(self.presets)
        self._refresh_preset_combo()
        self.status_var.set(f"Preset excluido: {name}")
        self._append_log(f"Preset excluido: {name}")

    def _pick_input(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecionar video(s)",
            filetypes=[("Videos", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"), ("Todos", "*.*")],
        )
        if paths:
            self.input_paths = [Path(path) for path in paths]
            if len(self.input_paths) == 1:
                current = self.input_paths[0]
                self.input_var.set(str(current))
                self.output_var.set(str(current.with_name(f"{current.stem}_sem_silencio.mp4")))
                self.status_var.set("1 video selecionado.")
            else:
                preview = ", ".join(path.name for path in self.input_paths[:3])
                if len(self.input_paths) > 3:
                    preview += ", ..."
                self.input_var.set(f"{len(self.input_paths)} videos selecionados: {preview}")
                self.output_var.set(str(self.input_paths[0].parent / "sem_silencio"))
                self.status_var.set(f"{len(self.input_paths)} videos selecionados.")

    def _pick_output(self) -> None:
        if len(self.input_paths) > 1:
            path = filedialog.askdirectory(title="Selecionar pasta de saida")
        else:
            path = filedialog.asksaveasfilename(
                title="Salvar video como",
                defaultextension=".mp4",
                filetypes=[("MP4", "*.mp4"), ("Todos", "*.*")],
            )
        if path:
            self.output_var.set(path)

    def _pick_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(title="Selecionar ffmpeg.exe", filetypes=[("ffmpeg", "ffmpeg.exe"), ("Todos", "*.*")])
        if path:
            self.ffmpeg_var.set(path)

    def _pick_video_use_transcript(self) -> None:
        if len(self.input_paths) > 1:
            path = filedialog.askdirectory(title="Selecionar pasta de transcripts Video Use")
        else:
            path = filedialog.askopenfilename(
                title="Selecionar transcript Video Use",
                filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            )
        if path:
            self.video_use_transcript_var.set(path)

    def _check_updates_on_startup(self) -> None:
        config = load_update_config()
        if bool(config.get("enabled", True)) and bool(config.get("check_on_startup", True)) and str(config.get("manifest_url", "")).strip():
            self._check_updates(auto=True)

    def _check_updates(self, auto: bool = False) -> None:
        if self.update_worker and self.update_worker.is_alive():
            return
        if not auto:
            self.update_button.configure(state="disabled")
            self.status_var.set("Verificando atualizacao...")
            self._append_log("Verificando atualizacao do Encut...")
        self.update_worker = threading.Thread(target=self._run_update_check, args=(auto,), daemon=True)
        self.update_worker.start()

    def _run_update_check(self, auto: bool) -> None:
        try:
            config = load_update_config()
            manifest_url = str(config.get("manifest_url", "")).strip()
            if not bool(config.get("enabled", True)) or not manifest_url:
                if not auto:
                    self.events.put(("update_status", "Atualizacao nao configurada. Informe a URL do update.json em update_config.json."))
                return
            update = check_for_update(manifest_url)
            if update is None:
                if not auto:
                    self.events.put(("update_status", f"Encut ja esta atualizado (v{APP_VERSION})."))
                return
            self.events.put(("update_available", update))
        except Exception as exc:
            if auto:
                self.events.put(("log", f"Atualizacao: nao foi possivel verificar ({exc})"))
            else:
                self.events.put(("update_error", str(exc)))

    def _start_update_install(self, update: UpdateInfo) -> None:
        self.update_button.configure(state="disabled")
        self.status_var.set(f"Atualizando para v{update.version}...")
        self._append_log(f"Atualizando Encut para v{update.version}...")
        self.update_worker = threading.Thread(target=self._run_update_install, args=(update,), daemon=True)
        self.update_worker.start()

    def _run_update_install(self, update: UpdateInfo) -> None:
        try:
            install_update(update, log=lambda text: self.events.put(("log", "Atualizacao: " + text)))
            self.events.put(("update_done", update.version))
        except Exception as exc:
            self.events.put(("update_error", str(exc)))
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            options = self._options_from_ui()
        except Exception as exc:
            messagebox.showerror("Ajustes invalidos", str(exc))
            return

        self.start_button.configure(state="disabled")
        self.status_var.set("Processando...")
        if len(options) == 1:
            self._append_log(f"Iniciando corte de silencio | versao {APP_VERSION}.")
        else:
            self._append_log(f"Iniciando lote com {len(options)} videos | versao {APP_VERSION}.")
        self.worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True)
        self.worker.start()

    def _options_from_ui(self) -> list[CutterOptions]:
        input_text = self.input_var.get().strip()
        output_text = self.output_var.get().strip()
        ffmpeg_path = self.ffmpeg_var.get().strip() or default_ffmpeg_path()
        input_paths = self.input_paths or ([Path(input_text)] if input_text else [])
        if not input_paths:
            raise ValueError("Selecione o video de entrada.")
        if not output_text:
            raise ValueError("Escolha o arquivo de saida ou pasta de saida.")
        template = CutterOptions(
            input_path=input_paths[0],
            output_path=Path(output_text),
            ffmpeg_path=ffmpeg_path,
            threshold_db=float(self.threshold_var.get()),
            min_silence=float(self.min_silence_var.get()),
            padding=float(self.padding_var.get()),
            min_keep=float(self.min_keep_var.get()),
            detection_mode=self.detection_mode_var.get(),
            ignore_ranges=self.ignore_ranges_var.get().strip(),
            video_use_transcript=self.video_use_transcript_var.get().strip(),
            mode=self.mode_var.get(),
        )

        if len(input_paths) == 1:
            return [template]

        return build_batch_jobs(input_paths, Path(output_text), template)

    def _run_worker(self, options: list[CutterOptions]) -> None:
        try:
            if len(options) == 1:
                cut_video(options[0], log=lambda text: self.events.put(("log", text)))
                self.events.put(("done", str(options[0].output_path)))
            else:
                successes, failures = cut_video_batch(options, log=lambda text: self.events.put(("log", text)))
                self.events.put(("batch_done", f"{successes} concluido(s), {failures} com erro."))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(text)
                if text.startswith("Analisando:") or text.startswith("Lote ") or "Progresso:" in text:
                    self.status_var.set(text)
            elif kind == "error":
                self.start_button.configure(state="normal")
                self.status_var.set("Erro.")
                self._append_log(f"ERRO: {text}")
                messagebox.showerror("Erro", text)
            elif kind == "done":
                self.start_button.configure(state="normal")
                self.status_var.set("Concluido.")
                self._append_log(f"Concluido: {text}")
                messagebox.showinfo("Concluido", f"Video salvo em:\n{text}")
            elif kind == "batch_done":
                self.start_button.configure(state="normal")
                self.status_var.set("Lote concluido.")
                self._append_log(f"Lote concluido: {text}")
                messagebox.showinfo("Lote concluido", str(text))
            elif kind == "update_status":
                self.update_button.configure(state="normal")
                self.status_var.set(str(text))
                self._append_log(str(text))
                messagebox.showinfo("Atualizacao", str(text))
            elif kind == "update_error":
                self.update_button.configure(state="normal")
                self.status_var.set("Erro na atualizacao.")
                self._append_log(f"ERRO NA ATUALIZACAO: {text}")
                messagebox.showerror("Atualizacao", str(text))
            elif kind == "update_available":
                self.update_button.configure(state="normal")
                update = text
                details = f"Existe uma nova versao do Encut: v{update.version}.\n\nVersao atual: v{APP_VERSION}"
                if update.notes:
                    details += f"\n\nNotas:\n{update.notes}"
                details += "\n\nBaixar e instalar agora?"
                self._append_log(f"Atualizacao disponivel: v{update.version}")
                if messagebox.askyesno("Atualizacao disponivel", details):
                    self._start_update_install(update)
            elif kind == "update_done":
                self.update_button.configure(state="normal")
                self.status_var.set("Atualizacao instalada.")
                self._append_log(f"Atualizacao instalada: v{text}")
                messagebox.showinfo("Atualizacao instalada", f"Encut v{text} foi instalado. Feche e abra o aplicativo para usar a nova versao.")
        self.root.after(100, self._drain_events)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + os.linesep)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Corta silencios de videos grandes usando ffmpeg.")
    parser.add_argument("paths", nargs="*", help="Modo unico: entrada saida. Modo lote: videos de entrada.")
    parser.add_argument("--ffmpeg", default=default_ffmpeg_path(), help="Caminho do ffmpeg.exe")
    parser.add_argument("--threshold", type=float, default=-35.0, help="Volume considerado silencio em dB")
    parser.add_argument("--min-silence", type=float, default=0.45, help="Duracao minima do silencio em segundos")
    parser.add_argument("--padding", type=float, default=0.12, help="Margem removida antes/depois do silencio")
    parser.add_argument("--min-keep", type=float, default=0.18, help="Menor trecho com audio a manter")
    parser.add_argument("--detection-mode", choices=["speech", "silence", "video_use"], default="speech", help="Modo de deteccao: fala precisa, Video Use ou silencio tradicional")
    parser.add_argument("--ignore-ranges", default="", help="Intervalos sem corte, ex: 01:30-03:00;05:00-06:00")
    parser.add_argument("--video-use-transcript", default="", help="JSON ou pasta de transcripts Video Use/Scribe para o modo video_use")
    parser.add_argument("--mode", choices=["reencode", "copy"], default="reencode", help="Modo de exportacao")
    parser.add_argument("--batch", action="store_true", help="Processar multiplos videos de entrada")
    parser.add_argument("--output-dir", help="Pasta de saida para o modo lote")
    parser.add_argument("--suffix", default="_sem_silencio", help="Sufixo dos arquivos gerados no modo lote")
    parser.add_argument("--gui", action="store_true", help="Abrir interface grafica")
    parser.add_argument("--check-update", action="store_true", help="Verificar atualizacao pelo manifesto configurado")
    parser.add_argument("--install-update", action="store_true", help="Baixar e instalar a atualizacao se houver")
    parser.add_argument("--update-manifest", help="URL do update.json usado para verificar atualizacoes")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.check_update or args.install_update:
        manifest_url = args.update_manifest or str(load_update_config().get("manifest_url", "")).strip()
        if not manifest_url:
            print("Atualizacao nao configurada. Informe --update-manifest ou preencha update_config.json.", file=sys.stderr)
            return 2
        try:
            update = check_for_update(manifest_url)
        except Exception as exc:
            print(f"Erro ao verificar atualizacao: {exc}", file=sys.stderr)
            return 1
        if update is None:
            print(f"Encut ja esta atualizado (v{APP_VERSION}).")
            return 0
        print(f"Atualizacao disponivel: v{update.version} (atual: v{APP_VERSION})")
        if update.notes:
            print(update.notes)
        if args.install_update:
            install_update(update, log=print)
            print(f"Atualizacao instalada: v{update.version}. Reabra o Encut.")
        return 0
    if args.gui or not args.paths:
        app = SilenceCutterApp()
        app.run()
        return 0

    template = CutterOptions(
        input_path=Path(args.paths[0]),
        output_path=Path(args.output_dir or "."),
        ffmpeg_path=args.ffmpeg,
        threshold_db=args.threshold,
        min_silence=args.min_silence,
        padding=args.padding,
        min_keep=args.min_keep,
        detection_mode=args.detection_mode,
        ignore_ranges=args.ignore_ranges,
        video_use_transcript=args.video_use_transcript,
        mode=args.mode,
    )

    if args.batch:
        output_dir = Path(args.output_dir) if args.output_dir else Path(args.paths[0]).parent / "sem_silencio"
        jobs = build_batch_jobs([Path(path) for path in args.paths], output_dir, template, suffix=args.suffix)
        _, failures = cut_video_batch(jobs, log=print)
        return 1 if failures else 0

    if len(args.paths) != 2:
        print("Modo unico: informe entrada e saida. Para varios videos, use --batch.", file=sys.stderr)
        return 2

    options = clone_options(template, Path(args.paths[0]), Path(args.paths[1]))
    cut_video(options, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())







