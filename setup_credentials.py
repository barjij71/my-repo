from __future__ import annotations

import getpass
import os
import secrets
import sys

SERVICE = "JARVIS"
API_KEY_NAME = "OPENAI_API_KEY"
ACCESS_TOKEN_NAME = "JARVIS_ACCESS_TOKEN"


def main() -> int:
    if os.name != "nt":
        print("Credential setup is designed for Windows Credential Manager.", file=sys.stderr)
        return 2

    try:
        import keyring
    except ImportError:
        print("Missing dependency. Run start.ps1 first to install requirements.", file=sys.stderr)
        return 2

    try:
        reset_api_key = "--reset-api-key" in sys.argv[1:]
        current_key = keyring.get_password(SERVICE, API_KEY_NAME)
        if reset_api_key:
            print("Replacement OpenAI API key setup (input is hidden; key is stored in Windows Credential Manager).")
            key = getpass.getpass("Replacement OpenAI API key: ").strip()
            if not key:
                print("No key entered; the existing credential was left unchanged.", file=sys.stderr)
                return 1
            keyring.set_password(SERVICE, API_KEY_NAME, key)
            del key
            print("API key saved to Windows Credential Manager.")
        elif not current_key:
            print("No OpenAI API key is configured. JARVIS can start in limited mode; add any supported provider in Settings.")

        token = keyring.get_password(SERVICE, ACCESS_TOKEN_NAME)
        if not token:
            token = secrets.token_urlsafe(32)
            keyring.set_password(SERVICE, ACCESS_TOKEN_NAME, token)
        print("JARVIS local access token is stored in Windows Credential Manager and loaded automatically by the desktop app.")
        return 0
    except Exception as exc:
        print(f"Credential Manager operation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
