"""NVMe namespace + NVRAM image management.

The t8030 machine expects a set of raw NVMe namespace images and an NVRAM
image. Namespace 1 is the main user/data storage; the rest are small system
namespaces (effaceable, syscfg, etc.). We create sparse raw files so the
workspace stays small until iOS writes to them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import util


@dataclass(frozen=True)
class Namespace:
    nsid: int
    nstype: int
    filename: str
    size_mb: int
    is_nvram: bool = False


# Layout mirrors the documented t8030 invocation: 7 NVMe namespaces + nvram on
# nsid 5. Namespace 1 holds the filesystem; size it generously, others small.
def default_layout(main_size_gb: int = 16) -> list[Namespace]:
    return [
        Namespace(1, 1, "nvme.1", main_size_gb * 1024),
        Namespace(2, 2, "nvme.2", 8),
        Namespace(3, 3, "nvme.3", 8),
        Namespace(4, 4, "nvme.4", 8),
        Namespace(5, 5, "nvram", 1, is_nvram=True),
        Namespace(6, 6, "nvme.6", 8),
        Namespace(7, 8, "nvme.7", 8),
    ]


def ensure_images(disks_dir: Path, layout: list[Namespace]) -> None:
    disks_dir.mkdir(parents=True, exist_ok=True)
    for ns in layout:
        path = disks_dir / ns.filename
        if path.exists():
            continue
        # sparse allocation: create then truncate to size
        with open(path, "wb") as f:
            f.truncate(ns.size_mb * 1024 * 1024)
        util.ok(f"created {ns.filename} ({ns.size_mb} MiB, sparse)")


def reset_images(disks_dir: Path, layout: list[Namespace]) -> None:
    """Delete namespace images so the next boot starts from a clean restore."""
    for ns in layout:
        path = disks_dir / ns.filename
        if path.exists():
            path.unlink()
            util.info(f"removed {ns.filename}")
