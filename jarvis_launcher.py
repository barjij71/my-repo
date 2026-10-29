from __future__ import annotations

import os
import sys
import threading
import time
from urllib.parse import urlsplit


class LocalDesktopBridge:
    _WINDOWS_SETTINGS = {
        "general": "ms-settings:",
        "sound": "ms-settings:sound",
        "display": "ms-settings:display",
        "network": "ms-settings:network",
    }

    def __init__(self, expected_url: str) -> None:
        self.expected_url = expected_url
        self.window = None

    def _is_trusted_page(self) -> bool:
        if self.window is None:
            return False
        try:
            current_url = self.window.get_current_url()
        except Exception:
            return False
        expected = urlsplit(self.expected_url)
        current = urlsplit(current_url or "")
        return (
            (current.scheme, current.hostname, current.port)
            == (expected.scheme, expected.hostname, expected.port)
            and current.path in {"", "/"}
            and not current.query
            and not current.fragment
        )

    def get_access_token(self) -> str:
        if not self._is_trusted_page():
            return ""
        from app import APP_TOKEN

        return APP_TOKEN

    def open_windows_settings(self, setting: str) -> dict[str, bool | str]:
        target = self._WINDOWS_SETTINGS.get(setting) if isinstance(setting, str) else None
        if target is None or not self._is_trusted_page():
            return {
                "opened": False,
                "error": "Windows Settings shortcut unavailable or not allowed.",
            }
        open_target = getattr(os, "startfile", None)
        if open_target is None:
            return {"opened": False, "error": "Windows Settings could not be opened."}
        try:
            open_target(target)
        except OSError:
            return {"opened": False, "error": "Windows Settings could not be opened."}
        return {"opened": True}


def main() -> int:
    if os.name != "nt":
        print("The packaged JARVIS desktop launcher is for Windows 10/11.")
        return 2

    # Import lazily so a clear platform message is shown before Windows-only setup.
    import setup_credentials

    if "--self-test" in sys.argv[1:]:
        from app import app
        from pathlib import Path
        from computer_control import tool_schemas
        from piper import PiperVoice
        import webview

        # `app` is the FastAPI instance, not the Python module. In a PyInstaller
        # onedir build, bundled data normally lives under sys._MEIPASS.
        candidates = []
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir) / "static" / "index.html")
        candidates.append(Path(__file__).resolve().parent / "static" / "index.html")
        candidates.append(Path(sys.executable).resolve().parent / "static" / "index.html")
        static_index = next((path for path in candidates if path.is_file()), None)
        if static_index is None:
            print("JARVIS package self-test failed: static/index.html is missing.")
            print("Checked: " + "; ".join(str(path) for path in candidates))
            return 3
        route_paths = {getattr(route, "path", "") for route in app.routes}
        required_routes = {
            "/",
            "/api/health",
            "/api/status",
            "/api/system",
            "/api/chat",
            "/api/providers/{provider}/credential",
            "/api/memories",
            "/api/memories/export",
            "/api/memories/{memory_id}",
        }
        if not required_routes.issubset(route_paths):
            print("JARVIS package self-test failed: expected API routes are missing.")
            return 3
        required_tools = {"open_app", "analyze_suspicious_file", "scan_with_clamav", "save_memory", "search_memories", "forget_memory"}
        available_tools = {item.get("name") for item in tool_schemas()}
        if not required_tools.issubset(available_tools):
            print("JARVIS package self-test failed: expected local tools are missing.")
            return 3
        if not callable(PiperVoice.load):
            print("JARVIS package self-test failed: offline neural voice runtime is unavailable.")
            return 3
        if not callable(webview.create_window):
            print("JARVIS package self-test failed: native desktop window runtime is unavailable.")
            return 3
        print("JARVIS package self-test passed: imports, static UI, API routes, computer tools, offline voice runtime, and native desktop runtime are available.")
        return 0

    # Configure credentials BEFORE importing app: app reads JARVIS_ACCESS_TOKEN
    # from Windows Credential Manager once, at module import time.
    setup_result = setup_credentials.main()
    if setup_result != 0:
        return setup_result

    import uvicorn
    from app import app

    host = os.environ.get("JARVIS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in {"127.0.0.1", "localhost"}:
        print("For safety, the packaged launcher only supports loopback binding.")
        return 2
    try:
        port = int(os.environ.get("JARVIS_PORT", "8765"))
    except ValueError:
        print("JARVIS_PORT must be a number.")
        return 2
    if not 1024 <= port <= 65535:
        print("JARVIS_PORT must be between 1024 and 65535.")
        return 2

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="JARVIS-API", daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and thread.is_alive() and not server.started:
        time.sleep(0.2)
    if not server.started:
        print("JARVIS did not start. Check whether the local port is already in use.")
        server.should_exit = True
        thread.join(timeout=3)
        return 1

    url = f"http://127.0.0.1:{port}"
    print()
    print(f"JARVIS is ready at {url}")
    try:
        import webview

        bridge = LocalDesktopBridge(url + "/")
        window = webview.create_window(
            "JARVIS — AI Core Overview",
            url,
            width=1440,
            height=940,
            min_size=(960, 680),
            background_color="#030b14",
            text_select=True,
            js_api=bridge,
        )
        bridge.window = window
        webview.start(debug=False, private_mode=True)
    except KeyboardInterrupt:
        print("\nStopping JARVIS...")
    except Exception as exc:
        print(
            f"JARVIS desktop window could not start ({type(exc).__name__}). "
            "Install or repair Microsoft Edge WebView2 Runtime, then retry."
        )
        return 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
