"""Shared helpers: logging, shell execution, file checks.

Style follows the project design system: terminal-adjacent, precise,
status-colored, monospace-friendly. No decoration.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

# ─── ANSI status palette (mirrors the macOS UI accents) ──────────────
_RESET = "\033[0m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_AMBER = "\033[33m"
_RED = "\033[31m"
_BLUE = "\033[34m"
_BOLD = "\033[1m"

_USE_COLOR = sys.stderr.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _USE_COLOR else text


def info(msg: str) -> None:
    print(_c(_BLUE, "[*]") + f" {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(_c(_GREEN, "[+]") + f" {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(_c(_AMBER, "[!]") + f" {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(_c(_RED, "[x]") + f" {msg}", file=sys.stderr)


def step(msg: str) -> None:
    print(_c(_BOLD, f"\n══ {msg}"), file=sys.stderr)


def dim(msg: str) -> None:
    print(_c(_DIM, msg), file=sys.stderr)


class CommandError(RuntimeError):
    """A subprocess exited non-zero."""


def have(tool: str) -> bool:
    """Return True if `tool` is on PATH."""
    return shutil.which(tool) is not None


def run(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = False,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, echoing it first. Raises CommandError on failure."""
    printable = " ".join(str(c) for c in cmd)
    dim(f"  $ {printable}")
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd) if cwd else None,
            check=False,
            text=True,
            capture_output=capture,
            env=env,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"command not found: {cmd[0]}") from exc
    if check and proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        raise CommandError(
            f"`{cmd[0]}` exited {proc.returncode}" + (f":\n{out}" if out.strip() else "")
        )
    return proc


def require_files(paths: Iterable[Path]) -> None:
    """Raise if any path is missing — used before building a boot command."""
    missing = [str(p) for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            "required file(s) not found:\n  " + "\n  ".join(missing)
        )


def human_size(num: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}"
        num = int(num / 1024.0)
    return f"{num:.1f}PiB"
