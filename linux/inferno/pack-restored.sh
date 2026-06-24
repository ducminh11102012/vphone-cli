#!/usr/bin/env bash
# Package a RESTORED disk for one-shot boot, split into upload-friendly parts.
#
#   ./pack-restored.sh <root-disk> [part-size]   # default part size 95M
#
# Produces:  restored-root.tar.zst.part_aa, ...part_ab, ...  + a SHA256SUMS file.
# Reassemble + boot with restore-from-image steps in README.md ("one-shot boot").
#
# IMPORTANT — licensing: a restored disk contains Apple's iOS (kernel, frameworks,
# SpringBoard). It is Apple's copyrighted OS. Do NOT publish it on a public repo
# or release. Keep it private / share only where you have the right to. This
# script is for producing YOUR OWN image for YOUR OWN reuse.
set -euo pipefail
DISK="${1:?usage: $0 <root-disk> [part-size, e.g. 95M]}"
PART="${2:-95M}"
OUT="${OUT:-restored-pack}"
mkdir -p "$OUT"

echo "==> compressing $DISK (sparse-aware) with zstd"
# --sparse keeps unwritten 32G regions cheap; zstd -19 for size, adjust as needed.
tar --sparse -cf - "$DISK" | zstd -19 -T0 -o "$OUT/restored-root.tar.zst"
echo "==> splitting into $PART parts"
( cd "$OUT" && split -b "$PART" restored-root.tar.zst restored-root.tar.zst.part_ \
  && rm -f restored-root.tar.zst && sha256sum restored-root.tar.zst.part_* > SHA256SUMS )
echo "==> done:"; ls -lh "$OUT"
cat <<EOF

Reassemble + boot:
  cat $OUT/restored-root.tar.zst.part_* | zstd -d | tar --sparse -xf -   # -> root
  MODE=boot ./04-run-main-vm.sh                                          # -> SpringBoard
EOF
