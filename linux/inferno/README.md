# Inferno turnkey scaffold — iPhone 11 (t8030) iOS 14 → SpringBoard

Scripts that encode the validated build + the official ChefKiss Inferno restore
procedure (`chefkiss.dev/guides/inferno`). They get you from nothing to a booted
SpringBoard **without any copyrighted Apple SEP/SecureROM dump** (simulated SEP).

## Prebuilt binaries — skip the build

`prebuilt/inferno-qemu-prebuilt-linux-x86_64.tar.xz` (9.5 MB) holds stripped,
**ready-to-run** `qemu-system-aarch64` + `qemu-system-x86_64` + `qemu-img`,
bundled with their 5 non-system libs. Unpack with **`./00-use-prebuilt.sh`**
instead of running `01-build-inferno.sh`.

- Target: **Linux x86_64, glibc ≥ 2.38** (Ubuntu 24.04+, Debian 13+, Fedora 38+,
  recent Arch). You still need system `glib-2.0`, `pixman-1`, `gio-2.0`. Older
  distro? Build from source with `01-build-inferno.sh`.
- **What the prebuilt removes:** the ~15-min compile only.
- **What it does NOT remove (still required for SpringBoard):** a legally-obtained
  iOS 14.0 `iPhone12,1` IPSW (not redistributable here), a companion Linux VM with
  the libimobiledevice stack, a **KVM-capable** host, and the multi-GB restore.
- **Quickest real payoff:** with the prebuilt + an IPSW you can reach the **Apple
  logo** in two commands and **zero building** — no companion needed:
  ```bash
  ./00-use-prebuilt.sh
  ./02-extract-firmware.sh <IPSW>
  MODE=restore ./04-run-main-vm.sh      # Apple logo + progress bar (restore-wait)
  ```
  SpringBoard additionally needs steps 3–7 below.

> Run this on a real, **KVM-capable** Linux host with ≥6 GB RAM and ≥32 GB free.
> ChefKiss's own prerequisites: *"a relatively lengthy process… no steps can be
> skipped… this isn't really going to run on a Pentium."* It is **not** suited to
> an ephemeral, nested-TCG CI container (the restore writes multiple GB over an
> emulated USB stack — hours without KVM, and fragile).

## Order of operations

| # | Script | Where | What |
|---|--------|-------|------|
| 1 | `01-build-inferno.sh` | host | build deps + Inferno (aarch64 main + x86_64 companion) |
| 2 | `02-extract-firmware.sh <IPSW>` | host | extract firmware, make disks, forge ticket |
| 3 | install a lightweight Linux into `companion.qcow2`, then run `03-run-companion-vm.sh` | host | start companion VM (**before** the main VM) |
| 3b | `03b-setup-companion-tools.sh` (+ `idevicerestore.patch`) | **inside companion** | build libimobiledevice stack + patch idevicerestore |
| 4 | `MODE=restore ./04-run-main-vm.sh` | host | boot the Erase ramdisk |
| 5 | in the companion: `idevicerestore --erase --restore-mode -i 0x1122334455667788 <IPSW> -T root_ticket.der` | companion | drive the restore (main VM auto-closes at stage-1 end) |
| 6 | apply **fs-patches** (software rendering) | host | mount `root`, run InfernoFSPatcher on the dyld cache + disable broken launch services — see below |
| 7 | `MODE=boot ./04-run-main-vm.sh` | host | boot the restored OS → SpringBoard |

## Filesystem patches (step 6) — required for any UI to render

iOS 14's QuartzCore keeps a hard Metal-context reference even under software
rendering, so without these patches SpringBoard segfaults / shows black.

1. Mount the `root` raw image. macOS:
   `hdiutil attach -imagekey diskimage-class=CRawDiskImage -blocksize 4096 -noverify -noautofsck root`.
   Linux: use `apfs-fuse`.
2. `git clone https://git.chefkiss.dev/AppleHax/InfernoFSPatcher`, build with CMake,
   then `sudo build/inferno_fs_patcher <mnt>/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e`.
3. In `<mnt>/System/Library/xpc/launchd.plist` set `Disabled=true` for:
   `com.apple.voicemail.vmd`, `com.apple.CommCenter`,
   `com.apple.CommCenterMobileHelper`, `com.apple.CommCenterRootHelper`,
   `com.apple.locationd`.

## Notes

- A **real, encrypted** restore instead needs `sep-rom=AppleSEPROM-Cebu-B1` +
  `sep-fw=...new.img4` on the `-M t8030,...` line (copyrighted dumps; optional —
  see `../INFERNO-SPRINGBOARD-RUNBOOK.md` for the source-level SEP gating).
- Behind a TLS-inspecting proxy, add `--cacert <bundle>` to the `curl` calls.
- `idevicerestore.patch` rewrites the restore model `N104DEV` → `N104AP` to match
  the DeviceTree compatibility hack the machine applies during restore.
