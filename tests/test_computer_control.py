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
            "list_installed_apps", "scan_with_clamav", "request_system_repair",
            "request_uninstall", "request_stop_process", "confirm_pending_action"} <= names


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
    assert "will not launch executable" in result["error"]



def test_clamav_scan_reports_official_options_when_scanner_missing(monkeypatch, tmp_path):
    import os
    if os.name != "nt":
        return
    monkeypatch.setattr(control.shutil if hasattr(control, "shutil") else __import__("shutil"), "which", lambda _name: None)
    result = json.loads(control.execute_tool("scan_with_clamav", json.dumps({"path": str(tmp_path)})))
    assert result["ok"] is False
    assert result["scanner_missing"] is True
    assert "clamav.net" in result["official_download"]


def test_cross_drive_copy_requires_windows_and_is_exposed():
    names = {tool["name"] for tool in control.tool_schemas()}
    assert "request_copy_file" in names
    result = json.loads(control.execute_tool("request_copy_file", json.dumps({
        "source_path": "C:\\\\example.txt", "destination_path": "D:\\\\example.txt"
    })))
    if __import__("os").name != "nt":
        assert result["ok"] is False
        assert "Windows" in result["error"]
