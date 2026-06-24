"""Workspace configuration.

A workspace is a directory that holds: the built QEMU fork, the extracted
firmware, the NVMe namespace images, and a `vphone-linux.toml` describing the
chosen backend/device and resource sizing. Everything is relative to the
workspace root so a workspace is self-contained and movable.
"""
from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

# tomli_w is optional; we fall back to a tiny hand-writer if absent.
try:  # pragma: no cover - trivial import guard
    import tomli_w  # type: ignore

    _HAVE_TOMLI_W = True
except Exception:  # pragma: no cover
    _HAVE_TOMLI_W = False


CONFIG_NAME = "vphone-linux.toml"


@dataclass
class Config:
    backend: str = "chefkiss"
    device: str = "t8030"
    # resources
    cpus: int = 4
    memory_mb: int = 4096
    # boot args appended to the kernel command line
    boot_args: str = "debug=0x14e kextlog=0xffff serial=3 -v wdt=-1"
    # source ref to build (branch/tag/commit)
    qemu_ref: str = ""          # empty → backend default
    # monitor / debug
    gdb_stub: bool = True       # qemu -s (gdb on :1234)
    monitor_telnet_port: int = 1235

    # ─── workspace-relative layout ───────────────────────────────────
    @staticmethod
    def workspace_dirs() -> dict[str, str]:
        return {
            "src": "qemu-src",          # cloned QEMU fork
            "build": "qemu-src/build",  # QEMU build dir
            "firmware": "firmware",     # extracted IPSW components
            "disks": "disks",           # nvme.* namespace images + nvram
            "ipsw": "ipsw",             # downloaded IPSWs
            "logs": "logs",
        }

    def save(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / CONFIG_NAME
        data = asdict(self)
        if _HAVE_TOMLI_W:
            with open(path, "wb") as f:
                tomli_w.dump(data, f)
        else:
            path.write_text(_dump_toml(data))

    @classmethod
    def load(cls, workspace: Path) -> "Config":
        path = workspace / CONFIG_NAME
        if not path.exists():
            raise FileNotFoundError(
                f"no {CONFIG_NAME} in {workspace} — run `vphone-linux init` first"
            )
        with open(path, "rb") as f:
            data = tomllib.load(f)
        known = {f.name for f in fields_of(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def fields_of(cls):
    import dataclasses

    return dataclasses.fields(cls)


def _dump_toml(data: dict) -> str:
    """Minimal TOML writer for flat str/int/bool dicts (fallback only)."""
    lines = []
    for k, v in data.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        else:
            esc = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{esc}"')
    return "\n".join(lines) + "\n"
