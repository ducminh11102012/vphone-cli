# vphone-linux

**Turnkey iOS-on-QEMU orchestrator for Linux** — the Linux sibling of the
macOS `vphone-cli`.

## Why this exists (read this first)

The macOS `vphone-cli` boots a virtual iPhone through Apple's
`Virtualization.framework`. That framework **only exists on macOS running on
Apple Silicon** — it cannot be ported to Linux or Windows. There is no trick,
no flag, no library that changes this.

What *can* run iOS on Linux is a **software emulator of the Apple SoC**. Two
mature open-source QEMU forks do exactly this for the **t8030 (Apple A13 /
iPhone 11)** running **iOS 14.x**:

| Backend (`--backend`) | Project | Status |
| --- | --- | --- |
| `chefkiss` | [ChefKissInc/QEMUAppleSilicon](https://github.com/ChefKissInc/QEMUAppleSilicon) (Inferno) | Boots to SpringBoard; SSH, pairing, multitouch, networking, IPA install |
| `trung` | [TrungNguyen1909/qemu-t8030](https://github.com/TrungNguyen1909/qemu-t8030) | Original fork; stable; detailed wiki |

**This tool does not reimplement the emulator.** Booting iOS in software is a
multi-year reverse-engineering effort by those communities, and the fidelity
you get is theirs. What `vphone-linux` adds is the part that is genuinely
painful today: **orchestration**. It builds the fork, extracts firmware from
an IPSW, sizes the NVMe namespaces, assembles the ~40-flag QEMU command line,
and manages the VM lifecycle — so the whole flow is a handful of commands
instead of a wiki crawl.

### Honest scope

- ✅ Builds either QEMU fork from source.
- ✅ Extracts kernelcache / DeviceTree / SEP / ramdisk / trustcache from an
  IPSW (no hardcoded paths — everything resolved from the BuildManifest).
- ✅ Creates the NVMe namespace + NVRAM images.
- ✅ Assembles correct `restore` and `boot` command lines for both forks.
- ⚠️ A valid `root_ticket.der` is taken from the IPSW identity when present;
  otherwise you must supply one (see *Tickets* below). Emulated SEP does not
  need real SHSH blobs, but it needs a well-formed ticket.
- ❌ Targets only **t8030 / iPhone 11 / iOS 14.x** — the range the forks boot.
- ❌ Runs under TCG on x86_64 hosts (correct but slow); aarch64 hosts are far
  faster.

## Install

```bash
cd linux
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or: pip install -e .
```

## Quick start

```bash
# 1. create a self-contained workspace
vphone-linux init ./ws --backend chefkiss --cpus 4 --memory-mb 4096

# 2. check host prerequisites (build toolchain, arch)
vphone-linux doctor ./ws

# 3. clone + build the QEMU fork (slow, one-time)
vphone-linux build ./ws

# 4. extract firmware from an iOS 14 IPSW for iPhone 11 (iPhone12,1)
vphone-linux fetch ./ws iPhone11,8_iPhone12,1_14.x_Restore.ipsw

# 5. create disk images
vphone-linux prepare ./ws --main-gb 16

# 6. inspect the exact QEMU command without running it
vphone-linux plan ./ws --restore

# 7. first-time restore (installs iOS into the NVMe images)
vphone-linux restore ./ws

# 8. boot the installed system
vphone-linux boot ./ws
```

`vphone-linux info ./ws` shows current state at any time.

## Networking (the iPhone has no network by default — fixed here)

The emulated t8030 has **no plain ethernet NIC** iOS will use; on real
hardware and in these forks the phone only reaches the network over **USB**.
The stock wiki boot commands add no network devices at all — which is why the
VM appears offline. `vphone-linux` closes this gap with three modes:

```bash
vphone-linux init ./ws --net usb-bridge   # default: USB → companion VM → internet
vphone-linux companion ./ws               # start the bridge VM first…
vphone-linux boot ./ws                     # …then boot the phone
vphone-linux ssh ./ws                      # prints the SSH command to the phone
```

- `usb-bridge` (default) — exposes the phone's USB on a socket and runs a
  small companion Linux VM that NATs it to the internet. The reliable path.
- `user` — attaches a QEMU user-mode netdev directly (forks that expose a NIC).
- `off` — no networking.

Full details, companion-image requirements, and the exact device wiring are in
[`NETWORKING.md`](./NETWORKING.md).

## Display / GPU acceleration

**iOS rendering cannot be GPU-accelerated** in these forks — they don't
emulate the Apple GPU, so iOS draws in software on the CPU (a hard emulator
limitation, see [`GPU.md`](./GPU.md)). What *can* use the host GPU is the
**presentation** of that framebuffer (upload/scale/blit via OpenGL), plus
headless/VNC output:

```bash
vphone-linux init ./ws --display gtk --gl on   # host-GPU-accelerated window
vphone-linux init ./ws --vnc 1 --gl on         # headless host-GPU → VNC :5901
vphone-linux init ./ws --display none          # fully headless
```

`vphone-linux doctor ./ws` reports whether host EGL is available for `gl=on`.

## Workspace layout

A workspace is self-contained and movable:

```
ws/
├── vphone-linux.toml     # backend, device, cpu/mem, boot args
├── qemu-src/             # cloned QEMU fork (+ build/)
├── firmware/             # extracted kernelcache, DeviceTree, SEP, ...
├── disks/                # nvme.1..7 + nvram (sparse raw images)
├── ipsw/                 # downloaded IPSWs
└── logs/                 # serial console logs
```

## Tickets

Both forks need a `root_ticket.der` (APTicket / IM4M). `fetch` writes one
automatically when the IPSW BuildManifest embeds `ApImg4Ticket`. If it does
not, generate one with `img4tool`/`pyimg4` against the same BuildIdentity, or
use the fork's auto-ticket mode, and drop it at `firmware/root_ticket.der`.
Real SHSH blobs are **not** required under emulation.

## Relationship to the macOS firmware patcher

The macOS tree contains pure-Swift (`sources/FirmwarePatcher/`) and Python
(`scripts/patchers/`) firmware patchers. Those are cross-platform binary
manipulation (ARM64 disasm/asm, Mach-O, IM4P) and can run on Linux; this
orchestrator is structured so a future `patch` step can call into them for the
small set of kernel patches some boot paths want. The QEMU forks already need
fewer than ~10 instruction patches, so this is optional today.

## Windows

The orchestrator is pure Python and runs on Windows, but the QEMU forks build
cleanly under **WSL2** (a Linux environment) rather than native Win32. Use the
same commands inside WSL2. Native Windows QEMU builds of these forks are not
something upstream supports today.

## Credits

All emulation credit belongs to the
[ChefKiss](https://github.com/ChefKissInc/QEMUAppleSilicon) and
[TrungNguyen1909](https://github.com/TrungNguyen1909/qemu-t8030) projects and
the wider iOS-on-QEMU community. This tool only orchestrates them.
