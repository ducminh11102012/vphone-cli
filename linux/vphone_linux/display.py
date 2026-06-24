"""Display backend + host-GPU presentation acceleration.

Hard truth first: these QEMU forks do **not** emulate the Apple GPU. iOS
renders its UI in software (on the CPU), and there is no virtio-gpu / virgl
path for iOS (those are Linux-guest only) and no way to expose a host GPU to
Apple's Metal/AGX stack. So you cannot GPU-accelerate iOS rendering itself —
that is a limitation of the emulator, not of this orchestrator.

What you CAN accelerate with the host GPU is *presentation*: the
software-rendered framebuffer is uploaded/scaled/blitted to the window through
OpenGL instead of the CPU. That is what `gl=on` does on the gtk/sdl/egl
backends, and it meaningfully cuts the CPU spent on the display path and gives
smooth scaling. We also expose headless/VNC for remote or server use.
"""
from __future__ import annotations

from .config import Config

_GL_CAPABLE = {"gtk", "sdl", "egl-headless"}
_KNOWN = {"auto", "gtk", "sdl", "cocoa", "egl-headless", "vnc", "none"}


def display_args(cfg: Config) -> list[str]:
    """QEMU args selecting the display backend + host-GPU presentation."""
    # VNC takes precedence when a display number is configured.
    if cfg.vnc_display and cfg.vnc_display > 0:
        args: list[str] = []
        # egl-headless renders with the host GPU and feeds the VNC server,
        # giving GPU-accelerated presentation over a remote connection.
        if cfg.gl == "on":
            args += ["-display", "egl-headless"]
        args += ["-vnc", f"127.0.0.1:{cfg.vnc_display}"]
        return args

    mode = cfg.display
    if mode not in _KNOWN:
        raise ValueError(
            f"unknown display '{mode}' (use: {', '.join(sorted(_KNOWN))})"
        )

    if mode == "none":
        return ["-display", "none"]

    if mode == "auto":
        # Let QEMU choose its compiled-in default backend, but still ask for
        # GL when the user wants it — QEMU ignores gl on backends that lack it.
        return []

    spec = mode
    if mode in _GL_CAPABLE:
        spec += f",gl={'on' if cfg.gl == 'on' else 'off'}"
    return ["-display", spec]


def describe(cfg: Config) -> str:
    if cfg.vnc_display and cfg.vnc_display > 0:
        acc = "host-GPU (egl-headless)" if cfg.gl == "on" else "software"
        return f"display: VNC 127.0.0.1:{5900 + cfg.vnc_display} ({acc} present)"
    if cfg.display == "none":
        return "display: headless (none)"
    gl = "host-GPU present" if (cfg.gl == "on" and cfg.display in _GL_CAPABLE | {"auto"}) else "software present"
    return f"display: {cfg.display} ({gl}); iOS renders in software either way"
