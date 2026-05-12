#!/usr/bin/env python3
"""Generate the "Install in VS Code" badge URLs for the README.

Usage:
    uv run scripts/generate_vscode_install_urls.py

Prints two URLs (Stable, Insiders) plus ready-to-paste badge markdown for both.
If the launch command or prompted inputs ever change, edit the CONFIG / INPUTS
constants below and rerun this script, then paste the new URLs into README.md.

URL format reference: https://code.visualstudio.com/api/extension-guides/ai/mcp
"""

import json
import urllib.parse

NAME = "mcp-hydrolix"

CONFIG = {
    "type": "stdio",
    "command": "uvx",
    "args": ["--python", "3.13", "--refresh-package", "mcp-hydrolix", "mcp-hydrolix"],
    "env": {
        "HYDROLIX_HOST": "${input:hydrolix_host}",
        "HYDROLIX_USER": "${input:hydrolix_user}",
        "HYDROLIX_PASSWORD": "${input:hydrolix_password}",
    },
}

INPUTS = [
    {
        "id": "hydrolix_host",
        "type": "promptString",
        "description": "Hydrolix hostname (e.g. mycluster.hydrolix.live)",
    },
    {
        "id": "hydrolix_user",
        "type": "promptString",
        "description": "Hydrolix username",
    },
    {
        "id": "hydrolix_password",
        "type": "promptString",
        "description": "Hydrolix password",
        "password": True,
    },
]


def encode(obj: object) -> str:
    return urllib.parse.quote(json.dumps(obj, separators=(",", ":")), safe="")


def build_urls() -> tuple[str, str]:
    cfg = encode(CONFIG)
    inp = encode(INPUTS)
    stable = f"https://vscode.dev/redirect/mcp/install?name={NAME}&config={cfg}&inputs={inp}"
    insiders = (
        f"https://insiders.vscode.dev/redirect/mcp/install?name={NAME}"
        f"&quality=insiders&config={cfg}&inputs={inp}"
    )
    return stable, insiders


def main() -> None:
    stable, insiders = build_urls()

    print("=== Stable URL ===")
    print(stable)
    print()
    print("=== Insiders URL ===")
    print(insiders)
    print()
    print("=== Badge markdown (paste into README.md) ===")
    print(
        f"[![Install in VS Code]"
        f"(https://img.shields.io/badge/VS_Code-Install_mcp--hydrolix-0098FF"
        f"?style=flat-square&logo=visualstudiocode&logoColor=white)]({stable})"
    )
    print(
        f"[![Install in VS Code Insiders]"
        f"(https://img.shields.io/badge/VS_Code_Insiders-Install_mcp--hydrolix-24bfa5"
        f"?style=flat-square&logo=visualstudiocode&logoColor=white)]({insiders})"
    )


if __name__ == "__main__":
    main()
