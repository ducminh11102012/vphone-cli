"""vphone-linux — turnkey iOS-on-QEMU orchestrator for Linux.

This package is the Linux counterpart to the macOS `vphone-cli`. Where the
macOS tool drives Apple's Virtualization.framework (which does not exist off
macOS), this tool drives a *software* Apple-silicon emulator (QEMU forks:
ChefKiss/Inferno or TrungNguyen1909/qemu-t8030) so that iOS can be booted on
Linux without any Apple hardware.

Scope (be honest about it):
  * The emulation *core* is the upstream QEMU fork — we do not reimplement it.
  * Our value is orchestration: building the fork, extracting firmware from an
    IPSW, applying the small set of boot patches, assembling the (very long)
    QEMU command line, and managing the VM lifecycle from a single CLI.
  * Target SoC is t8030 (Apple A13 / iPhone 11, board n104ap), iOS 14.x — the
    range the upstream forks actually boot.
"""

__version__ = "0.1.0"
