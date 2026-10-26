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
