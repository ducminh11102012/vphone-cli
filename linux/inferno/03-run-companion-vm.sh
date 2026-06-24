#!/usr/bin/env bash
# Start the COMPANION VM (x86_64 Linux) that drives the restore. It must be
# started BEFORE the main VM, otherwise no USB connection is established.
#
# Prereqs: a lightweight Linux install (Arch/Artix, no DE) in companion.qcow2 with
# the libimobiledevice stack built (see 03b-setup-companion-tools.sh, run inside it).
set -euo pipefail

ROOT="${INFERNO_ROOT:-$HOME/InfernoData}"
SRC="$ROOT/Inferno"
DISK="${COMPANION_DISK:-$ROOT/companion.qcow2}"
ACCEL="${ACCEL:-kvm}"   # use 'tcg' if no KVM (much slower); 'kvm' strongly recommended

export LD_LIBRARY_PATH="$ROOT/prefix/lib:$ROOT/prefix/lib64:${LD_LIBRARY_PATH:-}"

exec "$SRC/build/qemu-system-x86_64" \
  -M q35 -accel "$ACCEL" -m 2G -smp 4 \
  -usb -device usb-ehci,id=ehci -device usb-tcp-remote,bus=ehci.0 \
  -drive file="$DISK",if=virtio,format=qcow2 \
  -nic user,model=virtio-net-pci,hostfwd=tcp::32222-:22 \
  -display none -serial mon:stdio
# usb-tcp-remote defaults to the /tmp/InfernoUSBRemote unix socket (matches main VM default).
