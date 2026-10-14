#!/bin/bash
# Sets up the v4l2loopback kernel module so HandCue can provide a virtual
# camera, and loads it on every boot. Asks for the administrator password.
#
#   bash install-virtual-camera.sh              use the distribution's package
#   bash install-virtual-camera.sh --source     build a pinned upstream release with DKMS
#
# --source exists because some distribution packages lag behind the kernel; for
# example Debian 13 ships 0.15.0, which does not build on kernels >= 6.18.
set -euo pipefail

VERSION=0.15.4
COMMIT=0f9ee86760b7f2bea174b7e3e7a1d38845da0ab4  # tag v0.15.4
LABEL="HandCue"
CONF=/etc/modprobe.d/handcue-virtual-camera.conf
LOAD=/etc/modules-load.d/handcue-virtual-camera.conf

from_source=false
[ "${1:-}" = "--source" ] && from_source=true

. /etc/os-release
family="$ID ${ID_LIKE:-}"

# Header packages that follow kernel upgrades, so DKMS can rebuild the module.
headers_meta() {
  case "$ID" in
    ubuntu) echo linux-headers-generic ;;
    debian) echo "linux-headers-$(dpkg --print-architecture)" ;;
  esac
}

install_package() {
  case "$family" in
    *debian*|*ubuntu*)
      sudo apt-get install -y v4l2loopback-dkms "linux-headers-$(uname -r)" $(headers_meta) ;;
    *fedora*)
      # Packaged by RPM Fusion, which has to be enabled first.
      sudo dnf install -y v4l2loopback ;;
    *arch*)
      sudo pacman -S --needed v4l2loopback-dkms linux-headers ;;
    *suse*)
      sudo zypper install -y v4l2loopback-kmp-default ;;
    *)
      echo "Unknown distribution ($ID). Install v4l2loopback with your package manager," >&2
      echo "or run this script with --source on a Debian-based system." >&2
      exit 1 ;;
  esac
}

install_from_source() {
  case "$family" in
    *debian*|*ubuntu*) ;;
    *) echo "--source is only supported on Debian-based systems." >&2; exit 1 ;;
  esac
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  sudo apt-get install -y dkms git "linux-headers-$(uname -r)" $(headers_meta)
  git clone -q --depth 1 --branch "v$VERSION" https://github.com/umlaeute/v4l2loopback.git "$tmp/src"
  # A tag can be moved; a commit cannot. Stop if the code is not what we expect.
  if [ "$(git -C "$tmp/src" rev-parse HEAD)" != "$COMMIT" ]; then
    echo "Downloaded code does not match commit $COMMIT. Aborting." >&2
    exit 1
  fi
  if dpkg -s v4l2loopback-dkms >/dev/null 2>&1; then
    sudo apt-get remove -y v4l2loopback-dkms
  fi
  sudo rm -rf "/usr/src/v4l2loopback-$VERSION"
  sudo cp -r "$tmp/src" "/usr/src/v4l2loopback-$VERSION"
  sudo dkms add "v4l2loopback/$VERSION" 2>/dev/null || true
  sudo dkms install "v4l2loopback/$VERSION" -k "$(uname -r)"
}

if $from_source; then
  echo "==> Building v4l2loopback $VERSION from source"
  install_from_source
else
  echo "==> Installing v4l2loopback"
  install_package
fi

echo "==> Configuring the virtual camera"
# exclusive_caps=1: Chrome and Meet only list the device if it advertises capture only.
echo "options v4l2loopback video_nr=10 card_label=\"$LABEL\" exclusive_caps=1 max_buffers=2" \
  | sudo tee "$CONF" > /dev/null
echo v4l2loopback | sudo tee "$LOAD" > /dev/null
# Files written by versions before 0.1.0
sudo rm -f /etc/modprobe.d/control-gestos-camara-virtual.conf \
           /etc/modules-load.d/control-gestos-camara-virtual.conf

echo "==> Loading the module"
sudo modprobe -r v4l2loopback 2>/dev/null || true
sudo modprobe v4l2loopback

if [ -e /dev/video10 ]; then
  echo "Done: the virtual camera is /dev/video10 (\"$LABEL\")."
  echo "Turn it on in HandCue: Camera tab, Virtual camera."
else
  echo "The module loaded but /dev/video10 is missing. Check: sudo dmesg | tail" >&2
  exit 1
fi
