"""QEMU-fork backend abstraction.

Two software Apple-silicon emulators are supported and switchable at runtime:

  * chefkiss   — ChefKissInc/QEMUAppleSilicon (a.k.a. Inferno). Most active;
                 boots iPhone 11 to SpringBoard, software rendering, SSH,
                 pairing, multitouch, networking, IPA install.
  * trung      — TrungNguyen1909/qemu-t8030. The original; well-documented
                 wiki, stable, fewer features.

Both expose a `t8030` machine type and share the same configure flags, so the
abstraction is intentionally thin: it captures where to clone from, what to
build, and the per-fork quirks of the boot command line.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Backend:
    key: str
    name: str
    git_url: str
    default_ref: str
    # configure flags shared by both forks (verified against both wikis)
    configure_flags: tuple[str, ...] = (
        "--target-list=aarch64-softmmu,x86_64-softmmu",
        "--disable-capstone",
        "--enable-lzfse",
        "--disable-werror",
    )
    # Some forks gate behaviour on extra machine sub-options. Kept here so the
    # boot-command builder can append them without hardcoding per fork.
    extra_machine_opts: tuple[str, ...] = ()
    notes: str = ""

    @property
    def qemu_binary(self) -> str:
        return "qemu-system-aarch64"


CHEFKISS = Backend(
    key="chefkiss",
    name="ChefKiss / Inferno (QEMUAppleSilicon)",
    git_url="https://github.com/ChefKissInc/QEMUAppleSilicon.git",
    default_ref="master",
    notes=(
        "Most active fork; boots iPhone 11 (t8030) iOS 14.x to SpringBoard. "
        "See https://github.com/ChefKissInc/QEMUAppleSilicon/wiki"
    ),
)

TRUNG = Backend(
    key="trung",
    name="TrungNguyen1909/qemu-t8030",
    git_url="https://github.com/TrungNguyen1909/qemu-t8030.git",
    default_ref="master",
    notes=(
        "Original fork; detailed wiki. "
        "See https://github.com/TrungNguyen1909/qemu-t8030/wiki"
    ),
)

BACKENDS: dict[str, Backend] = {
    CHEFKISS.key: CHEFKISS,
    "inferno": CHEFKISS,
    TRUNG.key: TRUNG,
    "trungnguyen": TRUNG,
    "qemu-t8030": TRUNG,
}


def get_backend(key: str) -> Backend:
    b = BACKENDS.get(key.lower())
    if b is None:
        known = ", ".join(sorted({v.key for v in BACKENDS.values()}))
        raise KeyError(f"unknown backend '{key}'. Known: {known}")
    return b
