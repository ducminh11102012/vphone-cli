#!/usr/bin/env bash
# Start the MAIN VM (t8030 / iPhone 11). Start the companion VM FIRST.
#
# MODE=restore  -> boot the Erase ramdisk so the companion can restore (default)
# MODE=boot     -> boot the already-restored OS (after fs-patches) to SpringBoard
set -euo pipefail

ROOT="${INFERNO_ROOT:-$HOME/InfernoData}"
SRC="$ROOT/Inferno"; R="$ROOT/Restore"
MODE="${MODE:-restore}"
export LD_LIBRARY_PATH="$ROOT/prefix/lib:$ROOT/prefix/lib64:${LD_LIBRARY_PATH:-}"
cd "$ROOT"

KC="$R/kernelcache.research.iphone12b"
DTB="$R/Firmware/all_flash/DeviceTree.n104ap.im4p"
# Erase ramdisk = smaller of the two 048-*.dmg; its trustcache lives in Firmware/
RAMDISK="$(ls -1S "$R"/048-*.dmg | tail -1)"
TC="$R/Firmware/$(basename "$RAMDISK").trustcache"
# For a real (encrypted) restore add: sep-rom=<AppleSEPROM-Cebu-B1>,sep-fw=<sep-firmware...new.img4>
MACH="t8030,trustcache=$TC,ticket=$ROOT/root_ticket.der,kaslr-off=true"

DISPLAY_FLAG="${DISPLAY_FLAG:--display gtk,zoom-to-fit=on,show-cursor=on}"
COMMON=(-smp 7 -m 4G $DISPLAY_FLAG -serial mon:stdio
  -drive file=root,format=raw,if=none,id=root          -device nvme-ns,drive=root,bus=nvme-bus.0,nsid=1,nstype=1,logical_block_size=4096,physical_block_size=4096
  -drive file=firmware,format=raw,if=none,id=firmware   -device nvme-ns,drive=firmware,bus=nvme-bus.0,nsid=2,nstype=2,logical_block_size=4096,physical_block_size=4096
  -drive file=syscfg,format=raw,if=none,id=syscfg       -device nvme-ns,drive=syscfg,bus=nvme-bus.0,nsid=3,nstype=3,logical_block_size=4096,physical_block_size=4096
  -drive file=ctrl_bits,format=raw,if=none,id=ctrl_bits -device nvme-ns,drive=ctrl_bits,bus=nvme-bus.0,nsid=4,nstype=4,logical_block_size=4096,physical_block_size=4096
  -drive file=nvram,if=none,format=raw,id=nvram         -device apple-nvram,drive=nvram,bus=nvme-bus.0,nsid=5,nstype=5,id=nvram,logical_block_size=4096,physical_block_size=4096
  -drive file=effaceable,format=raw,if=none,id=effaceable -device nvme-ns,drive=effaceable,bus=nvme-bus.0,nsid=6,nstype=6,logical_block_size=4096,physical_block_size=4096
  -drive file=panic_log,format=raw,if=none,id=panic_log -device nvme-ns,drive=panic_log,bus=nvme-bus.0,nsid=7,nstype=8,logical_block_size=4096,physical_block_size=4096)
APPEND="tlto_us=-1 mtxspin=-1 agm-genuine=1 agm-authentic=1 agm-trusted=1 serial=3 wdt=-1 -vm_compressor_wk_sw"

if [ "$MODE" = restore ]; then
  exec "$SRC/build/qemu-system-aarch64" -M "$MACH" -kernel "$KC" -dtb "$DTB" \
    -append "$APPEND" -initrd "$RAMDISK" "${COMMON[@]}"
else   # boot the restored OS
  exec "$SRC/build/qemu-system-aarch64" -M "$MACH,boot-mode=exit_recovery" \
    -kernel "$KC" -dtb "$DTB" -append "$APPEND" "${COMMON[@]}"
fi
