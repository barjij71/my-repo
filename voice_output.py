from __future__ import annotations

import gc
import hashlib
import importlib.util
import io
import json
import logging
import os
import shutil
import sys
import threading
import wave
from pathlib import Path
from urllib.parse import quote

import httpx

from memory_store import database_path

MODEL_REVISION = "v1.0.0"
MODEL_LIMIT = 100 * 1024 * 1024
CHATTERBOX_REPO = "ResembleAI/chatterbox"
CHATTERBOX_REVISION = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
CHATTERBOX_FILES = (
    "ve.pt",
    "t3_mtl23ls_v3.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
)
CHATTERBOX_DOWNLOAD_BYTES = 3_208_951_924
CHATTERBOX_FILE_SIZES = {
    "ve.pt": 5_698_626,
    "t3_mtl23ls_v3.safetensors": 2_143_989_928,
    "s3gen.pt": 1_057_165_844,
    "grapheme_mtl_merged_expanded_v1.json": 69_989,
    "conds.pt": 107_374,
    "Cangjie5_TC.json": 1_920_163,
}
CHATTERBOX_FILE_SHA256 = {
    "ve.pt": "4b16d836bc598509860f6fa068165a8bb5e9ac84f05582dfcf278a5a372879f1",
    "t3_mtl23ls_v3.safetensors": "5abca8321ede76f8e61f1cc0d19aea6c946b28871017ce8726f8a69203f05953",
    "s3gen.pt": "9b9ff07e60b20c136e2b1b3d7563a24604e8d2c4c267888d1ee929dd0151d2a3",
    "conds.pt": "6552d70568833628ba019c6b03459e77fe71ca197d5c560cef9411bee9d87f4e",
}
CHATTERBOX_MODEL_DIRECTORY = "chatterbox-model"
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_CHATTERBOX_DISK_RESERVE_BYTES = 512 * 1024 * 1024
VOICES = {
    "en": {
        "id": "en_US-lessac-medium",
        "label": "English (US)",
        "path": "en/en_US/lessac/medium",
        "license": "See the voice model card and its linked dataset license.",
    },
    "ar": {
        "id": "ar_JO-kareem-medium",
        "label": "Arabic",
        "path": "ar/ar_JO/kareem/medium",
        "license": "See the voice model card for its dataset license.",
    },
}
_VOICE_LOCK = threading.RLock()
_LOADED_VOICES: dict[str, object] = {}
_CHATTERBOX_MODEL: object | None = None
_CHATTERBOX_SETUP_LOCK = threading.Lock()
_CHATTERBOX_SETUP_STATE = {
    "state": "idle",
    "error": None,
    "downloaded_bytes": 0,
    "current_file": "",
}
_CHATTERBOX_SETUP_THREAD: threading.Thread | None = None
_CHATTERBOX_CANCEL_EVENT = threading.Event()
_CHATTERBOX_RUNTIME_ERROR: str | None = None
_LOGGER = logging.getLogger(__name__)


def voice_directory() -> Path:
    override = os.environ.get("JARVIS_VOICE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return database_path().parent / "voices"


def _voice_paths(voice: dict[str, str]) -> tuple[Path, Path]:
    directory = voice_directory()
    stem = voice["id"]
    return directory / f"{stem}.onnx", directory / f"{stem}.onnx.json"


def _chatterbox_cache_dir() -> Path:
    return voice_directory() / CHATTERBOX_MODEL_DIRECTORY


def _legacy_chatterbox_cache_dir() -> Path:
    return (
        voice_directory()
        / "chatterbox-cache"
        / f"models--{CHATTERBOX_REPO.replace('/', '--')}"
        / "snapshots"
        / CHATTERBOX_REVISION
    )


def _is_complete_chatterbox_directory(directory: Path) -> bool:
    try:
        return all(
            (directory / filename).is_file()
            and (directory / filename).stat().st_size == CHATTERBOX_FILE_SIZES[filename]
            for filename in CHATTERBOX_FILES
        )
    except OSError:
        return False


def _chatterbox_model_directory() -> Path:
    current = _chatterbox_cache_dir()
    if _is_complete_chatterbox_directory(current):
        return current
    legacy = _legacy_chatterbox_cache_dir()
    return legacy if _is_complete_chatterbox_directory(legacy) else current


def _chatterbox_missing_dependencies() -> list[str]:
    modules = {
        "chatterbox": "chatterbox-tts",
        "torch": "torch",
        "torchaudio": "torchaudio",
        "librosa": "librosa",
        "safetensors": "safetensors",
        "transformers": "transformers",
        "diffusers": "diffusers",
        "perth": "resemble-perth",
        "s3tokenizer": "s3tokenizer",
        "conformer": "conformer",
        "huggingface_hub": "huggingface-hub",
        "numpy": "numpy",
        "spacy_pkuseg": "spacy-pkuseg",
        "pykakasi": "pykakasi",
        "pyloudnorm": "pyloudnorm",
        "omegaconf": "omegaconf",
    }
    return [
        package
        for module, package in modules.items()
        if importlib.util.find_spec(module) is None
    ]


def _chatterbox_cached_files() -> list[bool]:
    return [True] * len(CHATTERBOX_FILES) if _is_complete_chatterbox_directory(
        _chatterbox_model_directory()
    ) else [False] * len(CHATTERBOX_FILES)


def _chatterbox_status() -> dict[str, object]:
    missing_dependencies = _chatterbox_missing_dependencies()
    cached = [False] * len(CHATTERBOX_FILES)
    try:
        cached = _chatterbox_cached_files()
    except OSError:
        pass

    with _CHATTERBOX_SETUP_LOCK:
        setup_state = dict(_CHATTERBOX_SETUP_STATE)
    download_state = setup_state["state"]
    setup_error = setup_state["error"]

    downloaded = all(cached)
    if downloaded:
        download_state = "ready"
        setup_error = None
    elif missing_dependencies:
        download_state = "dependencies_missing"

    model_directory = _chatterbox_model_directory()
    downloaded_bytes = min(
        CHATTERBOX_DOWNLOAD_BYTES,
        max(0, int(setup_state.get("downloaded_bytes") or 0)),
    )
    if downloaded:
        downloaded_bytes = CHATTERBOX_DOWNLOAD_BYTES
    return {
        "ready": not missing_dependencies and downloaded,
        "dependencies_installed": not missing_dependencies,
        "missing_dependencies": missing_dependencies,
        "model_downloaded": downloaded,
        "download_state": download_state,
        "setup_error": setup_error,
        "download_size_gb": round(CHATTERBOX_DOWNLOAD_BYTES / 1_000_000_000, 1),
        "downloaded_bytes": downloaded_bytes,
        "total_bytes": CHATTERBOX_DOWNLOAD_BYTES,
        "progress_percent": round(downloaded_bytes * 100 / CHATTERBOX_DOWNLOAD_BYTES),
        "current_file": str(setup_state.get("current_file") or ""),
        "can_cancel_download": download_state == "downloading",
        "model_directory": str(model_directory),
        "license": "MIT",
        "watermarked": True,
        "offline_after_download": True,
        "languages": ["Arabic", "English"],
        "source_install_supported": not getattr(sys, "frozen", False),
    }


def voice_status() -> dict[str, object]:
    statuses = {}
    for language, voice in VOICES.items():
        model_path, config_path = _voice_paths(voice)
        installed = (
            model_path.is_file()
            and model_path.stat().st_size > 1_000_000
            and config_path.is_file()
            and config_path.stat().st_size > 0
        )
        statuses[language] = {
            "id": voice["id"],
            "label": voice["label"],
            "installed": installed,
            "license": voice["license"],
        }
    chatterbox = _chatterbox_status()
    engine = selected_voice_engine()
    piper_ready = all(item["installed"] for item in statuses.values())
    chatterbox["fallback_ready"] = piper_ready
    return {
        "ready": (
            piper_ready
            if engine == "piper"
            else bool(chatterbox["ready"]) or piper_ready
        ),
        "selected_engine_ready": piper_ready if engine == "piper" else bool(chatterbox["ready"]),
        "engine": engine,
        "engines": {
            "piper": {
                "label": "Piper (offline)",
                "ready": piper_ready,
                "license": "See each voice model card.",
            },
            "chatterbox": {
                "label": "Chatterbox Multilingual V3",
                **chatterbox,
            },
        },
        "voices": statuses,
        "download_size_mb": 127,
        "offline_after_download": True,
        "chatterbox_runtime_error": _CHATTERBOX_RUNTIME_ERROR,
    }


def selected_voice_engine() -> str:
    settings_path = voice_directory() / "settings.json"
    if not settings_path.is_file():
        return "piper"
    with settings_path.open("r", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)
    if not isinstance(settings, dict) or settings.get("engine") not in {"piper", "chatterbox"}:
        raise ValueError("Saved voice settings are invalid.")
    return settings["engine"]


def set_voice_engine(engine: str) -> dict[str, object]:
    global _CHATTERBOX_MODEL
    if engine not in {"piper", "chatterbox"}:
        raise ValueError("Unsupported voice engine.")
    if engine == "chatterbox" and not _chatterbox_status()["ready"]:
        raise ValueError("Chatterbox dependencies and the model must be installed before selecting it.")

    with _VOICE_LOCK:
        directory = voice_directory()
        directory.mkdir(parents=True, exist_ok=True)
        settings_path = directory / "settings.json"
        temporary_path = settings_path.with_suffix(".json.part")
        temporary_path.write_text(json.dumps({"engine": engine}), encoding="utf-8")
        temporary_path.replace(settings_path)
        if engine == "piper" and _CHATTERBOX_MODEL is not None:
            _CHATTERBOX_MODEL = None
            gc.collect()
    return voice_status()


class _DownloadCancelled(Exception):
    pass


def _set_chatterbox_progress(
    downloaded_bytes: int,
    current_file: str,
) -> None:
    with _CHATTERBOX_SETUP_LOCK:
        _CHATTERBOX_SETUP_STATE.update(
            downloaded_bytes=min(CHATTERBOX_DOWNLOAD_BYTES, max(0, downloaded_bytes)),
            current_file=current_file,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_chatterbox_file(filename: str, downloaded_before: int) -> int:
    if _CHATTERBOX_CANCEL_EVENT.is_set():
        raise _DownloadCancelled

    directory = _chatterbox_cache_dir()
    destination = directory / filename
    partial_path = destination.with_name(destination.name + ".part")
    expected_size = CHATTERBOX_FILE_SIZES[filename]
    expected_hash = CHATTERBOX_FILE_SHA256.get(filename)
    if destination.is_file():
        if destination.stat().st_size == expected_size:
            return downloaded_before
        downloaded_before = max(0, downloaded_before - destination.stat().st_size)
        destination.unlink()

    offset = partial_path.stat().st_size if partial_path.is_file() else 0
    if offset == expected_size:
        if not expected_hash or _sha256_file(partial_path) == expected_hash:
            partial_path.replace(destination)
            return downloaded_before
        downloaded_before -= offset
        partial_path.unlink(missing_ok=True)
        offset = 0
    elif offset > expected_size:
        downloaded_before -= offset
        partial_path.unlink(missing_ok=True)
        offset = 0
    if downloaded_before > CHATTERBOX_DOWNLOAD_BYTES:
        raise OSError("The Chatterbox download exceeded its expected size.")
    completed_before = downloaded_before - offset

    url = (
        f"https://huggingface.co/{CHATTERBOX_REPO}/resolve/"
        f"{CHATTERBOX_REVISION}/{quote(filename)}"
    )
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with httpx.stream(
        "GET",
        url,
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=20.0, read=90.0, write=20.0, pool=20.0),
    ) as response:
        if response.status_code == 416 and offset:
            partial_path.unlink(missing_ok=True)
            return _download_chatterbox_file(filename, downloaded_before - offset)
        response.raise_for_status()

        if offset and response.status_code != 206:
            completed_before = downloaded_before - offset
            offset = 0
        elif offset:
            content_range = response.headers.get("content-range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise OSError("The Chatterbox download could not safely resume.")

        mode = "ab" if offset else "wb"
        received = 0
        digest = hashlib.sha256()
        if offset:
            with partial_path.open("rb") as partial:
                for existing_chunk in iter(
                    lambda: partial.read(_DOWNLOAD_CHUNK_BYTES),
                    b"",
                ):
                    digest.update(existing_chunk)
        with partial_path.open(mode) as output:
            for chunk in response.iter_bytes(_DOWNLOAD_CHUNK_BYTES):
                if _CHATTERBOX_CANCEL_EVENT.is_set():
                    raise _DownloadCancelled
                if not chunk:
                    continue
                received += len(chunk)
                if completed_before + offset + received > CHATTERBOX_DOWNLOAD_BYTES:
                    raise OSError("The Chatterbox download exceeded its expected size.")
                output.write(chunk)
                digest.update(chunk)
                _set_chatterbox_progress(
                    completed_before + offset + received,
                    filename,
                )

    if partial_path.stat().st_size != expected_size:
        raise OSError(f"The Chatterbox download has an invalid size: {filename}.")
    if expected_hash and digest.hexdigest() != expected_hash:
        raise OSError(f"The Chatterbox download failed its SHA-256 check: {filename}.")
    partial_path.replace(destination)
    return completed_before + destination.stat().st_size


def _download_chatterbox_model() -> None:
    global _CHATTERBOX_SETUP_STATE
    try:
        directory = _chatterbox_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(directory.parent)
        if disk.free < CHATTERBOX_DOWNLOAD_BYTES + _CHATTERBOX_DISK_RESERVE_BYTES:
            raise OSError(
                "Not enough free disk space. Chatterbox needs about 3.2 GB plus at least 512 MB free."
            )
        downloaded = sum(
            (directory / name).stat().st_size
            for name in CHATTERBOX_FILES
            if (directory / name).is_file()
        ) + sum(
            (directory / (name + ".part")).stat().st_size
            for name in CHATTERBOX_FILES
            if (directory / (name + ".part")).is_file()
        )
        _set_chatterbox_progress(downloaded, "")
        for filename in CHATTERBOX_FILES:
            if _CHATTERBOX_CANCEL_EVENT.is_set():
                raise _DownloadCancelled
            downloaded = _download_chatterbox_file(filename, downloaded)
        if not all(_chatterbox_cached_files()):
            raise OSError("The Chatterbox download is incomplete.")
    except _DownloadCancelled:
        with _CHATTERBOX_SETUP_LOCK:
            _CHATTERBOX_SETUP_STATE = {
                "state": "cancelled",
                "error": "Download cancelled. Partial files were kept so a retry can resume.",
                "downloaded_bytes": int(_CHATTERBOX_SETUP_STATE.get("downloaded_bytes") or 0),
                "current_file": "",
            }
    except Exception:
        _LOGGER.exception("Chatterbox model download failed.")
        with _CHATTERBOX_SETUP_LOCK:
            _CHATTERBOX_SETUP_STATE = {
                "state": "failed",
                "error": "The Chatterbox model download failed. Check internet access, disk space, and the reported destination.",
                "downloaded_bytes": int(_CHATTERBOX_SETUP_STATE.get("downloaded_bytes") or 0),
                "current_file": "",
            }
        return

    with _CHATTERBOX_SETUP_LOCK:
        if _CHATTERBOX_SETUP_STATE.get("state") != "cancelled":
            _CHATTERBOX_SETUP_STATE = {
                "state": "ready",
                "error": None,
                "downloaded_bytes": CHATTERBOX_DOWNLOAD_BYTES,
                "current_file": "",
            }


def prepare_chatterbox_model(*, confirmed: bool) -> dict[str, object]:
    global _CHATTERBOX_SETUP_STATE, _CHATTERBOX_SETUP_THREAD
    if confirmed is not True:
        raise ValueError("Confirm the 3.2 GB download before starting Chatterbox setup.")
    missing_dependencies = _chatterbox_missing_dependencies()
    if missing_dependencies:
        raise FileNotFoundError(
            "Install the optional Chatterbox CPU dependencies with install_chatterbox_voice.ps1 first."
        )
    status = _chatterbox_status()
    if status["ready"]:
        return status

    with _CHATTERBOX_SETUP_LOCK:
        if _CHATTERBOX_SETUP_STATE["state"] == "downloading":
            return {
                **status,
                "download_state": "downloading",
                "setup_error": None,
            }
        _CHATTERBOX_CANCEL_EVENT.clear()
        _CHATTERBOX_SETUP_STATE = {
            "state": "downloading",
            "error": None,
            "downloaded_bytes": int(status.get("downloaded_bytes") or 0),
            "current_file": "",
        }
        _CHATTERBOX_SETUP_THREAD = threading.Thread(
            target=_download_chatterbox_model,
            name="jarvis-chatterbox-download",
            daemon=True,
        )
        _CHATTERBOX_SETUP_THREAD.start()
    return {
        **status,
        "download_state": "downloading",
        "setup_error": None,
        "can_cancel_download": True,
    }


def cancel_chatterbox_model_download() -> dict[str, object]:
    with _CHATTERBOX_SETUP_LOCK:
        downloading = _CHATTERBOX_SETUP_STATE["state"] == "downloading"
        if downloading:
            _CHATTERBOX_CANCEL_EVENT.set()
    if not downloading:
        return _chatterbox_status()
    return {
        **_chatterbox_status(),
        "download_state": "cancelling",
        "setup_error": "Stopping the download. Any partial file is retained for retry.",
        "can_cancel_download": False,
    }


def _download_file(url: str, destination: Path, minimum_size: int) -> None:
    if destination.is_file() and destination.stat().st_size >= minimum_size:
        return
    temporary = destination.with_name(destination.name + ".part")
    total = 0
    try:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0),
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MODEL_LIMIT:
                raise ValueError("Voice model download exceeded the size limit.")
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MODEL_LIMIT:
                        raise ValueError("Voice model download exceeded the size limit.")
                    output.write(chunk)
        if total < minimum_size:
            raise ValueError("Voice model download was incomplete.")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_config(config_path: Path) -> None:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict) or not isinstance(config.get("audio"), dict):
        raise ValueError("Downloaded voice configuration is invalid.")


def download_voice_models() -> dict[str, object]:
    directory = voice_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with _VOICE_LOCK:
        for voice in VOICES.values():
            model_path, config_path = _voice_paths(voice)
            base_url = (
                "https://huggingface.co/rhasspy/piper-voices/resolve/"
                f"{MODEL_REVISION}/{voice['path']}/{voice['id']}.onnx"
            )
            _download_file(base_url, model_path, 1_000_000)
            if config_path.is_file():
                try:
                    _validate_config(config_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    config_path.unlink()
            _download_file(base_url + ".json", config_path, 100)
            _validate_config(config_path)
        _LOADED_VOICES.clear()
    return voice_status()


def _language_for_text(text: str) -> str:
    if any(
        0x0600 <= ord(character) <= 0x06FF
        or 0x0750 <= ord(character) <= 0x077F
        or 0x0870 <= ord(character) <= 0x089F
        or 0x08A0 <= ord(character) <= 0x08FF
        or 0xFB50 <= ord(character) <= 0xFDFF
        or 0xFE70 <= ord(character) <= 0xFEFF
        or 0x10EC0 <= ord(character) <= 0x10EFF
        for character in text
    ):
        return "ar"
    return "en"


def synthesize_wav(text: str) -> bytes:
    return synthesize_wav_with_engine(text)[0]


def synthesize_wav_with_engine(text: str) -> tuple[bytes, str, bool]:
    global _CHATTERBOX_RUNTIME_ERROR
    language = _language_for_text(text)
    with _VOICE_LOCK:
        if selected_voice_engine() == "chatterbox":
            try:
                audio = _synthesize_chatterbox(text, language)
                _CHATTERBOX_RUNTIME_ERROR = None
                return audio, "chatterbox", False
            except Exception as exc:
                _CHATTERBOX_RUNTIME_ERROR = type(exc).__name__
                _LOGGER.warning(
                    "Chatterbox failed for %s; trying local Piper fallback (%s).",
                    language,
                    type(exc).__name__,
                    exc_info=True,
                )
                try:
                    return _synthesize_piper(text, language), "piper", True
                except Exception as fallback_exc:
                    raise VoiceSynthesisError(
                        "Chatterbox failed and Piper fallback could not synthesize this reply. "
                        "Check both voice engines in Settings & Access."
                    ) from fallback_exc
        return _synthesize_piper(text, language), "piper", False


class VoiceSynthesisError(RuntimeError):
    pass


def _synthesize_piper(text: str, language: str) -> bytes:
    voice = VOICES[language]
    model_path, config_path = _voice_paths(voice)
    if (
        not model_path.is_file()
        or model_path.stat().st_size <= 1_000_000
        or not config_path.is_file()
        or config_path.stat().st_size <= 0
    ):
        raise FileNotFoundError(
            f"The Piper {voice['label']} voice files are missing or incomplete. "
            "Install the Arabic and English offline voices in Settings & Access."
        )
    try:
        _validate_config(config_path)
    except (OSError, ValueError, json.JSONDecodeError):
        raise FileNotFoundError(
            f"The Piper {voice['label']} configuration is invalid. Reinstall that voice in Settings & Access."
        ) from None
    voice_model = _LOADED_VOICES.get(language)
    if voice_model is None:
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise VoiceSynthesisError(
                "The Piper runtime is unavailable. Run .\\start.ps1 to restore the project dependencies."
            ) from exc
        try:
            voice_model = PiperVoice.load(str(model_path))
        except Exception as exc:
            raise VoiceSynthesisError(
                f"The Piper {voice['label']} model could not be loaded. Reinstall that voice in Settings & Access."
            ) from exc
        _LOADED_VOICES[language] = voice_model
    output = io.BytesIO()
    try:
        with wave.open(output, "wb") as wav_file:
            voice_model.synthesize_wav(text, wav_file)
    except Exception as exc:
        raise VoiceSynthesisError(
            f"The Piper {voice['label']} voice could not synthesize this reply."
        ) from exc
    return output.getvalue()


def _load_chatterbox_model() -> object:
    global _CHATTERBOX_MODEL
    if _CHATTERBOX_MODEL is not None:
        return _CHATTERBOX_MODEL
    status = _chatterbox_status()
    if not status["ready"]:
        raise FileNotFoundError(
            "Chatterbox is not ready. Install its optional dependencies and download the model in Settings."
        )

    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    _CHATTERBOX_MODEL = ChatterboxMultilingualTTS.from_local(
        str(_chatterbox_model_directory()),
        device=torch.device("cpu"),
        t3_model="v3",
    )
    return _CHATTERBOX_MODEL


def _synthesize_chatterbox(text: str, language: str) -> bytes:
    if not _chatterbox_status()["ready"]:
        raise FileNotFoundError(
            "Chatterbox is not ready. Install its optional dependencies and download the model in Settings."
        )

    import numpy as np

    model = _load_chatterbox_model()
    audio = model.generate(text, language_id=language)
    samples = audio.detach().cpu().numpy().reshape(-1)
    if samples.size == 0 or not np.isfinite(samples).all():
        raise ValueError("Chatterbox returned invalid audio.")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm.tobytes())
    return output.getvalue()
