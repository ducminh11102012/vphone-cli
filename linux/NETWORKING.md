# Networking the emulated iPhone

> TL;DR: the emulated iPhone shows **no network by default** because the
> t8030 SoC has no plain ethernet NIC iOS will use for internet. iOS reaches
> the network over **USB tethering**, which has to be bridged out. This is the
> exact gap `vphone-linux` now closes.

## Why the stock VM has no network

On a real iPhone — and in these QEMU forks — there is no virtio-net / e1000
card that iOS binds to. The data paths iOS has are cellular (baseband, not
emulated), Wi‑Fi (not emulated), and **USB**. So the only practical way to get
the emulated phone online is to bridge its USB out, exactly as if you plugged
a physical iPhone into a Linux PC and enabled Personal Hotspot / USB
tethering.

The original wiki boot commands include **no** networking devices at all,
which is why "the VM doesn't get network". `vphone-linux` adds the missing
pieces and automates the bridge.

## Modes (`--net` on `init`, or `network` in `vphone-linux.toml`)

### `usb-bridge` (default, the way that actually works)

```
iOS VM ──(usb-tcp-remote over unix socket)──▶ companion Linux VM ──(user-mode NAT)──▶ internet
```

1. The iOS boot command exposes the phone's USB on a unix socket:

   ```
   -chardev socket,id=usbcdc,path=<ws>/usbqemu.sock,server=on,wait=off
   -device  usb-ehci,id=ehci
   -device  usb-tcp-remote,bus=ehci.0,chardev=usbcdc
   ```

2. A small **companion Linux VM** connects to that socket as the USB *host*,
   runs `usbmuxd`, brings up the Apple USB‑ethernet (CDC‑NCM) interface the
   phone presents, and NATs its traffic out through QEMU user‑mode networking.

   ```bash
   # set a companion image once, in vphone-linux.toml:
   #   companion_image = "/path/to/companion.qcow2"
   vphone-linux companion ./ws      # start this FIRST
   vphone-linux boot ./ws           # then boot the phone
   ```

3. SSH to the phone is forwarded out of the companion to the host:

   ```bash
   vphone-linux ssh ./ws            # prints: ssh -p 2222 root@127.0.0.1
   ```

**Companion image requirements:** any minimal Linux that can run `usbmuxd`
(e.g. a small Debian/Alpine qcow2). Inside it, on boot, run usbmuxd and a NAT/
forwarding setup; a reverse tunnel `ssh -fN -R 10222:localhost:22` from the
phone (or `iproxy 10222 22`) exposes the phone's SSH to the companion, which
`vphone-linux companion` then forwards to the host's `ssh_host_port`.

### `user` (one-flag convenience, fork-dependent)

If the fork you build exposes an in‑machine NIC, you can skip the companion
and attach a user‑mode netdev directly:

```
-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22
```

```bash
vphone-linux init ./ws --net user
```

This is convenient when it works, but whether iOS binds the NIC depends on the
fork/firmware — `usb-bridge` is the reliable path.

### `off`

No networking devices added.

## Notes on device-string accuracy

`usb-tcp-remote` / `usb-tcp-host` are the documented qemu-t8030 device names.
ChefKiss/Inferno's docs are currently gated, so the iOS-side bridge device
name is configurable (`usb_bridge_device` in `vphone-linux.toml`) — if your
fork spells it differently, change it there without touching code. The
`-chardev`/`usb-ehci` wiring and the user-mode `hostfwd` form are standard
QEMU and stable across forks.
