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


def apply_source_fixes(workspace: Path) -> None:
    """Apply the source-level fixes needed to build the t8030 fork (7.1.0).

    Both are idempotent and guarded — they no-op if the tree already differs
    (e.g. a newer fork that fixed them upstream). See BUILD.md for the why.
    """
    src = src_dir(workspace)

    # 1) qapi/ui.json: QKeyCode is trimmed to f1–f12, but generated keymaps
    #    reference F13–F24. Add the missing enum entries.
    ui_json = src / "qapi" / "ui.json"
    if ui_json.exists():
        text = ui_json.read_text()
        if "'f13'" not in text and "'lang1', 'lang2' ] }" in text:
            text = text.replace(
                "'lang1', 'lang2' ] }",
                "'lang1', 'lang2',\n"
                "            'f13', 'f14', 'f15', 'f16', 'f17', 'f18',\n"
                "            'f19', 'f20', 'f21', 'f22', 'f23', 'f24' ] }",
            )
            ui_json.write_text(text)
            util.ok("patched qapi/ui.json (QKeyCode f13–f24)")

    # 2) meson.build: libtasn1 detection is gated behind gnutls. Ungate it so
    #    hw/arm/xnu.c links (asn1_* symbols).
    meson = src / "meson.build"
    if meson.exists():
        text = meson.read_text()
        gated = (
            "tasn1 = not_found\n"
            "if gnutls.found()\n"
            "  tasn1 = dependency('libtasn1',\n"
            "                     method: 'pkg-config',\n"
            "                     kwargs: static_kwargs)\n"
            "endif"
        )
        if gated in text:
            text = text.replace(
                gated,
                "tasn1 = dependency('libtasn1',\n"
                "                   method: 'pkg-config',\n"
                "                   required: false,\n"
                "                   kwargs: static_kwargs)",
            )
            meson.write_text(text)
            util.ok("patched meson.build (ungate libtasn1 from gnutls)")


def configure_and_make(workspace: Path, backend: Backend, jobs: int | None = None) -> Path:
    src = src_dir(workspace)
    build = build_dir(workspace)
    build.mkdir(parents=True, exist_ok=True)
    apply_source_fixes(workspace)

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
