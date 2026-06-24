# Building the QEMU fork (validated recipe)

This is the exact, **tested-from-scratch** procedure to build the
`TrungNguyen1909/qemu-t8030` fork (QEMU 7.1.0 base) on a clean Ubuntu 24.04
x86_64 box with no `apt` access — every missing piece is built from source.
It was validated end-to-end: the resulting `qemu-system-aarch64` runs and
exposes the `t8030` (iPhone 11) machine, reaching the firmware-load stage.

> The orchestrator's `vphone-linux build` does the git-based version of this
> automatically when it can clone. This doc captures the manual recipe and the
> **source-level fixes** needed when building from a tarball / clean env.

## System packages (present on the box)

`git ninja-build pkg-config gcc cmake make python3` plus dev headers for
`glib-2.0` and `pixman-1`. Install `meson` via `pip` if absent.

## Dependencies built from source (no apt)

| Lib | Why | Source |
| --- | --- | --- |
| **lzfse** | fork decompresses kernelcache/IM4P | `github.com/lzfse/lzfse` (CMake) |
| **libtasn1** | IMG4/ASN.1 parsing (`hw/arm/img4.h`) | `ftp.gnu.org/gnu/libtasn1` (autotools) |

Install both into a local prefix (e.g. `$PREFIX=…/prefix`) and export:

```bash
export CPATH=$PREFIX/include LIBRARY_PATH=$PREFIX/lib
export LD_LIBRARY_PATH=$PREFIX/lib PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig
```

## Submodules (a GitHub tarball ships none)

QEMU's `configure` refuses to build without them. Drop these into the source
tree (download each as an archive if you can't `git submodule update`):

- `ui/keycodemapdb` — **must match the QEMU base version**. For 7.1.0 use
  commit `d21009b1c9f94b740ea66be8e48a1d8ad8124023`. A newer master references
  keycodes the fork's `QKeyCode` enum lacks (see fix below).
- `dtc` — provides libfdt (required by `aarch64-softmmu`); build with
  `--enable-fdt`.
- `tests/fp/berkeley-softfloat-3` and `tests/fp/berkeley-testfloat-3` —
  `tests/fp/meson.build` includes them unconditionally.

## Two source-level fixes required

1. **`qapi/ui.json` — `QKeyCode` is trimmed to `f1`–`f12`.** The generated
   `ui/input-keymap-*.c.inc` references `Q_KEY_CODE_F13`…`F24`, so the build
   fails with "undeclared". Add the missing entries to the enum:

   ```
   'lang1', 'lang2',
   'f13','f14','f15','f16','f17','f18','f19','f20','f21','f22','f23','f24' ] }
   ```

2. **`meson.build` — libtasn1 detection is gated behind gnutls.** The fork
   wraps the `dependency('libtasn1', …)` in `if gnutls.found()`. Without gnutls
   it stays `not_found`, so `hw/arm/xnu.c` fails to link (`undefined reference
   to asn1_*`). Detect it unconditionally:

   ```meson
   tasn1 = dependency('libtasn1', method: 'pkg-config',
                      required: false, kwargs: static_kwargs)
   ```

## Configure + build

```bash
mkdir build && cd build
../configure \
  --target-list=aarch64-softmmu \
  --disable-capstone --enable-lzfse --disable-werror --enable-fdt \
  --with-git-submodules=ignore \
  --meson=$(command -v meson) \
  --extra-cflags=-I$PREFIX/include --extra-ldflags=-L$PREFIX/lib
ninja
```

Verify:

```bash
LD_LIBRARY_PATH=$PREFIX/lib ./qemu-system-aarch64 --version      # QEMU 7.1.0
LD_LIBRARY_PATH=$PREFIX/lib ./qemu-system-aarch64 -M help | grep t8030
```

Point the orchestrator at it:

```bash
ln -s $(pwd)/qemu-system-aarch64 <ws>/qemu-src/build/qemu-system-aarch64
vphone-linux info <ws>      # → qemu: built
```

## What still blocks an actual iOS boot

A built emulator is necessary but not sufficient: booting iOS needs a real
**iOS 14.x IPSW for iPhone12,1** (kernelcache, DeviceTree, SEP, ramdisk,
trustcache, ticket). Without it, `boot` correctly stops at "missing
extracted component(s): kernelcache, devicetree". The IPSW is Apple firmware
you must supply yourself; it is not bundled or downloadable here.
