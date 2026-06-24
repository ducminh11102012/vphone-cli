"""Device (SoC/board) profiles.

Only t8030 (Apple A13) is wired up because that is what the upstream QEMU
forks actually boot. The profile captures the board id and the firmware
component names so the IPSW extractor and the boot-command builder agree on
what to look for.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceProfile:
    key: str                      # short id used on the CLI
    name: str                     # human name
    soc: str                      # SoC name, e.g. t8030
    board: str                    # board config, e.g. n104ap
    machine: str                  # QEMU -M machine type
    cpid: int                     # chip id
    # Firmware component names as they appear in the BuildManifest / IPSW.
    devicetree_glob: str = "DeviceTree.*.im4p"
    sep_fw_glob: str = "sep-firmware.*.im4p"
    # kernelcache flavours the forks accept; "research" boots verbose, the
    # "release" cache is the stock one. We resolve whichever exists.
    kernelcache_globs: tuple[str, ...] = (
        "kernelcache.research.*",
        "kernelcache.release.*",
    )

    def describe(self) -> str:
        return f"{self.key} — {self.name} (SoC {self.soc}, board {self.board}, machine {self.machine})"


# iPhone 11 (iPhone12,1) — N104AP — Apple A13 (t8030).
T8030 = DeviceProfile(
    key="t8030",
    name="iPhone 11",
    soc="t8030",
    board="n104ap",
    machine="t8030",
    cpid=0x8030,
)

PROFILES: dict[str, DeviceProfile] = {
    T8030.key: T8030,
    # aliases
    "iphone11": T8030,
    "n104ap": T8030,
}


def get_profile(key: str) -> DeviceProfile:
    p = PROFILES.get(key.lower())
    if p is None:
        known = ", ".join(sorted({v.key for v in PROFILES.values()}))
        raise KeyError(f"unknown device profile '{key}'. Known: {known}")
    return p
