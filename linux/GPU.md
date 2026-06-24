# GPU / display acceleration

## The honest reality (read this)

**You cannot GPU-accelerate iOS rendering in these emulators.** The QEMU forks
do not emulate the Apple GPU at all — iOS draws its entire UI in **software**,
on the CPU. There are three independent reasons there is no way around this:

1. **No emulated Apple GPU.** The forks expose a framebuffer, not a GPU. iOS's
   AGX/IOGPU stack has nothing to talk to, so it uses the software fallback
   (this is exactly the "patches for software rendering" the wikis mention).
2. **virtio-gpu / virgl is Linux-guest only.** The standard QEMU GPU-accel
   path translates guest OpenGL → host OpenGL via a guest virtio-gpu driver.
   iOS has no such driver and never will.
3. **No host-GPU passthrough into Metal/AGX.** Apple's graphics stack is
   closed and Apple-silicon specific; a host AMD/NVIDIA/Intel GPU cannot back
   it.

Anyone claiming "iPhone-on-QEMU with full GPU acceleration" is mistaken. The
guest is CPU-bound for graphics, full stop.

## What `vphone-linux` *does* accelerate: presentation

The framebuffer iOS renders in software still has to be uploaded, scaled, and
blitted into a window. That presentation step **can** use the host GPU via
OpenGL instead of the CPU. It will not make iOS itself faster, but it offloads
the display path and gives clean scaling — a real, measurable saving on the
host CPU, especially at larger window sizes.

```bash
# host-GPU-accelerated local window
vphone-linux init ./ws --display gtk --gl on
# or SDL
vphone-linux init ./ws --display sdl --gl on
# headless host-GPU rendering streamed over VNC (remote/servers)
vphone-linux init ./ws --vnc 1 --gl on        # → 127.0.0.1:5901
# fully headless, no display
vphone-linux init ./ws --display none
```

Resulting QEMU flags:

| Config | Flag(s) |
| --- | --- |
| `--display gtk --gl on` | `-display gtk,gl=on` |
| `--display sdl --gl off` | `-display sdl,gl=off` |
| `--display egl-headless` | `-display egl-headless,gl=on` |
| `--vnc 1 --gl on` | `-display egl-headless -vnc 127.0.0.1:1` |
| `--display none` | `-display none` |
| `--display auto` | *(QEMU's built-in default)* |

## Requirements

`gl=on` needs QEMU built with OpenGL/EGL support and host GL libraries.
`vphone-linux doctor` checks for host EGL; install the dev packages it lists
(`libepoxy-dev libgbm-dev libegl-dev libgtk-3-dev libsdl2-dev`) **before**
building QEMU so configure picks them up. On x86_64 hosts everything runs
under TCG regardless — presentation accel helps the display path, not the
CPU-bound guest.

## Companion VM (separate, Linux — can be truly GPU-accelerated)

The networking companion is an ordinary Linux guest, so it *can* use real
virtio-gpu/virgl if you want a GPU-accelerated Linux desktop there. That has
no effect on the iPhone's rendering; it is only relevant if you do GPU work
inside the companion itself.
