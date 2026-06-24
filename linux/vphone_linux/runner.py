"""Run and supervise the QEMU process, plus environment doctor checks."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from .backends import Backend
from .bootcmd import BootPlan
from .config import Config
from . import qemu_build, util


# ─── doctor ──────────────────────────────────────────────────────────
def doctor(workspace: Path | None, backend: Backend) -> bool:
    """Report on build/runtime prerequisites. Returns True if runnable."""
    util.step("Environment check")
    ok = True

    # host arch note. KVM is NOT usable for t8030 on ANY host: the guest
    # relies on Apple-proprietary CPU features (SPRR/GXF, custom PAC) that the
    # fork emulates in TCG and that no real host CPU — not even Apple Silicon
    # via Linux/KVM — exposes. So it is always TCG; an aarch64 host is only
    # faster because ARM→ARM translation is cheaper, not because of KVM.
    machine = os.uname().machine
    if machine not in ("aarch64", "arm64"):
        util.warn(
            f"host arch is {machine}; always TCG (KVM cannot run t8030). "
            "ARM→x86 translation is heavy, so this is slow but functional. An "
            "aarch64 host is much faster — still TCG, just cheaper translation."
        )
    else:
        util.ok(
            f"host arch {machine}: TCG with cheap ARM→ARM translation "
            "(fastest available; KVM still does not apply to t8030)"
        )

    for tool in ("git", "make", "ninja", "pkg-config"):
        if util.have(tool):
            util.ok(f"found {tool}")
        else:
            util.err(f"missing build tool: {tool}")
            ok = False

    # python build deps for QEMU
    if util.have("meson"):
        util.ok("found meson")
    else:
        util.warn("meson not on PATH (QEMU may bootstrap its own)")

    # host-GPU presentation prerequisites (gl=on). iOS still renders in
    # software; this only accelerates display blitting.
    if any(os.path.exists(p) for p in (
        "/usr/lib/x86_64-linux-gnu/libEGL.so.1",
        "/usr/lib/aarch64-linux-gnu/libEGL.so.1",
        "/usr/lib/libEGL.so.1",
    )) or util.have("eglinfo"):
        util.ok("host EGL present (gl=on presentation available)")
    else:
        util.warn(
            "host EGL not detected; install libegl1/mesa for `gl=on`, or use "
            "--display none / --gl off. (Configure QEMU with --enable-opengl.)"
        )

    util.dim(
        "  apt deps: " + " ".join(qemu_build.BUILD_DEPS_APT)
    )

    if workspace is not None:
        binary = qemu_build.qemu_binary_path(workspace, backend)
        if binary.exists():
            util.ok(f"QEMU built: {binary}")
        else:
            util.warn(f"QEMU not built yet — run `vphone-linux build`")

    return ok


# ─── run ─────────────────────────────────────────────────────────────
def run_plan(plan: BootPlan, logs_dir: Path, log_name: str) -> int:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / log_name
    util.step(plan.description)
    util.info(f"serial console is attached to this terminal; log → {log_path}")

    # forward Ctrl-C cleanly to QEMU
    proc = subprocess.Popen(plan.argv)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        util.warn("interrupt — sending SIGTERM to QEMU")
        proc.send_signal(signal.SIGTERM)
        try:
            return proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait()
