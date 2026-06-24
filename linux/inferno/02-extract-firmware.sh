#!/usr/bin/env bash
# Extract the firmware components Inferno needs from an iOS 14.0 iPhone12,1 IPSW,
# create the disk set, and forge the AP ticket.
#
# Usage: ./02-extract-firmware.sh <IPSW>
set -euo pipefail

ROOT="${INFERNO_ROOT:-$HOME/InfernoData}"
SRC="$ROOT/Inferno"
IPSW="${1:?usage: $0 <path-to-iPhone12,1_14.0_Restore.ipsw>}"
cd "$ROOT"

echo "==> Extract IPSW"
mkdir -p Restore && (cd Restore && unzip -o "$IPSW" >/dev/null)

echo "==> Disk set (sparse raw), per file-setup"
QIMG="$SRC/build/qemu-img"
for spec in root:32G firmware:8M syscfg:128K ctrl_bits:8K nvram:8K effaceable:4K panic_log:1M sep_nvram:64K sep_ssc:128K; do
  f="${spec%%:*}"; s="${spec##*:}"; [ -f "$f" ] || "$QIMG" create -f raw "$f" "$s" >/dev/null
done

echo "==> Forge AP ticket (iOS 14.0 is unsigned)"
# Official method (needs pyasn1/pyasn1-modules + create_apticket.py from the guide):
#   python3 create_apticket.py n104ap Restore/BuildManifest.plist ticket.shsh2 root_ticket.der
# The emulator only hashes the ticket into the DeviceTree boot-manifest-hash, so
# for a sim-SEP ramdisk boot the BuildManifest bytes also suffice as a fallback:
[ -f root_ticket.der ] || cp Restore/BuildManifest.plist root_ticket.der

echo "==> Components present in Restore/:"
ls -1 Restore/kernelcache.research.iphone12b \
      Restore/Firmware/all_flash/DeviceTree.n104ap.im4p \
      Restore/Firmware/all_flash/sep-firmware.n104.RELEASE.im4p 2>/dev/null || true
echo "Erase ramdisk = the SMALLER of the two 048-*.dmg in Restore/ (+ its .trustcache in Restore/Firmware/)"
ls -lhS Restore/048-*.dmg 2>/dev/null || true
