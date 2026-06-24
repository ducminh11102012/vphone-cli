"""Networking for the emulated iPhone.

Why this module exists: the t8030 SoC the forks emulate does NOT present a
plain ethernet NIC that iOS will use for general internet. On real hardware
(and in these emulators) iOS reaches the network over USB. So "the VM has no
network" is the default state until USB tethering is bridged out.

Two strategies are supported:

  usb-bridge (default, documented & verified for both forks)
  ─────────────────────────────────────────────────────────
    * The iOS VM exposes its USB controller over a unix socket via the
      `usb-tcp-remote` device — exactly as if an iPhone were plugged into a
      Linux box.
    * A small companion Linux VM connects to that socket as the USB *host*,
      runs usbmuxd + the Apple USB-ethernet (CDC-NCM) interface, gets normal
      internet through QEMU user-mode networking, and NATs the iPhone's
      traffic out. SSH to iOS is reached through the companion.

  user (convenience, fork-dependent)
  ──────────────────────────────────
    * Attach a QEMU user-mode netdev directly to the machine with an SSH
      hostfwd. Only works on forks that expose an in-machine NIC; offered as
      a one-flag convenience when it does.

We never hardcode firmware offsets here; these are QEMU device/netdev option
strings, kept configurable where a fork's exact spelling may differ.
"""
from __future__ import annotations

from pathlib import Path

from .backends import Backend
from .config import Config


# ─── iOS-side networking args ────────────────────────────────────────
def ios_network_args(cfg: Config, workspace: Path) -> list[str]:
    """QEMU args to add to the *iOS* command line for the chosen strategy."""
    if cfg.network == "off":
        return []

    if cfg.network == "user":
        # Direct user-mode networking with SSH port-forward. The machine is
        # expected to wire its NIC to this netdev (fork-dependent).
        return [
            "-netdev",
            f"user,id=net0,hostfwd=tcp:127.0.0.1:{cfg.ssh_host_port}-:22",
        ]

    if cfg.network == "usb-bridge":
        socket_path = workspace / cfg.usb_socket
        # Expose the iOS USB over a unix-socket chardev, then attach the
        # remote-USB bridge device to it. The companion VM connects here.
        return [
            "-chardev", f"socket,id=usbcdc,path={socket_path},server=on,wait=off",
            "-device", "usb-ehci,id=ehci",
            "-device", f"{cfg.usb_bridge_device},bus=ehci.0,chardev=usbcdc",
        ]

    raise ValueError(
        f"unknown network mode '{cfg.network}' (use: usb-bridge | user | off)"
    )


def describe(cfg: Config) -> str:
    if cfg.network == "off":
        return "networking: off"
    if cfg.network == "user":
        return f"networking: user-mode (SSH → 127.0.0.1:{cfg.ssh_host_port})"
    return (
        f"networking: usb-bridge via {cfg.usb_socket} "
        f"(needs `vphone-linux companion`); SSH → 127.0.0.1:{cfg.ssh_host_port}"
    )


# ─── companion VM command ────────────────────────────────────────────
def companion_argv(cfg: Config, workspace: Path, qemu_x86: str | None = None) -> list[str]:
    """Build the companion Linux VM command that bridges iOS USB → internet.

    The companion is a normal Linux guest: it needs a bootable disk image
    (cfg.companion_image). It connects to the same USB socket as the USB
    *host* side and forwards the iPhone's SSH (22) out to the host.
    """
    socket_path = workspace / cfg.usb_socket
    binary = qemu_x86 or "qemu-system-x86_64"
    if not cfg.companion_image:
        raise ValueError(
            "network = usb-bridge needs a companion Linux image. Set "
            "companion_image in vphone-linux.toml (a small distro that runs "
            "usbmuxd; see linux/NETWORKING.md)."
        )

    argv = [binary, "-m", f"{cfg.companion_memory_mb}M", "-smp", str(cfg.companion_cpus)]
    # acceleration if available (host x86 KVM); harmless to request, QEMU
    # falls back to TCG. We leave accel to the user's QEMU default to stay
    # portable, but enable it via env if they want it.
    argv += ["-drive", f"file={cfg.companion_image},format=qcow2,if=virtio"]
    if cfg.companion_kernel:
        argv += ["-kernel", cfg.companion_kernel, "-append", "root=/dev/vda console=ttyS0"]
    # user-mode networking out to the internet, plus expose iOS SSH (tunnelled
    # inside the companion to localhost:22 of the phone) to the host.
    argv += [
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{cfg.ssh_host_port}-:10222",
        "-device", "virtio-net-pci,netdev=net0",
    ]
    # USB *host* side: connect to the iOS-exposed socket. usb-tcp-host is the
    # companion-side counterpart of usb-tcp-remote.
    argv += [
        "-chardev", f"socket,id=usbcdc,path={socket_path},server=off",
        "-device", "usb-ehci,id=ehci",
        "-device", "usb-tcp-host,bus=ehci.0,chardev=usbcdc",
    ]
    argv += ["-serial", "mon:stdio"]
    return argv
