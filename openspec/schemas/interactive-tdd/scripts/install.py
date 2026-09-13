"""Install the adjacent portable schema without replacing user modifications."""

import os
from pathlib import Path
import shutil


def inventory(root: Path) -> dict[str, bytes]:
    """Compare shipped files, excluding Python execution caches."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def destination() -> Path:
    """Match OpenSpec's documented user-data directory resolution."""
    if os.environ.get("XDG_DATA_HOME"):
        base = Path(os.environ["XDG_DATA_HOME"])
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "openspec" / "schemas" / "interactive-tdd"


def main() -> None:
    source = Path(__file__).resolve().parent.parent
    target = destination()
    if target.exists():
        if inventory(source) != inventory(target):
            raise SystemExit(f"Refusing to overwrite differing installation: {target}")
        print(f"Already installed: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"Installed: {target}")


if __name__ == "__main__":
    main()
