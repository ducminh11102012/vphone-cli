# Inferno (ChefKiss QEMUAppleSilicon) — iOS 14 to SpringBoard runbook

Validated-from-scratch notes for emulating an iPhone 11 (`t8030`) on Linux
x86_64 with the [ChefKissInc/Inferno](https://github.com/ChefKissInc/Inferno)
QEMU fork. This captures what was actually reproduced in a clean container and
— honestly — where the wall to SpringBoard is.

## What is reproducible without any Apple ROM dumps

Building the emulator and booting iOS 14.0's restore ramdisk to the Apple-logo
boot screen needs **only** the open-source fork + a public IPSW. Verified end
to end:

1. **Build deps from source** into a local `$PREFIX` (no apt):
   - `lzfse` (CMake) — kernelcache/IM4P decompression
   - `gmp` (autotools) — needed by nettle
   - `nettle` ≥ 3.10 (autotools) — SEP crypto; installs into `$PREFIX/lib64`
   - `libtasn1` (autotools) — IMG4/ASN.1
   - Export before configuring Inferno:
     ```
     export CPATH=$PREFIX/include
     export LIBRARY_PATH=$PREFIX/lib:$PREFIX/lib64
     export LD_LIBRARY_PATH=$PREFIX/lib:$PREFIX/lib64
     export PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig:$PREFIX/lib64/pkgconfig
     ```
2. **Source tree fix-ups** when building from a GitHub tarball (ships no submodules):
   - `util/mlib` submodule — fetch `P-p-H-d/mlib` at the commit Inferno pins
     (resolve via the GitHub contents API on `util/mlib`), drop it in place.
   - Rust toolchain (`rustc`/`cargo`) must be present; QEMU 10.2 has Rust subprojects.
   - glib ≥ 2.80 provides the SHA-384 hash backend, so the older crypto-backend
     gap that hit the QEMU-7.1 fork does not apply here.
3. **configure + ninja**:
   ```
   ../configure --target-list=aarch64-softmmu,x86_64-softmmu \
     --enable-lzfse --enable-nettle --disable-werror \
     --extra-cflags="-I$PREFIX/include" \
     --extra-ldflags="-L$PREFIX/lib -L$PREFIX/lib64"
   ninja
   ```
   > Build **both** `aarch64-softmmu` (main iPhone VM) and `x86_64-softmmu`
   > (companion VM — see below). This runbook's earlier pass only built aarch64.
4. **Extract from the IPSW** (`iPhone12,1` 14.0, build 18A373 release works; it
   ships `kernelcache.research.iphone12b`, which the restore command wants):
   - `kernelcache.research.iphone12b`
   - `Firmware/all_flash/DeviceTree.n104ap.im4p`
   - `Firmware/all_flash/sep-firmware.n104.RELEASE.im4p`
   - Erase ramdisk = smaller of the two `048-*.dmg` + its `.trustcache`
   - OS dmg = `038-*.dmg` (kept for the companion only)
5. **Forge the AP ticket**: iOS 14.0 is unsigned, so a ticket is forged. The
   emulator only *hashes* the ticket into the DeviceTree `boot-manifest-hash`;
   it does not verify the signature, so a stable byte blob suffices for the
   ramdisk boot. (The official guide forges a proper one with `create_apticket.py`
   + `pyasn1`; do that for a real restore.)
6. **Disk set** (sparse raw): `root 32G, firmware 8M, syscfg 128K, ctrl_bits 8K,
   nvram 8K, effaceable 4K, panic_log 1M, sep_nvram 64K, sep_ssc 128K`.
7. **Boot to the Apple logo** (no SEP ROM needed if `ENABLE_DATA_ENCRYPTION` is
   commented out in `include/hw/arm/apple-silicon/boot.h` → simulated SEP):
   ```
   qemu-system-aarch64 -M t8030,trustcache=<048>.trustcache,ticket=root_ticket.der,kaslr-off=true \
     -kernel kernelcache.research.iphone12b -dtb DeviceTree.n104ap.im4p \
     -append "tlto_us=-1 mtxspin=-1 agm-genuine=1 agm-authentic=1 agm-trusted=1 serial=3 wdt=-1 -vm_compressor_wk_sw" \
     -initrd <048-erase>.dmg -smp 4 -m 4G -serial mon:stdio -display none \
     -monitor unix:/tmp/mon.sock,server,nowait \
     -drive file=root,...nsid=1 ... (full nvme-ns/apple-nvram set per file-setup)
   ```
   Serial reaches `restored_external ... waiting for host to trigger start of
   restore`; the framebuffer (828×1792) shows the Apple logo + progress bar.
   Capture with HMP `screendump out.ppm` over the monitor socket.

## The wall: getting from the Apple logo to SpringBoard

Per the official ChefKiss guide (`chefkiss.dev/guides/inferno/...`), a real
restore — the only way to a booted OS / SpringBoard — additionally requires
**three things this clean Linux container cannot satisfy on its own**:

1. **Apple SEP ROM + SecureROM dumps.** The restore boot command needs
   `sep-rom=AppleSEPROM-Cebu-B1` (and SecureROM). These are dumped from real
   hardware and are copyrighted Apple firmware (hosted on third-party dump
   sites). Simulated SEP cannot do the encrypted-data-partition restore — the
   emulator aborts with *"Simulated SEP cannot be used with data encryption."*
   So real ROM dumps are mandatory for a real restore.
2. **A companion VM.** Inferno does the actual restore over a USB-over-TCP
   bridge: the main VM connects (as a client) to a Unix socket
   `/tmp/InfernoUSBRemote` (`hw/usb/tcp-usb.h`), and a **second** VM —
   `qemu-system-x86_64` running a normal Linux with
   `-device usb-tcp-remote,bus=ehci.0` — presents the iPhone as a real USB
   device to host-side `idevicerestore`/`usbmuxd`. The companion must be booted
   **before** the main VM. Restore is then kicked from inside the companion:
   ```
   idevicerestore --erase --restore-mode -i 0x1122334455667788 <ipsw> -T root_ticket.der
   ```
3. **Hours of nested TCG + fs-patches.** With no KVM, two heavy VMs run under
   pure TCG on the host CPU while `idevicerestore` writes the multi-GB OS across
   an emulated USB stack (the docs themselves call USB "currently unstable").
   After restore stage 1 the iOS VM auto-closes; you then apply the **filesystem
   patches** (software rendering) and reboot with `boot-mode=exit_recovery`
   (sets NVRAM `auto-boot`) to reach SpringBoard.

### Boot-mode reference (`hw/arm/apple-silicon/t8030.c`)

- `boot-mode=auto` (default) → boot installed OS from NVMe partition 1.
- `boot-mode=enter_recovery` → boot the restore ramdisk (`-restore rd=md0
  nand-enable-reformat=1`).
- `boot-mode=exit_recovery` → set `auto-boot=true`, boot the restored OS.

## SEP ROM is NOT strictly required (source-verified)

`hw/arm/apple-silicon/t8030.c:2972` gates SEP like this:

```c
if (sep_rom_filename && sep_fw_filename) {
    t8030_create_sep(t8030);              // real SEP, supports data encryption
} else {
#ifdef ENABLE_DATA_ENCRYPTION
    error_setg(..., "Simulated SEP cannot be used with data encryption ...");
#else
    t8030_create_sep_sim(t8030);          // simulated SEP, data volume NOT encrypted
#endif
}
```

So building with `ENABLE_DATA_ENCRYPTION` commented out (this runbook's build)
selects **simulated SEP** and a restore can proceed **without any copyrighted
Apple SEP ROM / SecureROM dump** — the Data volume just isn't encrypted. The
official guide uses a real `AppleSEPROM-Cebu-B1` dump for a faithful (encrypted)
restore, but it is not mandatory for reaching SpringBoard.

## Full restore → SpringBoard procedure (Inferno)

1. Build with **both** targets: `--target-list=aarch64-softmmu,x86_64-softmmu`.
2. **Companion VM** — boot a normal x86_64 Linux guest under `qemu-system-x86_64`
   with `-usb -device usb-ehci,id=ehci -device usb-tcp-remote,bus=ehci.0`
   (defaults to the `/tmp/InfernoUSBRemote` Unix socket). Install
   `idevicerestore` + `usbmuxd` in the guest. **Start the companion before the
   main VM.**
3. **Main VM** — the `-M t8030,...` boot command from "Running & Restoring" with
   the Erase ramdisk via `-initrd` and a display flag
   (`-display gtk,zoom-to-fit=on,show-cursor=on`).
4. **Kick the restore in the companion**:
   ```
   idevicerestore --erase --restore-mode -i 0x1122334455667788 <ipsw> -T root_ticket.der
   ```
   The main VM auto-closes when restore stage 1 finishes.
5. **Filesystem patches** (software rendering — the QuartzCore/Metal-context fix):
   - Mount the `root` raw image (macOS: `hdiutil attach -imagekey
     diskimage-class=CRawDiskImage -blocksize 4096 -noverify -noautofsck root`;
     Linux: `apfs-fuse`).
   - `git clone https://git.chefkiss.dev/AppleHax/InfernoFSPatcher`, build with
     CMake, then
     `sudo build/inferno_fs_patcher /Volumes/System/.../dyld_shared_cache_arm64e`.
   - Disable the broken launch services in
     `System/Library/xpc/launchd.plist` (add `Disabled=true`):
     `com.apple.voicemail.vmd`, `com.apple.CommCenter`,
     `com.apple.CommCenterMobileHelper`, `com.apple.CommCenterRootHelper`,
     `com.apple.locationd`.
6. **Reboot to SpringBoard**: relaunch the main VM with `boot-mode=exit_recovery`
   (sets NVRAM `auto-boot=true`, boots the restored OS from NVMe partition 1).

The eShard two-part series (eshard.com/blog) documents the same wall from the
research side — their public result came from a *private* fork after person-months
of RE (QEMU 8 port, PongoOS/checkra1n KPF, PAC + dyld-ASLR disable, dozens of
userspace/framework patches, a custom multitouch SPI device, `chip-id` 8015 GPU
workaround). Inferno packages the equivalents (KPF + InfernoFSPatcher + SEP
emulation), which is why it is the reproducible route.

## Honest status

- ✅ Emulator builds and runs; iOS 14 kernel + simulated SEP + userland
  (`restored_external`) execute; Apple-logo framebuffer rendered and screenshotted.
- ⛔ SpringBoard not reached **in this environment**. It does not need ROM dumps
  (simulated SEP works), but it does need a second x86_64 Linux VM running
  `idevicerestore`, a multi-GB restore under nested TCG (no KVM here → many hours,
  fragile), and the fs-patches above. That pipeline is meant for a real,
  KVM-capable host with persistent disk — not an ephemeral 4-core CI container
  that already wiped once mid-build. Follow the steps above on such a host.
