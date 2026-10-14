# Virtual camera

A webcam can only be used by one program at a time. While HandCue is running it owns
the real camera, so other apps should use its virtual camera instead. The virtual camera
shows the clean image (no overlay) with the background effect you choose.

## Installing v4l2loopback

The virtual camera is a `v4l2loopback` device, a kernel module. HandCue shows the
command to install it in *Camera > Virtual camera*. It runs
`src/handcue/resources/install-virtual-camera.sh`, which:

1. installs the module from your distribution (Debian, Ubuntu, Fedora with RPM Fusion,
   Arch, openSUSE),
2. configures it as `/dev/video10` named "HandCue", with `exclusive_caps=1` so
   browsers list it,
3. loads it now and on every boot.

```bash
bash src/handcue/resources/install-virtual-camera.sh
```

If your distribution's package does not build for your kernel (Debian 13 ships 0.15.0,
which fails on kernels 6.18 and newer from backports), build the pinned upstream release
instead:

```bash
bash src/handcue/resources/install-virtual-camera.sh --source
```

With Secure Boot enabled, DKMS modules have to be signed with a key enrolled in MOK; your
distribution's DKMS setup usually guides you through it.

## Using it

1. Turn on *Camera > Virtual camera* in HandCue.
2. In Meet, Zoom, Teams, Discord or OBS, pick the camera named "HandCue".
3. Choose a background: original, blur, a color or an image.

720p is what most video call services use. 1080p costs more CPU.

## Troubleshooting

- **The app says the module is not installed** after running the script: reboot, or run
  `sudo modprobe v4l2loopback`, then press *Check again*.
- **The browser does not list the camera**: make sure `exclusive_caps=1` is in
  `/etc/modprobe.d/handcue-virtual-camera.conf` and that HandCue is already
  streaming when the browser asks for cameras.
- **Black or frozen image in a browser** while other test pages work: check the browser's
  WebGL support. Some Firefox builds lose their WebGL context on recent Intel GPUs, which
  breaks video call effects; updating Mesa or trying Chromium helps.
- **Another resolution is used than the one selected**: if an app is already reading the
  virtual camera, its format cannot change. Close the app and turn the virtual camera off
  and on again.
