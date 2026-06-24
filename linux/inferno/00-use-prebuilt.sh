#!/usr/bin/env bash
# Skip the build entirely: unpack the prebuilt Inferno QEMU binaries into the
# layout the run scripts expect. After this you can go straight to
# 02-extract-firmware.sh and 04-run-main-vm.sh — no compiler needed.
#
# Prebuilt target: Linux x86_64, glibc >= 2.38 (Ubuntu 24.04+, Debian 13+,
# Fedora 38+, recent Arch). System libs still required: glib-2.0, pixman-1,
# gio-2.0 (and libslirp/libssh if you use those features). On older distros,
# build from source with 01-build-inferno.sh instead.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${INFERNO_ROOT:-$HOME/InfernoData}"
TARBALL="$HERE/prebuilt/inferno-qemu-prebuilt-linux-x86_64.tar.xz"

mkdir -p "$ROOT/Inferno/build" "$ROOT/prefix/lib"
tmp="$(mktemp -d)"; tar -C "$tmp" -xf "$TARBALL"
cp "$tmp"/bin/* "$ROOT/Inferno/build/"
cp "$tmp"/lib/* "$ROOT/prefix/lib/"
rm -rf "$tmp"
chmod +x "$ROOT/Inferno/build/"qemu-*

echo "Prebuilt installed:"
LD_LIBRARY_PATH="$ROOT/prefix/lib" "$ROOT/Inferno/build/qemu-system-aarch64" --version | head -1
echo "  main VM:      $ROOT/Inferno/build/qemu-system-aarch64"
echo "  companion VM: $ROOT/Inferno/build/qemu-system-x86_64"
echo "Next: ./02-extract-firmware.sh <IPSW>   then   MODE=restore ./04-run-main-vm.sh"
