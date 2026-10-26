from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import secrets
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

WORKSPACE = (Path.home() / "Documents" / "JARVISWorkspace").resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)
ALLOWED_APPS = {"notepad": ["notepad.exe"], "calculator": ["calc.exe"], "explorer": ["explorer.exe"]}
_PENDING_ACTIONS: dict[str, dict[str, str]] = {}
_PROTECTED_PROCESSES = {"system", "registry", "smss", "csrss", "wininit", "services", "lsass", "svchost", "winlogon", "explorer", "dwm", "fontdrvhost", "spoolsv", "securityhealthservice", "msmpeng", "antimalwareserviceexecutable"}
MAX_CLIPBOARD_CHARS = 20_000



def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_path(relative_path: str) -> Path:
    candidate = (WORKSPACE / relative_path).resolve()
    if candidate != WORKSPACE and WORKSPACE not in candidate.parents:
        raise ValueError("Path must remain inside the JARVISWorkspace folder.")
    return candidate


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("This action is supported on Windows only.")


def _powershell(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    _require_windows()
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, timeout=timeout, check=False,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _stage(kind: str, label: str, value: str = "") -> str:
    action_id = secrets.token_hex(4)
    _PENDING_ACTIONS[action_id] = {"kind": kind, "label": label, "value": value}
    return json.dumps({"ok": True, "status": "awaiting_confirmation", "action_id": action_id,
        "action": label, "message": "No change has been made. Explain this exact action and ask for explicit user confirmation before calling confirm_pending_action."}, ensure_ascii=False)


def tool_schemas() -> list[dict[str, Any]]:
    def s(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "function", "name": name, "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}, "strict": True}
    return [
        s("open_app", "Open Notepad, Calculator, or File Explorer.", {"app": {"type": "string", "enum": sorted(ALLOWED_APPS)}}, ["app"]),
        s("open_url", "Open an HTTP or HTTPS website in the default browser.", {"url": {"type": "string"}}, ["url"]),
        s("open_path", "Open an existing local file or folder by absolute path on any available Windows drive (C:, D:, etc). Never execute the file.", {"path": {"type": "string"}}, ["path"]),
        s("list_drives", "List available Windows drives and capacity.", {}, []),
        s("copy_to_clipboard", "Copy plain text, a command string, or a file path to the Windows clipboard; this does not execute it.", {"text": {"type": "string"}}, ["text"]),
        s("request_copy_file", "Stage copying a selected file between any accessible Windows drives using absolute source and destination paths. Never overwrite an existing destination; requires explicit confirmation.", {"source_path": {"type": "string"}, "destination_path": {"type": "string"}}, ["source_path", "destination_path"]),
        s("list_processes", "Read-only list of running processes sorted by RAM use.", {"limit": {"type": "integer"}}, ["limit"]),
        s("list_installed_apps", "List installed apps from Windows registry without uninstalling anything.", {}, []),
        s("analyze_suspicious_file", "Lightweight local static triage of one selected file without installing an antivirus. Reports SHA-256, basic file type, and suspicious strings commonly associated with remote access, persistence, or cryptomining. Findings are heuristics, not proof of malware; does not execute, delete, upload, or quarantine the file.", {"path": {"type": "string"}}, ["path"]),
        s("scan_with_clamav", "On-demand, resource-bounded ClamAV scan of one user-selected existing file or folder. Low process priority, capped file/scan sizes and file count, PUA detection enabled. Never deletes or quarantines. Does not auto-update signatures during scans.", {"path": {"type": "string"}}, ["path"]),
        s("request_quarantine_file", "Stage moving one exact suspicious user-selected file into a reversible JARVIS quarantine after explicit confirmation. Never permanently deletes files or accepts folders/system/program installation paths.", {"path": {"type": "string"}}, ["path"]),
        s("request_system_repair", "Stage DISM image repair and SFC scan; requires explicit confirmation and may need Administrator.", {}, []),
        s("request_uninstall", "Stage uninstall of one exact app name via winget. Never remove Windows/security components, drivers, or shared runtimes.", {"app_name": {"type": "string"}}, ["app_name"]),
        s("request_stop_process", "Stage a graceful close request for a user-selected process to reduce load while gaming. Never force-kill or target Windows/security processes.", {"process_name": {"type": "string"}}, ["process_name"]),
        s("confirm_pending_action", "Execute a staged disruptive action only if the latest user message explicitly confirms that exact action.", {"action_id": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["action_id", "confirmed"]),
        s("list_workspace", "List files and folders inside JARVISWorkspace.", {"relative_path": {"type": "string"}}, ["relative_path"]),
        s("read_workspace_file", "Read a UTF-8 text file inside JARVISWorkspace (maximum 200 KB).", {"relative_path": {"type": "string"}}, ["relative_path"]),
        s("write_workspace_file", "Create or replace a UTF-8 text file inside JARVISWorkspace only when explicitly requested.", {"relative_path": {"type": "string"}, "content": {"type": "string"}}, ["relative_path", "content"]),
        s("create_workspace_folder", "Create a folder inside JARVISWorkspace.", {"relative_path": {"type": "string"}}, ["relative_path"]),
    ]


def _list_drives() -> str:
    _require_windows()
    import psutil
    rows = []
    for part in psutil.disk_partitions(all=False):
        if len(part.device) < 2 or part.device[1] != ":":
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
            rows.append({"drive": part.device, "mountpoint": part.mountpoint, "total_gb": round(u.total / 1024**3, 1), "free_gb": round(u.free / 1024**3, 1)})
        except (PermissionError, OSError):
            rows.append({"drive": part.device, "mountpoint": part.mountpoint, "capacity": "unavailable"})
    return json.dumps({"ok": True, "drives": rows}, ensure_ascii=False)


def _list_processes(limit: int) -> str:
    import psutil
    limit = max(1, min(int(limit), 40))
    rows = []
    for proc in psutil.process_iter(["pid", "name", "username", "memory_info", "status"]):
        try:
            i = proc.info
            mem = i.get("memory_info")
            rows.append({"pid": i.get("pid"), "name": i.get("name") or "unknown", "user": i.get("username") or "unknown",
                         "status": i.get("status") or "unknown", "ram_mb": round(mem.rss / 1024**2, 1) if mem else 0})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    rows.sort(key=lambda x: x["ram_mb"], reverse=True)
    return json.dumps({"ok": True, "processes": rows[:limit], "note": "Read-only. Actual RAM is freed by closing appropriate apps, not by changing displayed metrics."}, ensure_ascii=False)


def _list_installed_apps() -> str:
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$paths = @('HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*')
$items = foreach ($path in $paths) { Get-ItemProperty $path | Where-Object { $_.DisplayName } | ForEach-Object { [pscustomobject]@{name=$_.DisplayName;publisher=$_.Publisher;version=$_.DisplayVersion} } }
$items | Sort-Object name -Unique | ConvertTo-Json -Depth 3 -Compress
"""
    r = _powershell(script, 30)
    if r.returncode:
        raise RuntimeError((r.stderr or "Could not read installed applications.")[:400])
    try:
        apps = json.loads(r.stdout.strip() or "[]")
    except json.JSONDecodeError:
        apps = []
    if isinstance(apps, dict):
        apps = [apps]
    return json.dumps({"ok": True, "apps": apps[:300], "note": "Inventory only; removal requires a separate explicit confirmation."}, ensure_ascii=False)


def execute_tool(name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json)
        if not isinstance(args, dict):
            raise ValueError("Arguments must be an object.")
        if name == "open_app":
            app = args["app"]
            if app not in ALLOWED_APPS:
                raise ValueError("That application is not approved.")
            _require_windows()
            subprocess.Popen(ALLOWED_APPS[app], shell=False, close_fds=True)
            return json.dumps({"ok": True, "opened": app})
        if name == "open_url":
            url = args["url"].strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Only complete http:// or https:// URLs are allowed.")
            webbrowser.open(url, new=2)
            return json.dumps({"ok": True, "opened_url": url})
        if name == "open_path":
            _require_windows()
            raw = args["path"].strip()
            path = Path(raw)
            if not path.is_absolute() or not path.exists():
                raise ValueError("Provide an existing absolute path, such as C:\\Users\\... or D:\\... .")
            if path.is_file():
                if path.suffix.casefold() in {".exe", ".com", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".vbs", ".js", ".reg", ".lnk"}:
                    raise ValueError("For safety, JARVIS will not launch executable, script, installer, registry, or shortcut files. Open the containing folder instead.")
                os.startfile(str(path))
            else:
                subprocess.Popen(["explorer.exe", str(path)], shell=False, close_fds=True)
            return json.dumps({"ok": True, "opened_path": str(path)}, ensure_ascii=False)
        if name == "list_drives":
            return _list_drives()
        if name == "copy_to_clipboard":
            value = args["text"]
            if len(value) > MAX_CLIPBOARD_CHARS:
                raise ValueError(f"Clipboard text exceeds {MAX_CLIPBOARD_CHARS} characters.")
            script = "$value = [Console]::In.ReadToEnd(); Set-Clipboard -Value $value"
            _require_windows()
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                input=value, capture_output=True, text=True, timeout=15, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode:
                raise RuntimeError((r.stderr or "Clipboard write failed.")[:300])
            return json.dumps({"ok": True, "copied_characters": len(value), "executed": False})
        if name == "request_copy_file":
            _require_windows()
            source = Path(args["source_path"].strip())
            destination = Path(args["destination_path"].strip())
            if not source.is_absolute() or not source.is_file():
                raise ValueError("Source must be an existing absolute file path.")
            if not destination.is_absolute() or not destination.name:
                raise ValueError("Destination must be an absolute file path including its file name.")
            if not destination.parent.is_dir():
                raise ValueError("Destination folder must already exist.")
            if destination.exists():
                raise ValueError("Destination already exists; JARVIS will not overwrite files.")
            return _stage("copy_file", f"Copy file '{source}' to '{destination}' without overwriting anything", json.dumps({"source": str(source), "destination": str(destination)}))
        if name == "list_processes":
            return _list_processes(args["limit"])
        if name == "list_installed_apps":
            return _list_installed_apps()
        if name == "analyze_suspicious_file":
            target = Path(args["path"].strip()).resolve()
            if not target.is_absolute() or not target.is_file():
                raise ValueError("Provide one existing absolute file path; folders are not accepted for static triage.")
            size = target.stat().st_size
            digest = _sha256_file(target)
            sample_limit = 25 * 1024 * 1024
            with target.open("rb") as stream:
                sample = stream.read(sample_limit)
            # Include common ASCII and UTF-16LE strings without executing the file.
            text_sample = sample.decode("latin-1", errors="ignore").casefold()
            wide_sample = sample.decode("utf-16le", errors="ignore").casefold()
            combined = text_sample + "\\n" + wide_sample
            indicators = []
            rules = [
                ("remote_access_or_shell", ["meterpreter", "reverse_tcp", "reverse_https", "bind_tcp", "shellcode", "remote shell", "remoteshell"]),
                ("credential_or_key_capture", ["keylogger", "getasynckeystate", "credential theft", "lsass", "mimikatz"]),
                ("persistence_or_autostart", ["currentversion\\\\run", "\\\\software\\\\microsoft\\\\windows\\\\currentversion\\\\run", "schtasks", "startup folder", "runonce"]),
                ("cryptomining", ["stratum+tcp", "stratum+ssl", "xmrig", "cryptonight", "randomx", "mining.pool", "monero"]),
                ("download_or_execution_chain", ["powershell -enc", "frombase64string", "downloadstring", "invoke-expression", "urlmon", "winhttp", "createprocess"]),
                ("process_injection_or_memory_execution", ["virtualalloc", "writeprocessmemory", "createremotethread", "ntunmapviewofsection"]),
                ("penetration_testing_tool_reference", ["metasploit", "meterpreter", "msfconsole", "msfvenom"]),
            ]
            for category, needles in rules:
                matches = [needle for needle in needles if needle in combined]
                if matches:
                    indicators.append({"category": category, "matched_indicators": matches[:8],
                        "interpretation": "Review context; this indicator can appear in legitimate software too."})
            file_type = "PE executable or DLL" if sample[:2] == b"MZ" else "unknown / non-PE / script or data"
            return json.dumps({"ok": True, "analysis": "static_triage_only", "path": str(target),
                "file_name": target.name, "extension": target.suffix.lower(), "size_bytes": size,
                "sha256": digest, "file_type_hint": file_type, "bytes_sampled": len(sample),
                "sample_truncated": size > len(sample), "indicators": indicators,
                "risk_summary": "review_indicators_found" if indicators else "no_known_string_indicators_found",
                "note": "This is a lightweight heuristic check, not an antivirus verdict. Strings can be absent, encrypted, or misleading. No file was executed, uploaded, deleted, or quarantined. Metasploit/Metasploit Server and similar testing tools can be legitimate; a tool-name match is not a malware verdict."}, ensure_ascii=False)
        if name == "scan_with_clamav":
            _require_windows()
            import shutil
            target = Path(args["path"].strip()).resolve()
            if not target.is_absolute() or not target.exists():
                raise ValueError("Provide an existing absolute file or folder path, such as C:\\Users\\...\\Downloads\\sample.exe.")
            candidates = [
                shutil.which("clamscan"),
                str(Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "ClamAV" / "clamscan.exe"),
                str(Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "ClamAV" / "bin" / "clamscan.exe"),
                str(Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "ClamAV" / "clamscan.exe"),
            ]
            scanner = next((p for p in candidates if p and Path(p).is_file()), None)
            if not scanner:
                return json.dumps({"ok": False, "scanner_missing": True,
                    "message": "ClamAV is not installed or clamscan.exe was not found. No scan was performed.",
                    "official_download": "https://www.clamav.net/downloads",
                    "alternative": "ESET offers a free one-time Windows scanner: https://www.eset.com/us/home/online-scanner/",
                    "note": "JARVIS will not download or execute installers automatically."}, ensure_ascii=False)
            # Deliberately skip automatic signature updates here to avoid network/CPU spikes on every scan.
            # Use the scanner's installed database as-is and report that limitation to the user.
            command = [scanner, "--infected", "--recursive", "--stdout", "--detect-pua=yes",
                       "--max-filesize=50M", "--max-scansize=250M", "--max-files=2000",
                       "--max-recursion=8", str(target)]
            low_priority = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            scan = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | low_priority)
            output = (scan.stdout + "\\n" + scan.stderr)[-12000:]
            details = {"scanned_path": str(target), "target_type": "file" if target.is_file() else "folder"}
            if target.is_file():
                details["size_bytes"] = target.stat().st_size
                details["sha256"] = _sha256_file(target)
                details["extension"] = target.suffix.lower()
            if scan.returncode not in (0, 1):
                return json.dumps({"ok": False, "scanner": "ClamAV", "exit_code": scan.returncode,
                    **details, "output": output, "note": "Scan failed or timed out. No files were removed. Large files and folders may be skipped by the configured limits."}, ensure_ascii=False)
            return json.dumps({"ok": True, "scanner": "ClamAV", **details,
                "result": "detections_found" if scan.returncode == 1 else "no_detection_reported",
                "exit_code": scan.returncode, "output": output, "signature_update": "not run automatically to reduce resource/network use",
                "limits": {"max_file_mb": 50, "max_total_scan_mb": 250, "max_files": 2000, "max_recursion": 8, "timeout_seconds": 900},
                "note": "PUA/hacking-tool detections can include legitimate penetration-testing software such as Metasploit; this is not proof of malicious intent. Explain each detection and confidence. No file is deleted or quarantined automatically; a separate explicit user request is required."}, ensure_ascii=False)
        if name == "request_quarantine_file":
            _require_windows()
            target = Path(args["path"].strip()).resolve()
            if not target.is_absolute() or not target.is_file():
                raise ValueError("Only one existing file can be quarantined; folders are not accepted.")
            protected_roots = [
                Path(os.environ.get("WINDIR", r"C:\\Windows")).resolve(),
                Path(os.environ.get("ProgramFiles", r"C:\\Program Files")).resolve(),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")).resolve(),
            ]
            if any(target == root or root in target.parents for root in protected_roots):
                raise ValueError("JARVIS will not quarantine files inside Windows or Program Files. Use a trusted security product to handle system/application installations.")
            if target.stat().st_size > 2 * 1024**3:
                raise ValueError("File exceeds the 2 GB quarantine limit.")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            value = json.dumps({"path": str(target), "sha256": digest, "size": target.stat().st_size})
            return _stage("quarantine_file", f"Move the exact file '{target}' to the reversible JARVIS quarantine (not permanent deletion)", value)
        if name == "request_system_repair":
            return _stage("repair", "Run DISM /Online /Cleanup-Image /RestoreHealth followed by sfc /scannow; may require Administrator")
        if name == "request_uninstall":
            app = args["app_name"].strip()
            if not app or len(app) > 160:
                raise ValueError("Provide the exact installed application display name.")
            protected = ("microsoft defender", "windows security", "security update", "driver", "visual c++", ".net runtime", "webview2")
            if any(term in app.casefold() for term in protected):
                raise ValueError("This matches a protected security, driver, or shared-runtime category.")
            return _stage("uninstall", f"Uninstall the exact application named: {app}", app)
        if name == "request_stop_process":
            raw = args["process_name"].strip()
            if not raw or len(raw) > 100 or any(c in raw for c in "\\/;&|<>$" + chr(96)):
                raise ValueError("Provide a simple exact process name, such as gamebar.exe.")
            proc_name = Path(raw).name.casefold().removesuffix(".exe")
            if proc_name in _PROTECTED_PROCESSES:
                raise ValueError("That process is protected and cannot be stopped by JARVIS.")
            return _stage("stop_process", f"Request graceful close of user-selected process: {proc_name}.exe", proc_name)
        if name == "confirm_pending_action":
            action_id = args["action_id"]
            if args["confirmed"] is not True:
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": True, "cancelled": True, "message": "Pending action cancelled."})
            action = _PENDING_ACTIONS.get(action_id)
            if not action:
                raise ValueError("Action ID missing or expired; stage it again after explicit confirmation.")
            _require_windows()
            if action["kind"] == "copy_file":
                import shutil
                details = json.loads(action["value"])
                source = Path(details["source"])
                destination = Path(details["destination"])
                if not source.is_file() or not destination.parent.is_dir() or destination.exists():
                    raise ValueError("Source/destination changed after review; no file was copied. Check paths and stage again.")
                shutil.copy2(source, destination)
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": True, "copied_from": str(source), "copied_to": str(destination), "bytes": destination.stat().st_size}, ensure_ascii=False)
            if action["kind"] == "quarantine_file":
                import shutil
                details = json.loads(action["value"])
                source = Path(details["path"])
                if not source.is_file():
                    raise ValueError("The selected file no longer exists; nothing was changed.")
                if source.stat().st_size != details["size"] or _sha256_file(source) != details["sha256"]:
                    raise ValueError("The file changed after review; nothing was moved. Scan and review it again.")
                quarantine_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JARVIS" / "Quarantine"
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                destination = quarantine_dir / (details["sha256"] + "_" + source.name)
                if destination.exists():
                    raise ValueError("A quarantine item with this name already exists; no file was moved.")
                shutil.move(str(source), str(destination))
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": True, "quarantined": True, "original_path": str(source),
                    "quarantine_path": str(destination), "sha256": details["sha256"],
                    "note": "Moved to reversible quarantine; not permanently deleted."}, ensure_ascii=False)
            if action["kind"] == "repair":
                d = subprocess.run(["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"], capture_output=True, text=True, timeout=1800, check=False)
                if d.returncode:
                    raise RuntimeError(f"DISM failed with exit code {d.returncode}; check logs and Administrator permissions.")
                s = subprocess.run(["sfc.exe", "/scannow"], capture_output=True, text=True, timeout=1800, check=False)
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": s.returncode == 0, "dism_exit_code": d.returncode, "sfc_exit_code": s.returncode, "sfc_output": s.stdout[-2000:]}, ensure_ascii=False)
            if action["kind"] == "uninstall":
                r = subprocess.run(["winget.exe", "uninstall", "--name", action["value"], "--exact", "--accept-source-agreements"], capture_output=True, text=True, timeout=600, check=False)
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": r.returncode == 0, "exit_code": r.returncode, "output": (r.stdout + "\n" + r.stderr)[-2000:], "note": "Success is reported only for exit code 0."}, ensure_ascii=False)
            if action["kind"] == "stop_process":
                import ctypes
                from ctypes import wintypes
                import psutil
                target = action["value"]
                matches = []
                for p in psutil.process_iter(["pid", "name", "username"]):
                    try:
                        if (p.info.get("name") or "").casefold().removesuffix(".exe") == target and (not p.info.get("username") or p.info["username"].casefold() == getpass.getuser().casefold()):
                            matches.append(p)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if not matches:
                    _PENDING_ACTIONS.pop(action_id, None)
                    return json.dumps({"ok": True, "close_requests_sent": 0, "message": "No matching process owned by the current user."})
                sent = 0
                def callback(hwnd: int, _lp: int) -> bool:
                    nonlocal sent
                    pid = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if any(p.pid == pid.value for p in matches):
                        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
                        sent += 1
                    return True
                enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(callback)
                ctypes.windll.user32.EnumWindows(enum_proc, 0)
                _PENDING_ACTIONS.pop(action_id, None)
                return json.dumps({"ok": True, "close_requests_sent": sent, "matched_processes": len(matches), "note": "Graceful close requested; unsaved-work prompts may remain. No force-kill was used."})
            raise ValueError("Unsupported pending action type.")
        if name == "list_workspace":
            folder = _workspace_path(args["relative_path"])
            if not folder.exists():
                return json.dumps({"ok": True, "items": [], "note": "Folder does not exist."})
            if not folder.is_dir():
                raise ValueError("The requested path is not a folder.")
            items = [{"name": p.name, "type": "folder" if p.is_dir() else "file"} for p in sorted(folder.iterdir(), key=lambda p: p.name.lower())][:200]
            return json.dumps({"ok": True, "items": items})
        if name == "read_workspace_file":
            path = _workspace_path(args["relative_path"])
            if not path.is_file():
                raise ValueError("File not found in JARVISWorkspace.")
            if path.stat().st_size > 200_000:
                raise ValueError("File exceeds the 200 KB read limit.")
            return json.dumps({"ok": True, "relative_path": args["relative_path"], "content": path.read_text(encoding="utf-8")})
        if name == "write_workspace_file":
            path = _workspace_path(args["relative_path"])
            content = args["content"]
            if not path.name:
                raise ValueError("A file name is required.")
            if len(content.encode("utf-8")) > 200_000:
                raise ValueError("Content exceeds the 200 KB write limit.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return json.dumps({"ok": True, "written": args["relative_path"], "bytes": len(content.encode("utf-8"))})
        if name == "create_workspace_folder":
            path = _workspace_path(args["relative_path"])
            path.mkdir(parents=True, exist_ok=True)
            return json.dumps({"ok": True, "created_folder": args["relative_path"]})
        raise ValueError("Unknown or unsupported computer-control tool.")
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
