#!/usr/bin/env bash
# Run this INSIDE the companion Linux VM. Builds the libimobiledevice stack from
# source (release tarballs are too old) and applies the required idevicerestore
# patch. Copy idevicerestore.patch (next to this script) into the VM first.
set -euo pipefail

export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig/
# Toolchain deps vary by distro; on Arch: base-devel git autoconf automake libtool
# pkgconf openssl libusb libzip libplist curl ...
PROJECTS=(libplist libimobiledevice-glue libusbmuxd usbmuxd libirecovery libtatsu libimobiledevice idevicerestore)

for p in "${PROJECTS[@]}"; do
  [ -d "$p" ] || git clone "https://github.com/libimobiledevice/$p"
  pushd "$p" >/dev/null
  if [ "$p" = idevicerestore ] && [ -f ../idevicerestore.patch ]; then
    git apply ../idevicerestore.patch || echo "(patch already applied?)"
  fi
  ./autogen.sh && make -j"$(nproc)" && sudo make install
  popd >/dev/null
done
sudo ldconfig

# usbmuxd on systemd needs a 'usbmux' user:
echo 'u usbmux 140 "usbmux user"' | sudo tee /usr/lib/sysusers.d/usbmuxd.conf >/dev/null
sudo chmod 644 /usr/lib/sysusers.d/usbmuxd.conf
sudo systemd-sysusers || true
sudo udevadm control --reload-rules || true
sudo systemctl daemon-reload || true
sudo systemctl restart usbmuxd || true
echo "Companion tools ready. Transfer the IPSW + root_ticket.der in via scp (port 32222)."
