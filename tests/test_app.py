import pytest
import sys
import types
import wave
import io
import shutil
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

import app as jarvis
import chat_history
import jarvis_launcher
import voice_output
from jarvis_launcher import LocalDesktopBridge


client = TestClient(jarvis.app)


@pytest.fixture(autouse=True)
def isolate_chat_history(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "jarvis.sqlite3"))
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voices"))
    jarvis._PROVIDER_COOLDOWNS.clear()
    jarvis._PROVIDER_RESULTS.clear()
    voice_output._LOADED_VOICES.clear()
    monkeypatch.setattr(voice_output, "_CHATTERBOX_MODEL", None)
    monkeypatch.setattr(voice_output, "_CHATTERBOX_RUNTIME_ERROR", None)
    monkeypatch.setattr(
        voice_output,
        "_CHATTERBOX_SETUP_STATE",
        {
            "state": "idle",
            "error": None,
            "downloaded_bytes": 0,
            "current_file": "",
        },
    )
    voice_output._CHATTERBOX_CANCEL_EVENT.clear()


def test_health_endpoint_is_public_and_reports_version():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers_restrict_scripts_frames_and_device_access():
    response = client.get("/api/health")
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; base-uri 'self'; connect-src 'self'; "
        "img-src 'self' data:; media-src 'self' blob:; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "microphone=(self), camera=(), geolocation=()"


def test_desktop_token_bridge_only_serves_the_dashboard_root(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "desktop-only-token")

    class Window:
        current_url = "http://127.0.0.1:8765/"

        def get_current_url(self):
            return self.current_url

    window = Window()
    bridge = LocalDesktopBridge("http://127.0.0.1:8765/")
    bridge.window = window
    assert bridge.get_access_token() == "desktop-only-token"

    window.current_url = "http://127.0.0.1:8765/?redirected=1"
    assert bridge.get_access_token() == ""

    window.current_url = "http://127.0.0.1:8765/other"
    assert bridge.get_access_token() == ""


def test_desktop_bridge_opens_only_allowlisted_windows_settings(monkeypatch):
    opened = []
    monkeypatch.setattr(
        jarvis_launcher.os,
        "startfile",
        lambda target: opened.append(target),
        raising=False,
    )

    class Window:
        def get_current_url(self):
            return "http://127.0.0.1:8765/"

    bridge = LocalDesktopBridge("http://127.0.0.1:8765/")
    bridge.window = Window()
    assert bridge.open_windows_settings("sound") == {"opened": True}
    assert opened == ["ms-settings:sound"]
    assert bridge.open_windows_settings("arbitrary")["opened"] is False
    assert opened == ["ms-settings:sound"]
    bridge.window.get_current_url = lambda: "http://127.0.0.1:8765/other"
    assert bridge.open_windows_settings("general")["opened"] is False
    assert opened == ["ms-settings:sound"]


def test_home_page_exposes_neural_voice_and_optional_push_to_talk():
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="voiceInput"' in response.text
    assert 'id="liveToggle"' in response.text
    assert 'id="corePanel" data-state="idle"' in response.text
    assert 'id="newConversation"' in response.text
    assert 'id="stopVoice"' in response.text
    assert 'id="refreshSystem"' in response.text
    assert 'data-windows-setting="sound"' in response.text
    assert "prefers-reduced-motion:reduce" in response.text
    assert "async function sendMessage(rawText)" in response.text
    assert "recognized speech is sent automatically" in response.text
    assert 'id="speakToggle"' in response.text
    assert "SpeechRecognition" in response.text
    assert "voiceSynthesisPending" in response.text
    assert "scheduleListeningResume" in response.text
    assert "await speakReply(d.reply)" in response.text
    assert "JARVIS does not request microphone permission automatically." in response.text
    assert "function speechText(text)" in response.text
    assert "const spokenText=speechText(text).slice(0,4000)" in response.text
    assert "new AbortController()" in response.text
    assert "if(requestId!==voiceRequestId)" in response.text
    assert "Offline voice audio could not be played" in response.text
    assert "/api/voice/synthesize" in response.text
    assert "Download Arabic + English voices (~127 MB)" in response.text
    assert "Chatterbox V3 model (~3.2 GB)" in response.text
    assert "Cancel model download" in response.text
    assert "Destination:" in response.text
    assert "press EXECUTE to send it" in response.text


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for dashboard lifecycle simulation")
def test_dashboard_voice_lifecycle_recovers_without_duplicate_listening():
    root = Path(__file__).resolve().parents[1]
    result = _run_node(
        str(root / "tests" / "dashboard_voice_lifecycle.mjs"),
        str(root / "static" / "index.html"),
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    assert "Dashboard voice lifecycle passed" in result.stdout


def _run_node(*arguments):
    return subprocess.run(
        ["node", *arguments],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required to verify subprocess decoding")
def test_node_subprocess_decodes_utf8_and_replaces_invalid_output():
    result = _run_node(
        "-e",
        'process.stdout.write(Buffer.from([0xD9, 0x85, 0xFF]))',
    )

    assert result.returncode == 0
    assert result.stdout == "م�"


def test_voice_output_selects_arabic_or_english_model_from_text():
    assert voice_output._language_for_text("Hello, Jarvis.") == "en"
    assert voice_output._language_for_text("مرحبا يا جارفيس") == "ar"


def test_offline_voice_synthesizes_wav_with_the_matching_local_model(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path))
    model_path, config_path = voice_output._voice_paths(voice_output.VOICES["ar"])
    model_path.write_bytes(b"x" * 1_000_001)
    config_path.write_text('{"audio":{"sample_rate":22050}}', encoding="utf-8")
    calls = []

    class FakeVoice:
        def synthesize_wav(self, text, wav_file):
            calls.append(text)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00")

    class FakePiperVoice:
        @staticmethod
        def load(path):
            assert path == str(model_path)
            return FakeVoice()

    monkeypatch.setitem(sys.modules, "piper", types.SimpleNamespace(PiperVoice=FakePiperVoice))
    voice_output._LOADED_VOICES.clear()

    audio = voice_output.synthesize_wav("مرحبا يا جارفيس")
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 22050
        assert wav_file.getnframes() == 1
    assert calls == ["مرحبا يا جارفيس"]


def test_voice_routes_require_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    assert client.get("/api/voice/status").status_code == 401
    assert client.post("/api/voice/setup").status_code == 401
    assert client.post(
        "/api/voice/chatterbox/setup",
        json={"confirmed": True},
    ).status_code == 401
    assert client.post("/api/voice/chatterbox/cancel").status_code == 401
    assert client.put("/api/voice/engine", json={"engine": "piper"}).status_code == 401
    assert client.post("/api/voice/synthesize", json={"text": "hello"}).status_code == 401


def test_voice_status_reports_safe_optional_engine_state(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")

    response = client.get(
        "/api/voice/status",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
    )

    assert response.status_code == 200
    status = response.json()
    assert status["engine"] == "piper"
    assert status["ready"] is False
    assert status["engines"]["chatterbox"]["ready"] is False
    assert status["engines"]["chatterbox"]["download_size_gb"] == 3.2
    assert status["engines"]["chatterbox"]["offline_after_download"] is True


def test_voice_setup_route_downloads_offline_models_only_on_request(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    result = {"ready": True, "voices": {}, "offline_after_download": True}
    calls = []
    monkeypatch.setattr(voice_output, "download_voice_models", lambda: calls.append(True) or result)

    response = client.post("/api/voice/setup", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    assert response.json() == result
    assert calls == [True]


def test_chatterbox_setup_route_starts_only_after_authenticated_request(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    result = {"download_state": "downloading"}
    calls = []
    monkeypatch.setattr(
        voice_output,
        "prepare_chatterbox_model",
        lambda *, confirmed: calls.append(confirmed) or result,
    )

    response = client.post(
        "/api/voice/chatterbox/setup",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json() == result
    assert calls == [True]


def test_voice_engine_route_rejects_unknown_or_unready_engine(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(
        voice_output,
        "set_voice_engine",
        lambda engine: (_ for _ in ()).throw(ValueError("Chatterbox is not ready.")),
    )

    response = client.put(
        "/api/voice/engine",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
        json={"engine": "chatterbox"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Chatterbox is not ready."


def test_voice_engine_route_persists_ready_chatterbox_selection(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": True})

    response = client.put(
        "/api/voice/engine",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
        json={"engine": "chatterbox"},
    )

    assert response.status_code == 200
    assert response.json()["engine"] == "chatterbox"
    assert response.json()["ready"] is True
    assert voice_output.selected_voice_engine() == "chatterbox"


def test_chatterbox_setup_requires_optional_dependencies(monkeypatch):
    monkeypatch.setattr(voice_output, "_chatterbox_missing_dependencies", lambda: ["chatterbox-tts"])

    with pytest.raises(FileNotFoundError, match="install_chatterbox_voice.ps1"):
        voice_output.prepare_chatterbox_model(confirmed=True)


def test_chatterbox_model_download_requires_explicit_confirmation():
    with pytest.raises(ValueError, match="Confirm the 3.2 GB download"):
        voice_output.prepare_chatterbox_model(confirmed=False)


def test_chatterbox_setup_starts_model_download_in_background(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            assert callable(target)
            assert name == "jarvis-chatterbox-download"
            assert daemon is True

        def start(self):
            started.append(True)

    monkeypatch.setattr(voice_output, "_chatterbox_missing_dependencies", lambda: [])
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": False})
    monkeypatch.setattr(voice_output, "_CHATTERBOX_SETUP_STATE", {"state": "idle", "error": None})
    monkeypatch.setattr(voice_output, "_CHATTERBOX_SETUP_THREAD", None)
    monkeypatch.setattr(voice_output.threading, "Thread", FakeThread)

    result = voice_output.prepare_chatterbox_model(confirmed=True)
    assert result["download_state"] == "downloading"
    assert started == [True]


def test_voice_synthesis_returns_local_audio_and_handles_missing_models(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(
        voice_output,
        "synthesize_wav_with_engine",
        lambda text: (b"RIFF-local-audio", "piper", False),
    )
    headers = {"Authorization": "Bearer correct-token"}

    response = client.post("/api/voice/synthesize", headers=headers, json={"text": "Hello, JARVIS."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-jarvis-voice-engine"] == "piper"
    assert response.headers["x-jarvis-voice-fallback"] == "false"
    assert response.content == b"RIFF-local-audio"

    monkeypatch.setattr(
        voice_output,
        "synthesize_wav_with_engine",
        lambda text: (_ for _ in ()).throw(
            FileNotFoundError("Piper voice files are missing.")
        ),
    )
    missing = client.post("/api/voice/synthesize", headers=headers, json={"text": "Hello"})
    assert missing.status_code == 409
    assert "Piper voice files are missing" in missing.json()["detail"]


def test_voice_synthesis_reports_piper_failure_without_crashing(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(
        voice_output,
        "synthesize_wav_with_engine",
        lambda text: (_ for _ in ()).throw(
            voice_output.VoiceSynthesisError("Piper could not synthesize the reply.")
        ),
    )

    response = client.post(
        "/api/voice/synthesize",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
        json={"text": "Hello"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Piper could not synthesize the reply."


def test_chatterbox_synthesis_uses_detected_language_and_returns_24khz_wav(monkeypatch):
    np = pytest.importorskip("numpy")
    calls = []

    class FakeTensor:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.array([-0.5, 0.0, 0.5], dtype=np.float32)

    class FakeModel:
        def generate(self, text, *, language_id):
            calls.append((text, language_id))
            return FakeTensor()

    monkeypatch.setattr(voice_output, "selected_voice_engine", lambda: "chatterbox")
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": True})
    monkeypatch.setattr(voice_output, "_load_chatterbox_model", lambda: FakeModel())

    audio = voice_output.synthesize_wav("مرحبا يا جارفيس")
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.getnframes() == 3
    assert calls == [("مرحبا يا جارفيس", "ar")]


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Hello JARVIS.", "en"),
        ("السلام عليكم يا جارفيس", "ar"),
        ("\u08a0\u08a1", "ar"),
        ("\ufb50", "ar"),
    ],
)
def test_voice_language_detection_selects_supported_arabic_and_english(text, language):
    assert voice_output._language_for_text(text) == language


def test_chatterbox_initialization_failure_uses_piper_fallback(monkeypatch):
    monkeypatch.setattr(voice_output, "selected_voice_engine", lambda: "chatterbox")
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": True})
    monkeypatch.setattr(
        voice_output,
        "_synthesize_chatterbox",
        lambda text, language: (_ for _ in ()).throw(RuntimeError("initialization failed")),
    )
    monkeypatch.setattr(
        voice_output,
        "_synthesize_piper",
        lambda text, language: b"piper-wav",
    )

    assert voice_output.synthesize_wav_with_engine("Hello") == (
        b"piper-wav",
        "piper",
        True,
    )
    assert voice_output._CHATTERBOX_RUNTIME_ERROR == "RuntimeError"


def test_chatterbox_dependency_or_model_unavailable_uses_piper_fallback(monkeypatch):
    monkeypatch.setattr(voice_output, "selected_voice_engine", lambda: "chatterbox")
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": False})
    monkeypatch.setattr(
        voice_output,
        "_synthesize_chatterbox",
        lambda text, language: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(
        voice_output,
        "_synthesize_piper",
        lambda text, language: b"piper-wav",
    )

    assert voice_output.synthesize_wav_with_engine("مرحبا") == (
        b"piper-wav",
        "piper",
        True,
    )


def test_chatterbox_and_piper_synthesis_failures_are_reported(monkeypatch):
    monkeypatch.setattr(voice_output, "selected_voice_engine", lambda: "chatterbox")
    monkeypatch.setattr(voice_output, "_chatterbox_status", lambda: {"ready": True})
    monkeypatch.setattr(
        voice_output,
        "_synthesize_chatterbox",
        lambda text, language: (_ for _ in ()).throw(RuntimeError()),
    )
    monkeypatch.setattr(
        voice_output,
        "_synthesize_piper",
        lambda text, language: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(voice_output.VoiceSynthesisError, match="Piper fallback"):
        voice_output.synthesize_wav_with_engine("Hello")


def test_piper_reports_missing_or_invalid_voice_files(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice models"))
    with pytest.raises(FileNotFoundError, match="Piper English"):
        voice_output._synthesize_piper("Hello", "en")

    model_path, config_path = voice_output._voice_paths(voice_output.VOICES["en"])
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"x" * 1_000_001)
    config_path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="configuration is invalid"):
        voice_output._synthesize_piper("Hello", "en")


def test_chatterbox_model_download_reports_progress_and_saves_to_user_voice_dir(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice models"))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILES", ("tiny.bin",))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SIZES", {"tiny.bin": 6})
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SHA256", {})
    monkeypatch.setattr(voice_output, "CHATTERBOX_DOWNLOAD_BYTES", 6)
    monkeypatch.setattr(
        voice_output,
        "_CHATTERBOX_SETUP_STATE",
        {
            "state": "downloading",
            "error": None,
            "downloaded_bytes": 0,
            "current_file": "",
        },
    )
    voice_output._CHATTERBOX_CANCEL_EVENT.clear()

    class FakeResponse:
        status_code = 200
        headers = {"content-length": "6"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            assert chunk_size == 1024 * 1024
            yield b"abc"
            assert voice_output._CHATTERBOX_SETUP_STATE["downloaded_bytes"] == 3
            yield b"def"

    monkeypatch.setattr(voice_output.httpx, "stream", lambda *args, **kwargs: FakeResponse())

    voice_output._download_chatterbox_model()

    destination = tmp_path / "voice models" / "chatterbox-model"
    assert (destination / "tiny.bin").read_bytes() == b"abcdef"
    assert voice_output._CHATTERBOX_SETUP_STATE["state"] == "ready"
    assert voice_output._CHATTERBOX_SETUP_STATE["downloaded_bytes"] == 6


def test_chatterbox_model_download_can_be_cancelled_and_resumed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voices"))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILES", ("tiny.bin",))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SIZES", {"tiny.bin": 6})
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SHA256", {})
    monkeypatch.setattr(voice_output, "CHATTERBOX_DOWNLOAD_BYTES", 6)
    monkeypatch.setattr(
        voice_output,
        "_CHATTERBOX_SETUP_STATE",
        {
            "state": "downloading",
            "error": None,
            "downloaded_bytes": 0,
            "current_file": "",
        },
    )
    voice_output._CHATTERBOX_CANCEL_EVENT.clear()

    class FakeResponse:
        status_code = 200
        headers = {"content-length": "6"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            yield b"abc"
            voice_output.cancel_chatterbox_model_download()
            yield b"def"

    monkeypatch.setattr(voice_output.httpx, "stream", lambda *args, **kwargs: FakeResponse())
    voice_output._download_chatterbox_model()

    partial_path = (
        tmp_path / "voices" / "chatterbox-model" / "tiny.bin.part"
    )
    assert voice_output._CHATTERBOX_SETUP_STATE["state"] == "cancelled"
    assert partial_path.read_bytes() == b"abc"

    class ResumeResponse:
        status_code = 206
        headers = {"content-range": "bytes 3-5/6"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            yield b"def"

    voice_output._CHATTERBOX_CANCEL_EVENT.clear()
    monkeypatch.setattr(voice_output.httpx, "stream", lambda *args, **kwargs: ResumeResponse())
    voice_output._CHATTERBOX_SETUP_STATE = {
        "state": "downloading",
        "error": None,
        "downloaded_bytes": 3,
        "current_file": "",
    }
    voice_output._download_chatterbox_model()

    destination = tmp_path / "voices" / "chatterbox-model" / "tiny.bin"
    assert destination.read_bytes() == b"abcdef"
    assert voice_output._CHATTERBOX_SETUP_STATE["state"] == "ready"


def test_chatterbox_model_download_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voices"))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILES", ("tiny.bin",))
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SIZES", {"tiny.bin": 6})
    monkeypatch.setattr(voice_output, "CHATTERBOX_FILE_SHA256", {})
    monkeypatch.setattr(voice_output, "CHATTERBOX_DOWNLOAD_BYTES", 6)
    monkeypatch.setattr(
        voice_output,
        "_CHATTERBOX_SETUP_STATE",
        {
            "state": "downloading",
            "error": None,
            "downloaded_bytes": 0,
            "current_file": "",
        },
    )
    voice_output._CHATTERBOX_CANCEL_EVENT.clear()

    class FailedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            raise OSError("network unavailable")

    monkeypatch.setattr(voice_output.httpx, "stream", lambda *args, **kwargs: FailedResponse())

    voice_output._download_chatterbox_model()

    assert voice_output._CHATTERBOX_SETUP_STATE["state"] == "failed"
    assert "download failed" in voice_output._CHATTERBOX_SETUP_STATE["error"]


def test_status_requires_configured_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "")
    response = client.get("/api/status")
    assert response.status_code == 503


def test_status_rejects_wrong_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/status", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_status_accepts_correct_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = client.get("/api/status", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_status_distinguishes_configured_provider_from_verified_connection(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openai")
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "test-model")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "never-return-this-key" if provider == "openai" else None)

    response = client.get("/api/status", headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["provider_verified"] is False
    assert payload["available_providers"] == ["openai"]
    assert payload["provider_statuses"][0]["status"] == "configured"
    assert payload["provider_statuses"][0]["last_verified_at"] is None
    assert "never-return-this-key" not in response.text


def test_chat_rejects_missing_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "   "},
    )
    assert response.status_code == 422


def test_chat_requires_api_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "hello"},
    )
    assert response.status_code == 503


def test_chat_history_requires_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    assert client.get("/api/chat/history").status_code == 401
    assert client.delete("/api/chat/history").status_code == 401


def test_chat_history_persists_exchanges_supplies_context_and_can_be_cleared(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openai")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "test-key" if provider == "openai" else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "test-model")
    jarvis._PROVIDER_COOLDOWNS.clear()
    calls = []

    def fake_call(provider, model, api_key, instructions, history):
        calls.append(history)
        return "First reply." if len(calls) == 1 else "Second reply."

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    headers = {"Authorization": "Bearer correct-token"}
    first = client.post("/api/chat", headers=headers, json={"message": "First question."})
    assert first.status_code == 200
    assert first.json()["history_saved"] is True

    second = client.post("/api/chat", headers=headers, json={"message": "Follow-up question."})
    assert second.status_code == 200
    assert calls[1] == [
        {"role": "user", "content": "First question."},
        {"role": "assistant", "content": "First reply."},
        {"role": "user", "content": "Follow-up question."},
    ]

    history_response = client.get("/api/chat/history", headers=headers)
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["count"] == 4
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant", "user", "assistant"]

    cleared = client.delete("/api/chat/history", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json() == {"cleared": 4, "count": 0}
    assert client.get("/api/chat/history", headers=headers).json()["messages"] == []


def test_chat_history_retains_only_the_most_recent_500_messages():
    for index in range(251):
        chat_history.save_exchange(f"Question {index}", f"Reply {index}")

    messages = chat_history.load_messages()
    assert len(messages) == 500
    assert messages[0]["content"] == "Question 1"
    assert messages[-1]["content"] == "Reply 250"


def test_memory_center_can_save_search_and_delete_exact_memory(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    headers = {"Authorization": f"Bearer {jarvis.APP_TOKEN}"}

    created = client.post(
        "/api/memories",
        headers=headers,
        json={"content": "I prefer concise replies.", "category": "preferences"},
    )
    assert created.status_code == 200
    memory_id = created.json()["memory"]["id"]

    updated = client.put(
        f"/api/memories/{memory_id}",
        headers=headers,
        json={"content": "I prefer concise replies.", "category": "preferences"},
    )
    assert updated.status_code == 200
    assert updated.json()["memory"]["id"] == memory_id

    exported = client.get("/api/memories/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["memories"][0]["id"] == memory_id

    found = client.get("/api/memories", headers=headers, params={"query": "concise"})
    assert found.status_code == 200
    assert found.json()["count"] == 1
    assert found.json()["memories"][0]["id"] == memory_id

    deleted = client.delete(f"/api/memories/{memory_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["forgotten"]["id"] == memory_id
    assert client.get("/api/memories", headers=headers).json()["total"] == 0


def test_memory_center_requires_authentication_and_rejects_secret_values(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    assert client.get("/api/memories").status_code == 401
    response = client.post(
        "/api/memories",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
        json={"content": "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"},
    )
    assert response.status_code == 422
    assert "will not save secrets" in response.json()["detail"]


def test_arabic_chat_request_passes_explicit_arabic_reply_guidance_to_provider(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openai")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "test-key" if provider == "openai" else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "test-model")
    jarvis._PROVIDER_COOLDOWNS.clear()
    captured = {}

    def fake_call(provider, model, api_key, instructions, history):
        captured["instructions"] = instructions
        return "مرحبا"

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "مرحبا، جاوبني بالدارجة من فضلك"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "مرحبا"
    assert "answer in Arabic script" in captured["instructions"]
    assert "natural Moroccan Darija" in captured["instructions"]
    assert "do not switch to English unless asked" in captured["instructions"]
    assert "local Piper neural voices" in captured["instructions"]
    assert "not dedicated Moroccan Darija voices" in captured["instructions"]


def test_system_metrics_requires_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/system")
    assert response.status_code == 401


def test_system_metrics_returns_expected_fields_with_valid_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/system", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "uptime",
        "network_connected",
        "battery_percent",
        "battery_plugged",
    }


def test_system_metrics_include_only_bounded_network_and_battery_status(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    fake_psutil = types.SimpleNamespace(
        virtual_memory=lambda: types.SimpleNamespace(percent=35),
        disk_usage=lambda _path: types.SimpleNamespace(percent=41),
        boot_time=lambda: 0,
        cpu_percent=lambda interval: 12,
        net_if_stats=lambda: {
            "loopback": types.SimpleNamespace(isup=True),
            "Ethernet": types.SimpleNamespace(isup=True),
            "Wi-Fi": types.SimpleNamespace(isup=False),
        },
        sensors_battery=lambda: types.SimpleNamespace(percent=77.4, power_plugged=False),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    response = client.get("/api/system", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["network_connected"] is True
    assert payload["battery_percent"] == 77
    assert payload["battery_plugged"] is False



def test_logs_endpoint_requires_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/logs")
    assert response.status_code == 401


def test_logs_endpoint_returns_safe_diagnostic_entries(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    jarvis._LOGS.clear()
    jarvis.record_event("ERROR", "rate_limit", "Provider usage limit reached.", "Check usage and retry.")
    response = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["category"] == "rate_limit"
    assert "action" in payload["entries"][0]
    assert "content" not in payload["entries"][0]
    assert "api_key" not in payload["entries"][0]


def test_clear_logs_requires_access_token_and_clears_events(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    jarvis._LOGS.clear()
    jarvis.record_event("INFO", "request", "Test event.")
    response = client.delete("/api/logs", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    assert response.json()["cleared"] == 1
    # The clear operation leaves a single audit event confirming that the user cleared logs.
    assert client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).json()["count"] == 1


def test_rate_limit_error_has_actionable_safe_diagnostic():
    error_type = type("RateLimitError", (Exception,), {})
    category, message, action = jarvis.safe_provider_error(error_type())
    assert category == "rate_limit"
    assert "quota" in message.lower()
    assert "billing" in action.lower()



def test_provider_settings_requires_authentication(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    assert client.get("/api/providers").status_code == 401
    assert client.post("/api/providers/test", json={}).status_code == 401


def test_provider_list_is_safe_and_includes_requested_providers(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/providers", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["providers"]}
    assert {"openai", "claude", "gemini", "openrouter"} <= ids
    assert "grok" not in ids
    assert "api_key" not in payload
    assert "key" not in payload


def test_provider_credential_removal_is_authenticated_and_does_not_return_secret(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    removed = []
    monkeypatch.setattr(jarvis, "credential_delete", lambda name: removed.append(name))
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: None)

    response = client.delete(
        "/api/providers/openai/credential",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json() == {"removed": True, "provider": "openai", "key_configured": False}
    assert removed == ["OPENAI_API_KEY"]
    assert client.delete("/api/providers/openai/credential").status_code == 401


def test_provider_credential_removal_rejects_environment_managed_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(
        jarvis,
        "credential_delete",
        lambda name: (_ for _ in ()).throw(RuntimeError("environment managed")),
    )

    response = client.delete(
        "/api/providers/openai/credential",
        headers={"Authorization": f"Bearer {jarvis.APP_TOKEN}"},
    )

    assert response.status_code == 409
    assert "environment variable" in response.json()["detail"]


def test_save_provider_settings_never_returns_api_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    store = {}
    monkeypatch.setattr(jarvis, "credential_set", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(jarvis, "credential_get", lambda name: store.get(name) or ( "test-key" if name == "GEMINI_API_KEY" else None))
    response = client.post(
        "/api/providers",
        headers={"Authorization": "Bearer correct-token"},
        json={"provider": "gemini", "model": "gemini-2.5-flash", "api_key": "do-not-return-this"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gemini"
    assert payload["key_configured"] is True
    assert "do-not-return-this" not in response.text
    assert store["GEMINI_API_KEY"] == "do-not-return-this"


def test_unknown_and_removed_grok_provider_are_rejected(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post(
        "/api/providers",
        headers={"Authorization": "Bearer correct-token"},
        json={"provider": "unknown", "model": "model-x", "api_key": "secret"},
    )
    assert response.status_code == 422
    grok_response = client.post(
        "/api/providers",
        headers={"Authorization": "Bearer correct-token"},
        json={"provider": "grok", "model": "grok-4.6", "api_key": "unused"},
    )
    assert grok_response.status_code == 422


def test_provider_test_uses_configured_provider_without_logging_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openrouter")
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "openrouter-test-model")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "never-log-this-secret")

    class FakeUsage:
        total_tokens = 3

    class FakeMessage:
        content = "OK"

    class FakeChoice:
        message = FakeMessage()

    class FakeResult:
        choices = [FakeChoice()]
        usage = FakeUsage()

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "openrouter-test-model"
            return FakeResult()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "never-log-this-secret"
            assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
            self.chat = FakeChat()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(jarvis, "OpenAI", FakeClient)
    jarvis._LOGS.clear()
    response = client.post("/api/providers/test", headers={"Authorization": "Bearer correct-token"}, json={})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    logs = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text
    assert "never-log-this-secret" not in logs



def test_claude_provider_test_uses_native_anthropic_messages_api(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "claude-sonnet-4-6")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "claude-test-secret")
    calls = []

    class FakeResponse:
        is_error = False
        def json(self):
            return {"content": [{"type": "text", "text": "OK"}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(jarvis.provider_manager.httpx, "post", fake_post)
    jarvis._LOGS.clear()
    response = client.post("/api/providers/test", headers={"Authorization": "Bearer correct-token"}, json={})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert calls[0][0] == "https://api.anthropic.com/v1/messages"
    assert calls[0][1]["headers"]["x-api-key"] == "claude-test-secret"
    assert calls[0][1]["headers"]["anthropic-version"] == "2023-06-01"
    assert calls[0][1]["json"]["model"] == "claude-sonnet-4-6"
    assert calls[0][1]["json"]["messages"] == [
        {"role": "user", "content": "Reply with OK only."}
    ]
    assert "claude-test-secret" not in client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text


def test_bad_request_from_one_provider_fails_over_to_next_provider(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"claude", "openrouter"} else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "model-" + (provider or "claude"))
    jarvis._PROVIDER_COOLDOWNS.clear()
    calls = []

    def fake_call(provider, model, api_key, instructions, history):
        calls.append(provider)
        if provider == "claude":
            raise jarvis.ProviderHTTPError(400, "invalid_request_error")
        return "Recovered using OpenRouter."

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    response = client.post("/api/chat", headers={"Authorization": "Bearer correct-token"}, json={"message": "hello", "history": []})
    assert response.status_code == 200
    assert response.json()["reply"] == "Recovered using OpenRouter."
    assert calls == ["claude", "openrouter"]
    assert "provider_failover" in client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text


def test_rate_limit_fails_over_to_next_configured_provider(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openai")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"openai", "claude"} else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "model-" + (provider or "openai"))
    jarvis._PROVIDER_COOLDOWNS.clear()
    calls = []

    class RateLimitError(Exception):
        code = "rate_limit_exceeded"

    def fake_call(provider, model, api_key, instructions, history):
        calls.append(provider)
        if provider == "openai":
            raise RateLimitError("private upstream body must not be logged")
        return "Recovered using Claude."

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "hello", "history": []},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "Recovered using Claude."
    assert calls == ["openai", "claude"]
    logs = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text
    assert "provider_failover" in logs
    assert "private upstream body" not in logs
    assert "openai" in jarvis._PROVIDER_COOLDOWNS


def test_provider_in_cooldown_is_skipped_and_returns_after_expiry(monkeypatch):
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"openai", "claude"} else None)
    clock = {"now": 100.0}
    monkeypatch.setattr(jarvis.time, "monotonic", lambda: clock["now"])
    with jarvis._FAILOVER_LOCK:
        jarvis._PROVIDER_COOLDOWNS.clear()
        jarvis._PROVIDER_COOLDOWNS["openai"] = 150.0
    assert "openai" not in jarvis._available_provider_order("openai")
    clock["now"] = 151.0
    assert "openai" in jarvis._available_provider_order("claude")
    with jarvis._FAILOVER_LOCK:
        jarvis._PROVIDER_COOLDOWNS.clear()
