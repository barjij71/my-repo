from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser


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
        required_routes = {"/", "/api/health", "/api/status", "/api/system", "/api/chat"}
        if not required_routes.issubset(route_paths):
            print("JARVIS package self-test failed: expected API routes are missing.")
            return 3
        required_tools = {"open_app", "analyze_suspicious_file", "scan_with_clamav", "save_memory", "search_memories", "forget_memory"}
        available_tools = {item.get("name") for item in tool_schemas()}
        if not required_tools.issubset(available_tools):
            print("JARVIS package self-test failed: expected local tools are missing.")
            return 3
        print("JARVIS package self-test passed: imports, static UI, API routes, and required tools are available.")
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
    print("Paste the local access token shown above into the browser page. Keep the token private.")
    webbrowser.open(url, new=2)
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nStopping JARVIS...")
        server.should_exit = True
        thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
