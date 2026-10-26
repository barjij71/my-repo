import json
from pathlib import Path

import computer_control as control


def test_workspace_path_rejects_traversal():
    try:
        control._workspace_path("../outside.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("Workspace path traversal should be rejected")


def test_open_url_rejects_non_http_schemes():
    result = json.loads(control.execute_tool("open_url", json.dumps({"url": "file:///C:/Windows/win.ini"})))
    assert result["ok"] is False
    assert "http://" in result["error"] or "https://" in result["error"]


def test_open_app_rejects_unknown_application():
    result = json.loads(control.execute_tool("open_app", json.dumps({"app": "powershell"})))
    assert result["ok"] is False


def test_write_and_read_workspace_file(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "WORKSPACE", tmp_path.resolve())
    written = json.loads(control.execute_tool(
        "write_workspace_file",
        json.dumps({"relative_path": "notes/test.txt", "content": "JARVIS test"}),
    ))
    assert written["ok"] is True
    read = json.loads(control.execute_tool(
        "read_workspace_file",
        json.dumps({"relative_path": "notes/test.txt"}),
    ))
    assert read["ok"] is True
    assert read["content"] == "JARVIS test"


def test_write_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "WORKSPACE", tmp_path.resolve())
    result = json.loads(control.execute_tool(
        "write_workspace_file",
        json.dumps({"relative_path": "../escape.txt", "content": "no"}),
    ))
    assert result["ok"] is False
    assert not (tmp_path.parent / "escape.txt").exists()


def test_tool_schemas_include_maintenance_capabilities():
    names = {tool["name"] for tool in control.tool_schemas()}
    assert {"open_path", "list_drives", "copy_to_clipboard", "list_processes",
            "list_installed_apps", "analyze_suspicious_file", "scan_with_clamav", "request_quarantine_file", "request_system_repair",
            "request_uninstall", "request_stop_process", "confirm_pending_action",
            "save_memory", "search_memories", "list_memories", "forget_memory"} <= names


def test_clipboard_is_text_only_and_rejects_non_windows(monkeypatch):
    monkeypatch.setattr(control.os, "name", "posix")
    result = json.loads(control.execute_tool("copy_to_clipboard", json.dumps({"text": "C:\\Games\\game.exe"})))
    assert result["ok"] is False
    assert "Windows" in result["error"]


def test_stop_process_protects_critical_processes():
    result = json.loads(control.execute_tool("request_stop_process", json.dumps({"process_name": "lsass.exe"})))
    assert result["ok"] is False
    assert "protected" in result["error"]


def test_disruptive_actions_are_staged_not_executed():
    result = json.loads(control.execute_tool("request_system_repair", "{}"))
    assert result["ok"] is True
    assert result["status"] == "awaiting_confirmation"
    assert result["action_id"]
    assert "No change has been made" in result["message"]


def test_uninstall_requires_a_specific_app_name_and_stages_confirmation():
    result = json.loads(control.execute_tool("request_uninstall", json.dumps({"app_name": "Example App"})))
    assert result["ok"] is True
    assert result["status"] == "awaiting_confirmation"
    assert result["action"].endswith("Example App")
    protected = json.loads(control.execute_tool("request_uninstall", json.dumps({"app_name": "Microsoft Defender Antivirus"})))
    assert protected["ok"] is False


def test_process_listing_is_read_only():
    result = json.loads(control.execute_tool("list_processes", json.dumps({"limit": 5})))
    assert result["ok"] is True
    assert len(result["processes"]) <= 5
    assert "Read-only" in result["note"]


def test_confirmation_false_cancels_pending_action():
    staged = json.loads(control.execute_tool("request_system_repair", "{}"))
    result = json.loads(control.execute_tool("confirm_pending_action", json.dumps({"action_id": staged["action_id"], "confirmed": False})))
    assert result["ok"] is True
    assert result["cancelled"] is True


def test_open_path_refuses_executable_files_on_windows(tmp_path):
    import os
    if os.name != "nt":
        return
    executable = tmp_path / "not-a-real-program.exe"
    executable.write_text("test", encoding="utf-8")
    result = json.loads(control.execute_tool("open_path", json.dumps({"path": str(executable)})))
    assert result["ok"] is False
    assert "will not open executable" in result["error"]



def test_open_path_blocks_active_content_suffixes_on_all_platforms(tmp_path):
    dangerous = [
        "payload.exe", "script.ps1", "script.py", "active.html",
        "shortcut.url", "registry.reg", "installer.msi", "script.js",
    ]
    for filename in dangerous:
        assert control._is_blocked_open_suffix(tmp_path / filename), filename

    safe_examples = ["notes.txt", "report.pdf", "photo.png", "data.csv"]
    for filename in safe_examples:
        assert not control._is_blocked_open_suffix(tmp_path / filename), filename


def test_streaming_sha256_matches_standard_digest(tmp_path):
    import hashlib

    sample = tmp_path / "hash-me.bin"
    payload = b"jarvis-hash-test" * 100_000
    sample.write_bytes(payload)
    assert control._sha256_file(sample) == hashlib.sha256(payload).hexdigest()



def test_clamav_scanner_is_exposed_and_windows_only():
    import os
    names = {tool["name"] for tool in control.tool_schemas()}
    assert "scan_with_clamav" in names
    if os.name != "nt":
        result = json.loads(control.execute_tool("scan_with_clamav", json.dumps({"path": "/tmp"})))
        assert result["ok"] is False
        assert "Windows" in result["error"]


def test_cross_drive_copy_requires_windows_and_is_exposed():
    names = {tool["name"] for tool in control.tool_schemas()}
    assert "request_copy_file" in names
    result = json.loads(control.execute_tool("request_copy_file", json.dumps({
        "source_path": "C:\\\\example.txt", "destination_path": "D:\\\\example.txt"
    })))
    if __import__("os").name != "nt":
        assert result["ok"] is False
        assert "Windows" in result["error"]



def test_quarantine_requires_existing_file_and_windows(tmp_path, monkeypatch):
    import os
    result = json.loads(control.execute_tool("request_quarantine_file", json.dumps({"path": str(tmp_path / "missing.exe")})))
    assert result["ok"] is False
    if os.name != "nt":
        result = json.loads(control.execute_tool("request_quarantine_file", json.dumps({"path": str(tmp_path)})))
        assert result["ok"] is False
        assert "Windows" in result["error"]


def test_clamav_scan_is_resource_bounded_and_never_auto_remediates():
    schema = next(tool for tool in control.tool_schemas() if tool["name"] == "scan_with_clamav")
    assert "resource-bounded" in schema["description"]
    assert "Never deletes or quarantines" in schema["description"]
    assert "request_quarantine_file" in {tool["name"] for tool in control.tool_schemas()}



def test_static_triage_reports_indicators_without_execution(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("example string: xmrig stratum+tcp metasp loit", encoding="utf-8")
    result = json.loads(control.execute_tool("analyze_suspicious_file", json.dumps({"path": str(sample)})))
    assert result["ok"] is True
    assert result["analysis"] == "static_triage_only"
    assert result["sha256"]
    assert "cryptomining" in {item["category"] for item in result["indicators"]}
    assert sample.exists()


def test_static_triage_rejects_directories(tmp_path):
    result = json.loads(control.execute_tool("analyze_suspicious_file", json.dumps({"path": str(tmp_path)})))
    assert result["ok"] is False
    assert "file path" in result["error"]


def test_memory_tools_route_through_the_local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "jarvis-memory.sqlite3"))
    saved = json.loads(control.execute_tool("save_memory", json.dumps({
        "content": "Prefers lightweight on-demand scans.",
        "category": "preference",
    })))
    assert saved["ok"] is True
    memory_id = saved["memory"]["id"]

    found = json.loads(control.execute_tool("search_memories", json.dumps({
        "query": "on-demand", "limit": 5,
    })))
    assert found["count"] == 1
    assert found["memories"][0]["id"] == memory_id

    forgotten = json.loads(control.execute_tool("forget_memory", json.dumps({"memory_id": memory_id})))
    assert forgotten["ok"] is True
