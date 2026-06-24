"""Assemble the (very long) QEMU command line for restore and boot.

This is the heart of the orchestrator: it turns a workspace + extracted
firmware + config into a correct `qemu-system-aarch64` argv, so the user
never has to hand-write the 40-flag invocation. The structure follows the
documented t8030 command line; per-backend quirks are funnelled through the
Backend object.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .backends import Backend
from .config import Config
from .device import DeviceProfile
from .disks import Namespace
from .ipsw import ExtractedFirmware
from . import network, util


@dataclass
class BootPlan:
    argv: list[str]
    description: str

    def pretty(self) -> str:
        # one flag per line, line-continued — readable + copy-pasteable
        out = [self.argv[0]]
        i = 1
        while i < len(self.argv):
            tok = self.argv[i]
            if tok.startswith("-") and i + 1 < len(self.argv) and not self.argv[i + 1].startswith("-"):
                out.append(f"{tok} {self.argv[i + 1]}")
                i += 2
            else:
                out.append(tok)
                i += 1
        return " \\\n    ".join(out)


def _nvme_args(disks_dir: Path, layout: list[Namespace], bus: str = "nvme-bus.0") -> list[str]:
    args: list[str] = []
    for ns in layout:
        drive_id = f"nvram" if ns.is_nvram else f"drive.{ns.nsid}"
        path = disks_dir / ns.filename
        args += ["-drive", f"file={path},format=raw,if=none,id={drive_id}"]
        if ns.is_nvram:
            args += [
                "-device",
                f"apple-nvram,drive=nvram,bus={bus},nsid={ns.nsid},nstype={ns.nstype},"
                f"id=nvram,logical_block_size=4096,physical_block_size=4096",
            ]
        else:
            args += [
                "-device",
                f"nvme-ns,drive={drive_id},bus={bus},nsid={ns.nsid},nstype={ns.nstype},"
                f"logical_block_size=4096,physical_block_size=4096",
            ]
    return args


def _machine_arg(
    backend: Backend,
    profile: DeviceProfile,
    fw: ExtractedFirmware,
    *,
    restore: bool,
) -> str:
    opts = [profile.machine]
    tc = fw.get("static-trustcache") or fw.get("restore-trustcache")
    if tc:
        opts.append(f"trustcache-filename={tc}")
    if fw.ticket:
        opts.append(f"ticket-filename={fw.ticket}")
    if not restore:
        # manual boot from an installed system rather than auto-restore
        opts.append("boot-mode=manual")
    opts += list(backend.extra_machine_opts)
    return ",".join(opts)


def build(
    *,
    workspace: Path,
    backend: Backend,
    profile: DeviceProfile,
    cfg: Config,
    fw: ExtractedFirmware,
    layout: list[Namespace],
    qemu_binary: Path,
    restore: bool,
) -> BootPlan:
    dirs = Config.workspace_dirs()
    disks_dir = workspace / dirs["disks"]

    kernel = fw.get("kernelcache")
    dtb = fw.get("devicetree")
    ramdisk = fw.get("restore-ramdisk") if restore else fw.get("os")
    missing = [n for n, p in (("kernelcache", kernel), ("devicetree", dtb)) if p is None]
    if missing:
        raise util.CommandError(
            f"cannot build boot command — missing extracted component(s): {', '.join(missing)}"
        )

    boot_args = cfg.boot_args
    if restore and "rd=md0" not in boot_args:
        # restore boots from the ramdisk
        boot_args = boot_args
    argv: list[str] = [str(qemu_binary)]
    if cfg.gdb_stub:
        argv.append("-s")
    argv += ["-M", _machine_arg(backend, profile, fw, restore=restore)]
    argv += ["-kernel", str(kernel)]
    argv += ["-dtb", str(dtb)]
    argv += ["-append", boot_args]
    if ramdisk:
        argv += ["-initrd", str(ramdisk)]
    argv += ["-cpu", "max", "-smp", str(cfg.cpus)]
    argv += ["-m", f"{cfg.memory_mb // 1024}G" if cfg.memory_mb % 1024 == 0 else f"{cfg.memory_mb}M"]
    argv += ["-serial", "mon:stdio"]
    argv += _nvme_args(disks_dir, layout)
    argv += network.ios_network_args(cfg, workspace)
    if cfg.monitor_telnet_port:
        argv += ["-monitor", f"telnet:127.0.0.1:{cfg.monitor_telnet_port},server,nowait"]

    desc = (
        f"{'RESTORE' if restore else 'BOOT'} {profile.name} via {backend.name} "
        f"({cfg.cpus} CPU, {cfg.memory_mb} MiB) — {network.describe(cfg)}"
    )
    return BootPlan(argv=argv, description=desc)
