# Real boot serial excerpt — iOS 14.0 (18A373) on qemu-t8030, Linux x86_64 (TCG)
```
Loading iOS 14.0...
kernel_low: 0xfffffff004000000
kernel_high: 0xfffffff009b8bcb8
KPF: found apfs_vfsop_mount
KPF: found handle_eval_rootauth
KPF: Found AMFI hashtype check
kpf_amfi_callback: Found AMFI (Leaf)
kpf_amfi_callback: Found lookup_in_trust_cache_module @ 0xfffffff007b693ec
KPF: Found mac_mount
KPF: Found mac_mount
kpf_amfi_callback: Found AMFI (Routine)
kpf_amfi_callback: Found lookup_in_static_trust_cache @ 0xfffffff0097c5cb8
qemu-system-aarch64: Missing patch: trustcache16
KPF: Found AppleKeyStoreUserClient::handleUserClientCommandGated
...
iBoot version: qemu-t8030
Darwin Image4 Validator Version 3.0.0: Fri Aug 28 22:36:36 PDT 2020; root:AppleImage4-106.0.5.0.1~31/AppleImage4/RELEASE_ARM64E
AppleSEPKeyStore:321:0: starting (BUILT: Aug 28 2020 23:03:09)
AppleSEPKeyStore:545:0: _sep_enabled = 1
2026-06-24 03:55:41.710448+0000 restored_external[7:383] RestoreLog: Client Query: Image4Supported
2026-06-24 03:55:41.731336+0000 restored_external[7:383] Could not open /private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist: No such file or directory
2026-06-24 03:55:41.748304+0000 restored_external[7:383] RestoreLog: Client Response: Image4Supported : 1
2026-06-24 03:55:42.343158+0000 restored_external[7:383] RestoreLog: Client Query: DeviceClass
2026-06-24 03:55:42.347499+0000 restored_external[7:383] RestoreLog: Client Response: DeviceClass : iPhone
2026-06-24 03:55:42.349324+0000 restored_external[7:383] RestoreLog: Client Query: DeviceColorMapPolicy
2026-06-24 03:55:42.355523+0000 restored_external[7:383] RestoreLog: Client Response: DeviceColorMapPolicy : 0
2026-06-24 03:55:42.366590+0000 restored_external[7:383] IOMFB: /System/Library/Frameworks/MediaToolbox.framework/MediaToolbox not found
2026-06-24 03:55:42.370290+0000 restored_external[7:383] IOMFB: /System/Library/PrivateFrameworks/MediaToolbox.framework/MediaToolbox not found
2026-06-24 03:55:42.373776+0000 restored_external[7:383] IOMFB: /System/Library/PrivateFrameworks/Celestial.framework/Celestial not found
2026-06-24 03:55:42.375440+0000 restored_external[7:383] IOMFB: FigInstallVirtualDisplay not found
[03:55:48.0043-GMT]{4>7} CHECKPOINT BEGIN: MAIN:[0x0404] update_root_mount
restore-step-names = {0x11030404:update_root_mount}
[03:55:48.0084-GMT]{4>7} CHECKPOINT END: MAIN:[0x0404] update_root_mount
```

## What this proves

Built `qemu-t8030` (QEMU 7.1.0) from source on a clean **Ubuntu x86_64** box
(all deps incl. lzfse/libtasn1 from source; submodules + two source fixes per
[BUILD.md](./BUILD.md)) and booted the **stock iOS 14.0 IPSW for iPhone12,1**.
The real XNU kernel ran: KPF patched the live kernelcache, the Image4
validator, **emulated SEP** (`_sep_enabled = 1`), the IOKit driver stack, USB
(AppleUSBMux), and the userland **`restored_external`** daemon all came up. The
device reached restore mode and printed `waiting for host to trigger start of
restore` — i.e. it is a fully-booted iOS restore environment.

All under **TCG on x86_64** (no KVM — as documented, KVM can't run t8030).

## Why it stops here (honest)

1. **Restore needs a USB host.** `restored_external` waits for `idevicerestore`
   to drive the restore over USB (`usb_tcp_host_attach: failed to connect`).
   Completing it means: add `usb-tcp-remote` on the iOS side, run a host
   `idevicerestore`/usbmuxd shim against the socket, push the OS to NVMe, then
   boot the restored system. That is the multi-step qemu-t8030 restore flow.
2. **Crypto backend.** This QEMU was built without nettle/gcrypt, so the
   `ticket-filename` path (`boot-manifest-hash` SHA-384) aborts with "Unknown
   hash algorithm 4". Booting **without** a ticket avoids it (as above); a
   proper restore should rebuild QEMU with nettle.

## Next steps to SpringBoard

- Rebuild QEMU with `nettle` (→ gmp) for the hash path.
- Wire the USB bridge + a host `idevicerestore` to perform the actual restore
  into the NVMe images, then boot with `boot-mode=manual` (no ramdisk).
- Display: run with `--display gtk --gl on` (or `--vnc`) on a machine with a
  screen to see the UI; this container is headless.
