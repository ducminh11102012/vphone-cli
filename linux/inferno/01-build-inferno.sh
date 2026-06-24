#!/usr/bin/env bash
# Build the ChefKiss Inferno QEMU fork (aarch64 main VM + x86_64 companion VM)
# from scratch on a clean Linux x86_64 box with no apt access — every missing
# dependency is built from source into a local prefix.
#
# Validated end-to-end in a clean container up to the Apple-logo boot stage.
set -euo pipefail

ROOT="${INFERNO_ROOT:-$HOME/InfernoData}"
PREFIX="$ROOT/prefix"
SRC="$ROOT/Inferno"
JOBS="$(nproc)"
mkdir -p "$ROOT" "$PREFIX"

dl() { curl -fsSL "$1" -o "$2"; }   # add --cacert <bundle> behind a TLS proxy

echo "==> [1/5] Build dependency libraries into $PREFIX"
cd "$ROOT"
# lzfse — kernelcache/IM4P decompression
[ -f "$PREFIX/include/lzfse.h" ] || {
  dl https://codeload.github.com/lzfse/lzfse/tar.gz/refs/heads/master lzfse.tgz
  tar xf lzfse.tgz; ( cd lzfse-master && cmake -S . -B b -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_BUILD_TYPE=Release >/dev/null && cmake --build b -j"$JOBS" >/dev/null && cmake --install b >/dev/null )
}
# gmp -> nettle (>=3.10) for SEP crypto (SHA-384 etc.)
[ -f "$PREFIX/include/gmp.h" ] || {
  dl https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz gmp.txz; tar xf gmp.txz
  ( cd gmp-6.3.0 && ./configure --prefix="$PREFIX" --enable-shared >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null )
}
[ -f "$PREFIX/include/nettle/drbg-ctr.h" ] || {
  dl https://ftp.gnu.org/gnu/nettle/nettle-3.10.2.tar.gz nettle.tgz; tar xf nettle.tgz
  ( cd nettle-3.10.2 && CPPFLAGS="-I$PREFIX/include" LDFLAGS="-L$PREFIX/lib" \
    ./configure --prefix="$PREFIX" --enable-shared --disable-documentation >/dev/null \
    && make -j"$JOBS" >/dev/null && make install >/dev/null )
}
# libtasn1 — IMG4/ASN.1
[ -f "$PREFIX/include/libtasn1.h" ] || {
  dl https://ftp.gnu.org/gnu/libtasn1/libtasn1-4.19.0.tar.gz tasn1.tgz; tar xf tasn1.tgz
  ( cd libtasn1-4.19.0 && ./configure --prefix="$PREFIX" --disable-doc >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null )
}

echo "==> [2/5] Fetch Inferno source"
[ -d "$SRC" ] || {
  # Preferred: git clone https://github.com/ChefKissInc/Inferno && git submodule update --init
  dl https://codeload.github.com/ChefKissInc/QEMUAppleSilicon/tar.gz/refs/heads/master inferno.tgz
  tar xf inferno.tgz; mv Inferno-master "$SRC" 2>/dev/null || mv QEMUAppleSilicon-master "$SRC"
}

echo "==> [3/5] Provide the util/mlib submodule (tarballs ship no submodules)"
if [ ! -f "$SRC/util/mlib/m-algo.h" ]; then
  MSHA="$(curl -fsSL https://api.github.com/repos/ChefKissInc/Inferno/contents/util/mlib?ref=master | python3 -c 'import sys,json;print(json.load(sys.stdin)["sha"])')"
  dl "https://codeload.github.com/P-p-H-d/mlib/tar.gz/$MSHA" mlib.tgz
  tar xf mlib.tgz; rm -rf "$SRC/util/mlib"; mv "mlib-$MSHA" "$SRC/util/mlib"
fi

echo "==> [4/5] Use simulated SEP (no copyrighted SEP-ROM needed)"
# t8030.c:2972 — with sep-rom unset and ENABLE_DATA_ENCRYPTION off, the machine
# uses create_sep_sim(); the Data volume is simply left unencrypted.
sed -i 's@^#define ENABLE_DATA_ENCRYPTION@//#define ENABLE_DATA_ENCRYPTION /* simulated SEP */@' \
  "$SRC/include/hw/arm/apple-silicon/boot.h" || true

echo "==> [5/5] configure + build (aarch64 main + x86_64 companion targets)"
export CPATH="$PREFIX/include"
export LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib64"
export LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib64"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$PREFIX/lib64/pkgconfig"
mkdir -p "$SRC/build"; cd "$SRC/build"
../configure --target-list=aarch64-softmmu,x86_64-softmmu \
  --enable-lzfse --enable-nettle --disable-werror \
  --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib -L$PREFIX/lib64"
ninja
echo "Done: $SRC/build/qemu-system-aarch64  +  qemu-system-x86_64"
