from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

WORKSPACE = (Path.home() / "Documents" / "JARVISWorkspace").resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Deliberately narrow first release: no arbitrary shell, deletion, registry, or admin actions.
ALLOWED_APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
}


def _workspace_path(relative_path: str) -> Path:
    candidate = (WORKSPACE / relative_path).resolve()
    if candidate != WORKSPACE and WORKSPACE not in candidate.parents:
        raise ValueError("Path must remain inside the JARVISWorkspace folder.")
    return candidate


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "open_app",
            "description": "Open one of the approved Windows applications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "enum": sorted(ALLOWED_APPS)}
                },
                "required": ["app"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "open_url",
            "description": "Open a normal HTTP or HTTPS website in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "list_workspace",
            "description": "List files and folders inside the JARVISWorkspace folder.",
            "parameters": {
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "read_workspace_file",
            "description": "Read a UTF-8 text file inside the JARVISWorkspace folder (maximum 200 KB).",
            "parameters": {
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "write_workspace_file",
            "description": "Create or replace a UTF-8 text file inside JARVISWorkspace. Only do this when the user clearly requested the file change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["relative_path", "content"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "create_workspace_folder",
            "description": "Create a folder inside JARVISWorkspace.",
            "parameters": {
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


def execute_tool(name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json)
        if not isinstance(args, dict):
            raise ValueError("Arguments must be an object.")

        if name == "open_app":
            app_name = args["app"]
            command = ALLOWED_APPS.get(app_name)
            if not command:
                raise ValueError("That application is not in the approved app list.")
            if os.name != "nt":
                raise RuntimeError("Computer-control tools are currently supported on Windows only.")
            subprocess.Popen(command, shell=False, close_fds=True)
            return json.dumps({"ok": True, "opened": app_name})

        if name == "open_url":
            url = args["url"].strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Only complete http:// or https:// URLs are allowed.")
            webbrowser.open(url, new=2)
            return json.dumps({"ok": True, "opened_url": url})

        if name == "list_workspace":
            folder = _workspace_path(args["relative_path"])
            if not folder.exists():
                return json.dumps({"ok": True, "items": [], "note": "Folder does not exist."})
            if not folder.is_dir():
                raise ValueError("The requested path is not a folder.")
            items = [
                {"name": item.name, "type": "folder" if item.is_dir() else "file"}
                for item in sorted(folder.iterdir(), key=lambda p: p.name.lower())
            ][:200]
            return json.dumps({"ok": True, "items": items})

        if name == "read_workspace_file":
            path = _workspace_path(args["relative_path"])
            if not path.is_file():
                raise ValueError("File not found in JARVISWorkspace.")
            if path.stat().st_size > 200_000:
                raise ValueError("File is larger than the 200 KB read limit.")
            return json.dumps({"ok": True, "relative_path": args["relative_path"], "content": path.read_text(encoding="utf-8")})

        if name == "write_workspace_file":
            relative_path = args["relative_path"]
            path = _workspace_path(relative_path)
            if not path.name:
                raise ValueError("A file name is required.")
            content = args["content"]
            if len(content.encode("utf-8")) > 200_000:
                raise ValueError("File content exceeds the 200 KB write limit.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return json.dumps({"ok": True, "written": relative_path, "bytes": len(content.encode("utf-8"))})

        if name == "create_workspace_folder":
            path = _workspace_path(args["relative_path"])
            path.mkdir(parents=True, exist_ok=True)
            return json.dumps({"ok": True, "created_folder": args["relative_path"]})

        raise ValueError("Unknown or unsupported computer-control tool.")
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
