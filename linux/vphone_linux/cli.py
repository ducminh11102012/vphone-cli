"""vphone-linux command-line interface.

A single entrypoint that takes you from a fresh checkout to a booting iOS VM
on Linux:

    vphone-linux init          # create a workspace + config
    vphone-linux doctor        # check build/runtime prerequisites
    vphone-linux build         # clone + build the chosen QEMU fork
    vphone-linux fetch IPSW    # extract firmware (kernel/dtb/sep/ramdisk/...)
    vphone-linux restore       # first-time restore into the NVMe images
    vphone-linux boot          # boot the installed system
    vphone-linux plan          # print the QEMU command without running it
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import bootcmd, disks, display, ipsw, network, qemu_build, runner, util
from .backends import get_backend
from .config import Config
from .device import get_profile

app = typer.Typer(
    add_completion=False,
    help="Turnkey iOS-on-QEMU orchestrator for Linux (vphone-cli's Linux sibling).",
    no_args_is_help=True,
)


def _load_cfg(workspace: Path) -> Config:
    try:
        return Config.load(workspace)
    except FileNotFoundError as exc:
        util.err(str(exc))
        raise typer.Exit(2)


def _resolve(workspace: Path):
    cfg = _load_cfg(workspace)
    backend = get_backend(cfg.backend)
    profile = get_profile(cfg.device)
    return cfg, backend, profile


# ─── init ────────────────────────────────────────────────────────────
@app.command()
def init(
    workspace: Path = typer.Argument(..., help="Workspace directory to create"),
    backend: str = typer.Option("chefkiss", help="QEMU fork: chefkiss | trung"),
    device: str = typer.Option("t8030", help="Device profile (iPhone 11 = t8030)"),
    cpus: int = typer.Option(4),
    memory_mb: int = typer.Option(4096),
    net: str = typer.Option("usb-bridge", help="network mode: usb-bridge | user | off"),
    ssh_port: int = typer.Option(2222, help="host port forwarded to guest SSH"),
    disp: str = typer.Option("auto", "--display", help="display: auto|gtk|sdl|cocoa|egl-headless|vnc|none"),
    gl: str = typer.Option("on", help="host-GPU OpenGL presentation: on | off"),
    vnc: int = typer.Option(0, help="VNC display number (>0 enables VNC, overrides --display)"),
    tcg_thread: str = typer.Option("single", help="TCG threading: single | multi (MTTCG, opt-in)"),
    tb_size_mb: int = typer.Option(256, help="TCG translation-block cache size (MiB)"),
):
    """Create a workspace and write its config."""
    be = get_backend(backend)
    prof = get_profile(device)
    cfg = Config(
        backend=be.key, device=prof.key, cpus=cpus, memory_mb=memory_mb,
        network=net, ssh_host_port=ssh_port,
        display=disp, gl=gl, vnc_display=vnc,
        tcg_thread=tcg_thread, tb_size_mb=tb_size_mb,
    )
    cfg.save(workspace)
    for d in Config.workspace_dirs().values():
        (workspace / d).mkdir(parents=True, exist_ok=True)
    util.ok(f"workspace ready at {workspace}")
    util.info(f"backend: {be.name}")
    util.info(f"device:  {prof.describe()}")
    util.info(network.describe(cfg))
    util.info(display.describe(cfg))
    util.dim(be.notes)


# ─── doctor ──────────────────────────────────────────────────────────
@app.command()
def doctor(workspace: Optional[Path] = typer.Argument(None)):
    """Check build/runtime prerequisites."""
    backend = get_backend(Config.load(workspace).backend) if workspace and (workspace / "vphone-linux.toml").exists() else get_backend("chefkiss")
    ok = runner.doctor(workspace, backend)
    raise typer.Exit(0 if ok else 1)


# ─── build ───────────────────────────────────────────────────────────
@app.command()
def build(
    workspace: Path = typer.Argument(...),
    jobs: Optional[int] = typer.Option(None, "-j", help="parallel make jobs"),
):
    """Clone and build the selected QEMU fork."""
    cfg, backend, _ = _resolve(workspace)
    qemu_build.build(workspace, backend, cfg, jobs)


# ─── fetch / extract firmware ─────────────────────────────────────────
@app.command()
def fetch(
    workspace: Path = typer.Argument(...),
    ipsw_file: Path = typer.Argument(..., help="Path to the IPSW"),
):
    """Extract kernel/devicetree/sep/ramdisk/trustcache from an IPSW."""
    cfg, _, profile = _resolve(workspace)
    fw_dir = workspace / Config.workspace_dirs()["firmware"]
    fw = ipsw.extract(ipsw_file, fw_dir, profile)
    util.ok(f"extracted {len(fw.components)} component(s) → {fw_dir}")


# ─── prepare disks ────────────────────────────────────────────────────
@app.command()
def prepare(
    workspace: Path = typer.Argument(...),
    main_gb: int = typer.Option(16, help="size of the main NVMe namespace"),
):
    """Create the NVMe namespace + NVRAM images."""
    disks_dir = workspace / Config.workspace_dirs()["disks"]
    disks.ensure_images(disks_dir, disks.default_layout(main_gb))


def _make_plan(workspace: Path, restore: bool, main_gb: int) -> bootcmd.BootPlan:
    cfg, backend, profile = _resolve(workspace)
    binary = qemu_build.qemu_binary_path(workspace, backend)
    util.require_files([binary])
    fw_dir = workspace / Config.workspace_dirs()["firmware"]
    fw = ipsw.ExtractedFirmware(root=fw_dir)
    # re-discover already-extracted components by friendly name
    for friendly, pattern in {
        "kernelcache": "kernelcache*",
        "devicetree": "DeviceTree*",
        "sep-firmware": "sep-firmware*",
        "restore-ramdisk": "*ramdisk*",
        "os": "*.dmg",
        "static-trustcache": "*trustcache*",
    }.items():
        hits = sorted(fw_dir.glob(pattern))
        if hits:
            fw.components[friendly] = hits[0]
    t = fw_dir / "root_ticket.der"
    fw.ticket = t if t.exists() else None
    layout = disks.default_layout(main_gb)
    disks.ensure_images(workspace / Config.workspace_dirs()["disks"], layout)
    return bootcmd.build(
        workspace=workspace, backend=backend, profile=profile, cfg=cfg,
        fw=fw, layout=layout, qemu_binary=binary, restore=restore,
    )


# ─── plan (dry run) ───────────────────────────────────────────────────
@app.command()
def plan(
    workspace: Path = typer.Argument(...),
    restore: bool = typer.Option(False, help="show the restore command instead of boot"),
    main_gb: int = typer.Option(16),
):
    """Print the QEMU command line without running it."""
    p = _make_plan(workspace, restore, main_gb)
    util.step(p.description)
    print(p.pretty())


# ─── restore ──────────────────────────────────────────────────────────
@app.command()
def restore(workspace: Path = typer.Argument(...), main_gb: int = typer.Option(16)):
    """First-time restore: install iOS into the NVMe namespaces."""
    p = _make_plan(workspace, restore=True, main_gb=main_gb)
    logs = workspace / Config.workspace_dirs()["logs"]
    raise typer.Exit(runner.run_plan(p, logs, "restore.log"))


# ─── boot ─────────────────────────────────────────────────────────────
@app.command()
def boot(workspace: Path = typer.Argument(...), main_gb: int = typer.Option(16)):
    """Boot the already-restored system."""
    p = _make_plan(workspace, restore=False, main_gb=main_gb)
    logs = workspace / Config.workspace_dirs()["logs"]
    raise typer.Exit(runner.run_plan(p, logs, "boot.log"))


# ─── companion (networking bridge VM) ─────────────────────────────────
@app.command()
def companion(
    workspace: Path = typer.Argument(...),
    qemu: Optional[str] = typer.Option(None, help="x86_64 QEMU binary (default: system qemu-system-x86_64)"),
    dry_run: bool = typer.Option(False, help="print the command instead of running"),
):
    """Run the companion Linux VM that gives the iPhone internet (usb-bridge mode).

    Start this BEFORE `boot`/`restore` when network = usb-bridge: the iOS VM
    exposes its USB on a socket and the companion bridges it to the internet.
    """
    cfg, _, _ = _resolve(workspace)
    if cfg.network != "usb-bridge":
        util.warn(f"network mode is '{cfg.network}', companion only applies to usb-bridge")
        raise typer.Exit(1)
    try:
        argv = network.companion_argv(cfg, workspace, qemu)
    except ValueError as exc:
        util.err(str(exc))
        raise typer.Exit(2)
    if dry_run:
        print(" \\\n    ".join(argv))
        return
    logs = workspace / Config.workspace_dirs()["logs"]
    raise typer.Exit(runner.run_plan(bootcmd.BootPlan(argv=argv, description="Companion bridge VM"), logs, "companion.log"))


# ─── ssh helper ───────────────────────────────────────────────────────
@app.command()
def ssh(workspace: Path = typer.Argument(...)):
    """Print the SSH command to reach the booted iPhone."""
    cfg, _, _ = _resolve(workspace)
    if cfg.network == "off":
        util.err("networking is off; enable usb-bridge or user mode first")
        raise typer.Exit(1)
    util.info(network.describe(cfg))
    print(f"ssh -p {cfg.ssh_host_port} root@127.0.0.1   # password: alpine")


# ─── clean ────────────────────────────────────────────────────────────
@app.command()
def clean(
    workspace: Path = typer.Argument(...),
    disks_only: bool = typer.Option(True, help="only wipe NVMe images (keep build/firmware)"),
    main_gb: int = typer.Option(16),
):
    """Reset NVMe images so the next restore starts clean."""
    if disks_only:
        disks.reset_images(workspace / Config.workspace_dirs()["disks"], disks.default_layout(main_gb))
        util.ok("disk images reset")


# ─── gui ──────────────────────────────────────────────────────────────
@app.command()
def gui(
    workspace: Optional[Path] = typer.Argument(None, help="workspace to preload"),
    port: int = typer.Option(8723, help="local port"),
    host: str = typer.Option("127.0.0.1"),
    no_browser: bool = typer.Option(False, "--no-browser", help="don't auto-open the browser"),
):
    """Launch the local web GUI (point-and-click, no commands)."""
    from . import webgui

    webgui.serve(str(workspace) if workspace else "", host=host, port=port, open_browser=not no_browser)


# ─── info ─────────────────────────────────────────────────────────────
@app.command()
def info(workspace: Path = typer.Argument(...)):
    """Show workspace configuration and state."""
    cfg, backend, profile = _resolve(workspace)
    util.step("Workspace")
    util.info(f"path:    {workspace}")
    util.info(f"backend: {backend.name}")
    util.info(f"device:  {profile.describe()}")
    util.info(f"cpus={cfg.cpus} memory={cfg.memory_mb}MiB gdb={cfg.gdb_stub}")
    util.info(network.describe(cfg))
    util.info(display.describe(cfg))
    built = qemu_build.qemu_binary_path(workspace, backend)
    (util.ok if built.exists() else util.warn)(
        f"qemu: {'built' if built.exists() else 'not built'} ({built})"
    )
    fw_dir = workspace / Config.workspace_dirs()["firmware"]
    comps = sorted(p.name for p in fw_dir.glob("*")) if fw_dir.exists() else []
    util.info(f"firmware: {len(comps)} file(s)")
    for c in comps:
        util.dim(f"    {c}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
