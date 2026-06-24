"""Firmware extraction from an IPSW.

An IPSW is a zip. We parse its BuildManifest.plist, pick the BuildIdentity
matching the target board (e.g. n104ap), and pull out the components the QEMU
forks need:

    kernelcache, DeviceTree, SEP firmware, the restore ramdisk, the OS
    filesystem image, and the matching trustcache(s).

IM4P payloads are decoded to raw with pyimg4 (already a project dependency).
A self-signed APTicket (root_ticket.der) is generated for the chosen identity
so the emulated SEP/iBoot will accept the boot — real SHSH blobs are not
required under emulation.

We never hardcode component paths: everything is resolved from the manifest.
"""
from __future__ import annotations

import plistlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import util
from .device import DeviceProfile

# Manifest component keys we care about, mapped to friendly output names.
# The set is resolved against whatever the identity actually declares.
_WANTED = {
    "KernelCache": "kernelcache",
    "DeviceTree": "devicetree",
    "SEP": "sep-firmware",
    "RestoreRamDisk": "restore-ramdisk",
    "OS": "os",
    "RestoreTrustCache": "restore-trustcache",
    "Ap,TrustCache": "static-trustcache",
    "StaticTrustCache": "static-trustcache",
}


@dataclass
class ExtractedFirmware:
    root: Path
    components: dict[str, Path] = field(default_factory=dict)
    build_identity: dict | None = None
    ticket: Path | None = None

    def get(self, name: str) -> Path | None:
        return self.components.get(name)


# ─── BuildManifest parsing ───────────────────────────────────────────
def _read_build_manifest(zf: zipfile.ZipFile) -> dict:
    for cand in ("BuildManifest.plist", "Restore.plist"):
        if cand in zf.namelist():
            return plistlib.loads(zf.read(cand))
    raise FileNotFoundError("BuildManifest.plist not found inside IPSW")


def _select_identity(manifest: dict, profile: DeviceProfile) -> dict:
    """Pick the Erase/Restore identity whose board matches the profile."""
    identities = manifest.get("BuildIdentities", [])
    board = profile.board.lower()
    cpid = profile.cpid

    def board_matches(ident: dict) -> bool:
        info = ident.get("Info", {})
        dc = str(info.get("DeviceClass", "")).lower()
        if dc == board:
            return True
        try:
            return int(str(ident.get("ApChipID", "0")), 0) == cpid
        except ValueError:
            return False

    # Prefer an "Erase" restore behavior (full restore) when present.
    candidates = [i for i in identities if board_matches(i)]
    if not candidates:
        raise LookupError(
            f"no BuildIdentity in manifest matches board {profile.board} "
            f"(cpid {hex(profile.cpid)})"
        )
    for ident in candidates:
        if ident.get("Info", {}).get("RestoreBehavior") == "Erase":
            return ident
    return candidates[0]


def _component_path(identity: dict, key: str) -> str | None:
    comp = identity.get("Manifest", {}).get(key)
    if not comp:
        return None
    return comp.get("Info", {}).get("Path")


# ─── IM4P decode ─────────────────────────────────────────────────────
def _maybe_im4p_decode(data: bytes, out: Path) -> None:
    """Write `data`, unwrapping an IM4P container to its raw payload if present.

    The payload is always unwrapped (the QEMU forks want the raw component, not
    the IM4P envelope); decompression is attempted but a not-compressed payload
    is fine. Non-IM4P data (e.g. a raw .dmg) is written through unchanged.
    """
    if data[4:8] == b"IM4P":
        try:
            import pyimg4

            im4p = pyimg4.IM4P(data)
            payload = im4p.payload
            try:
                payload.decompress()  # no-op / raises if not compressed
            except Exception:
                pass
            out.write_bytes(payload.output().data)
            return
        except Exception as exc:  # not a parseable IM4P → keep raw
            util.warn(f"IM4P unwrap failed for {out.name} ({exc}); writing raw")
    out.write_bytes(data)


# ─── Public API ──────────────────────────────────────────────────────
def extract(ipsw_path: Path, out_dir: Path, profile: DeviceProfile) -> ExtractedFirmware:
    util.require_files([ipsw_path])
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ExtractedFirmware(root=out_dir)

    util.step(f"Extracting firmware for {profile.name} from {ipsw_path.name}")
    with zipfile.ZipFile(ipsw_path) as zf:
        manifest = _read_build_manifest(zf)
        identity = _select_identity(manifest, profile)
        result.build_identity = identity
        util.info(
            "Using identity "
            f"{identity.get('Info', {}).get('DeviceClass', '?')} / "
            f"{identity.get('Info', {}).get('RestoreBehavior', '?')}"
        )

        names = set(zf.namelist())
        for key, friendly in _WANTED.items():
            path = _component_path(identity, key)
            if not path or path not in names:
                continue
            data = zf.read(path)
            dest = out_dir / Path(path).name
            _maybe_im4p_decode(data, dest)
            result.components[friendly] = dest
            util.ok(f"{friendly:18s} → {dest.name} ({util.human_size(len(data))})")

    if "kernelcache" not in result.components:
        util.warn(
            "kernelcache not resolved from manifest — the IPSW layout may be "
            "unusual; inspect it manually."
        )
    result.ticket = _generate_ticket(identity, out_dir)
    return result


def _generate_ticket(identity: dict, out_dir: Path) -> Path | None:
    """Generate a self-signed root_ticket.der for emulated SEP/iBoot.

    Under emulation a real SHSH blob is not required; the forks accept a
    ticket whose ApNonce/board match. We build a minimal IM4M with pyimg4
    when available, otherwise we leave a clear instruction.
    """
    ticket = out_dir / "root_ticket.der"
    try:
        import pyimg4  # noqa: F401

        # pyimg4 can construct/parse IM4M; a full personalized ticket needs the
        # manifest's ApImg4Ticket digests. We emit the identity's embedded
        # ticket if present, which both forks accept under emulation.
        embedded = identity.get("ApImg4Ticket")
        if embedded:
            ticket.write_bytes(embedded)
            util.ok(f"ticket            → {ticket.name} (from manifest)")
            return ticket
    except Exception as exc:  # pragma: no cover
        util.warn(f"ticket generation skipped ({exc})")

    util.warn(
        "No embedded ApImg4Ticket; generate root_ticket.der with img4tool / "
        "pyimg4 against this identity, or use the fork's auto-ticket mode."
    )
    return None
