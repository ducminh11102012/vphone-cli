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

    # ─── networking ──────────────────────────────────────────────────
    # How the emulated iPhone reaches the network. The t8030 SoC has no
    # plain ethernet NIC that iOS binds for internet; the real path is USB
    # tethering bridged through a companion Linux VM.
    #   "usb-bridge" — expose iOS USB over a socket + run a companion VM
    #                  that NATs to the internet (the documented, working way)
    #   "user"       — attach a QEMU user-mode netdev directly (only forks
    #                  that expose an in-machine NIC; convenient when it works)
    #   "off"        — no networking
    network: str = "usb-bridge"
    # unix socket the iOS USB is exposed on (workspace-relative)
    usb_socket: str = "usbqemu.sock"
    # host TCP port forwarded to the guest's SSH (22)
    ssh_host_port: int = 2222
    # device string used to attach the iOS-side USB bridge. Kept as config
    # because forks differ; this is the documented qemu-t8030 form.
    usb_bridge_device: str = "usb-tcp-remote"
    # companion VM (used only for network = "usb-bridge")
    companion_image: str = ""    # path to a bootable Linux disk image
    companion_kernel: str = ""   # optional explicit kernel
    companion_memory_mb: int = 1024
    companion_cpus: int = 2

    # ─── display / GPU ───────────────────────────────────────────────
    # IMPORTANT: the forks do NOT emulate the Apple GPU; iOS renders in
    # software. There is no way to GPU-accelerate iOS rendering itself.
    # These options accelerate the *presentation* of the software-rendered
    # framebuffer using the host GPU via OpenGL, and pick the output backend.
    #   display: auto | gtk | sdl | cocoa | egl-headless | vnc | none
    #   gl:      on | off    (host OpenGL for the display surface)
    display: str = "auto"
    gl: str = "on"
    # VNC server display number base; 0 disables VNC (overrides `display`).
    # When >0, the server listens on 127.0.0.1:(5900 + vnc_display).
    vnc_display: int = 0

    # ─── acceleration / TCG tuning ───────────────────────────────────
    # On x86_64 hosts everything is TCG (KVM never applies — see README).
    # These knobs make TCG smoother without changing correctness:
    #   tcg_thread = "multi" enables MTTCG (one host thread per vCPU). Big win
    #     for SMP, but the fork's device models must be thread-safe — opt-in.
    #   tb_size_mb sizes the translation-block cache; larger = fewer costly
    #     re-translations (smoother), at the cost of host RAM.
    #   mem_prealloc preallocates guest RAM for steadier latency.
    tcg_thread: str = "single"   # single | multi
    tb_size_mb: int = 256
    mem_prealloc: bool = False

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
