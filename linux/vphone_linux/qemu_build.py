"""Clone and build the selected QEMU fork inside a workspace.

We do not vendor QEMU; we clone the chosen fork at the configured ref and run
its own configure/make. Build deps are checked up front by `doctor`.
"""
from __future__ import annotations

import os
from pathlib import Path

from .backends import Backend
from .config import Config
from . import util


# Debian/Ubuntu package names for the QEMU build toolchain. Reported by
# `doctor`; not auto-installed (we never sudo behind the user's back).
BUILD_DEPS_APT = [
    "git", "ninja-build", "pkg-config", "python3", "python3-venv",
    "libglib2.0-dev", "libpixman-1-dev", "libslirp-dev", "zlib1g-dev",
    "meson", "build-essential", "flex", "bison",
    # host-GPU presentation (gl=on) + GTK/SDL display backends
    "libgtk-3-dev", "libsdl2-dev", "libepoxy-dev", "libgbm-dev",
    "libegl-dev", "libvirglrenderer-dev",
]


def src_dir(workspace: Path) -> Path:
    return workspace / Config.workspace_dirs()["src"]


def build_dir(workspace: Path) -> Path:
    return workspace / Config.workspace_dirs()["build"]


def qemu_binary_path(workspace: Path, backend: Backend) -> Path:
    return build_dir(workspace) / backend.qemu_binary


def is_built(workspace: Path, backend: Backend) -> bool:
    return qemu_binary_path(workspace, backend).exists()


def clone_or_update(workspace: Path, backend: Backend, ref: str) -> None:
    src = src_dir(workspace)
    ref = ref or backend.default_ref
    if not src.exists():
        util.step(f"Cloning {backend.name}")
        util.run(["git", "clone", "--recursive", backend.git_url, str(src)])
    else:
        util.info(f"Source already present at {src}; fetching updates")
        util.run(["git", "fetch", "--all", "--tags"], cwd=src, check=False)
    util.run(["git", "checkout", ref], cwd=src, check=False)
    # keep submodules (e.g. fork-specific dtb/keystone bits) in sync
    util.run(["git", "submodule", "update", "--init", "--recursive"], cwd=src, check=False)


def configure_and_make(workspace: Path, backend: Backend, jobs: int | None = None) -> Path:
    src = src_dir(workspace)
    build = build_dir(workspace)
    build.mkdir(parents=True, exist_ok=True)

    util.step(f"Configuring {backend.name}")
    configure = src / "configure"
    if not configure.exists():
        raise util.CommandError(f"{configure} missing — clone may have failed")
    util.run([str(configure), *backend.configure_flags], cwd=build)

    util.step("Building (this takes a while)")
    jobs = jobs or os.cpu_count() or 4
    util.run(["make", f"-j{jobs}"], cwd=build)

    binary = qemu_binary_path(workspace, backend)
    if not binary.exists():
        raise util.CommandError(
            f"build finished but {binary.name} not found in {build}"
        )
    util.ok(f"Built {binary}")
    return binary


def build(workspace: Path, backend: Backend, cfg: Config, jobs: int | None = None) -> Path:
    clone_or_update(workspace, backend, cfg.qemu_ref)
    return configure_and_make(workspace, backend, jobs)
