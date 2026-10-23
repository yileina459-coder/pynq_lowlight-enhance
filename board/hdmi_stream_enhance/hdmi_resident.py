#!/usr/bin/env python3
"""A resident demo whose parameters are re-read from files, so tuning never restarts it.

Why this shape
    Restarting the demo is what breaks the picture on this bench: the process exit stops the
    VDMA, the video core starves, TMDS drops, and the USB capture dongle - which only samples HPD
    at connect time - frequently fails to re-lock and sits on its own test pattern until the cable
    is physically re-plugged. Every parameter tweak therefore cost a re-plug.

    This script owns the output for its whole lifetime and watches a few small files instead:

        /tmp/hdmi_roll.txt      horizontal compensation in pixels (empty or 0 = none)
        /tmp/hdmi_preset.txt    preset name
        /tmp/hdmi_image.txt     picture path (PNG/JPEG readable by Pillow, or a .bin raw frame)

    Changing a file re-renders and re-pushes the frame on the next tick - no reset, no clock
    reprogramming, no interruption. Frames are also re-pushed periodically so the VDMA never
    runs dry.

    sudo python3 -u hdmi_resident.py --image testcard_640x480.png --roll 89 --preset pass
"""

from __future__ import annotations

import argparse
import glob
import os
import time

import numpy as np

import hdmi_live as hl

ROLL_FILE = "/tmp/hdmi_roll.txt"
PRESET_FILE = "/tmp/hdmi_preset.txt"
IMAGE_FILE = "/tmp/hdmi_image.txt"
STATE_FILE = "/tmp/hdmi_state.txt"
SOF_FILE = "/tmp/hdmi_sof.txt"
PLAY_FILE = "/tmp/hdmi_play.txt"
PLAY_FPS_FILE = "/tmp/hdmi_play_fps.txt"


UPLOAD_DIR = "/tmp/hdmi_uploads"


def prepare_control_files() -> None:
    """Make the file-based interface usable by the desktop user, not just by root.

    This process runs as root, so the control files it touches would otherwise end up 0644 and
    root-owned - meaning the PC-side upload command cannot write them, and the whole file-driven
    workflow only works until the next reboot wipes /tmp. Setting a zero umask and chmod-ing the
    interface to world-writable keeps 'upload a picture from your laptop' possible without sudo.
    """
    os.umask(0o000)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.chmod(UPLOAD_DIR, 0o777)
    for path in (ROLL_FILE, PRESET_FILE, IMAGE_FILE, SOF_FILE, PLAY_FILE,
                 PLAY_FPS_FILE, STATE_FILE):
        try:
            with open(path, "a", encoding="utf-8"):
                pass
            os.chmod(path, 0o666)
        except OSError:
            pass


def roll_rows(pixels: np.ndarray, shift: int) -> np.ndarray:
    """Horizontal compensation, shared by the static and the playing paths."""
    if not shift:
        return pixels
    return np.roll(pixels, shift, axis=1)


def safe_writeframe(out, buf, state: dict, mode=None) -> bool:
    """Push a frame, recovering if the VDMA channel has halted.

    A halted MM2S channel shows up as

        RuntimeError: DMA channel not started

    and that is what used to kill the demo: the exception escaped the loop, the process exited, and
    the screen froze on the last frame it had managed to push - indistinguishable, from the outside,
    from "the pipeline is fine but ignores my commands".

    Recovery re-configures the mode and starts again, which is exactly what a fresh process does.
    out.stop() is deliberately not used: on an already-halted channel it recurses until Python's
    recursion limit, so the first version of this function made things worse.

    After max_failures consecutive failures it gives up by raising, so a broken design fails loudly
    instead of spinning quietly with a dead screen.
    """
    max_failures = 5
    try:
        out.writeframe(buf)
        state["write_failures"] = 0
        return True
    except RuntimeError as exc:
        failures = state.get("write_failures", 0) + 1
        state["write_failures"] = failures
        print(f"  writeframe failed ({exc}) [failure {failures}/{max_failures}]", flush=True)
        if failures >= max_failures:
            print("  giving up on recovery - the design needs attention", flush=True)
            raise
        if mode is not None:
            try:
                out.configure(mode)
                time.sleep(0.1)
                out.start()
                print("  output reconfigured and restarted", flush=True)
            except Exception as exc2:              # noqa: BLE001
                print(f"  reconfigure failed: {exc2}", flush=True)
        return False


def publish_state(state: dict, width: int, height: int) -> None:
    """Write what is on screen, so a tool on the PC can confirm an update instead of guessing.

    The resident process owns the VDMA, so it also owns the truth about the picture. A file in
    /tmp is the cheapest way to hand that truth to whoever just uploaded an image.
    """
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(f"image={state['image']}\n")
            fh.write(f"roll={state['roll']}\n")
            fh.write(f"preset={state['preset']}\n")
            fh.write(f"sof={state['sof']}\n")
            playing = state.get("playing", "")
            fh.write(f"playing={playing}\n")
            fh.write(f"mode={width}x{height}\n")
            fh.write(f"updated={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    except OSError:
        pass


def read_text(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return default


def load_picture(path: str, width: int, height: int) -> np.ndarray:
    if path.endswith(".bin"):
        data = np.fromfile(path, dtype=np.uint8)
        expected = width * height * 3
        if data.size != expected:
            raise ValueError(f"{path}: {data.size} bytes, expected {expected}")
        return data.reshape(height, width, 3)

    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        if img.size != (width, height):
            scale = min(width / img.width, height / img.height)
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            resized = img.resize(size, Image.LANCZOS)
            canvas = Image.new("RGB", (width, height), (0, 0, 0))
            canvas.paste(resized, ((width - size[0]) // 2, (height - size[1]) // 2))
            img = canvas
        return np.asarray(img, dtype=np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--image", default="testcard_640x480.png")
    ap.add_argument("--roll", type=int, default=0)
    ap.add_argument("--preset", default="pass")
    ap.add_argument("--tick", type=float, default=2.0, help="seconds between file checks")
    ap.add_argument("--force-clock", action="store_true",
                    help="reprogram the pixel clock even if the mode already matches")
    ap.add_argument("--refresh", type=float, default=10.0,
                    help="re-push the frame this often even when nothing changed")
    args = ap.parse_args(argv)

    width, height = (int(v) for v in args.mode.lower().split("x"))

    ol = hl.open_overlay(args.bitstream)
    out = ol.video.hdmi_out
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    state = {"roll": args.roll, "preset": args.preset, "image": args.image,
             "sof": None, "playing": "", "write_failures": 0}
    picture = load_picture(state["image"], width, height)
    frame = None

    def render() -> np.ndarray:
        rolled = hl.roll_frame(picture, state["roll"]) if state["roll"] else picture
        return rolled

    def fill_all_buffers(pixels) -> None:
        """Write the picture into every VDMA frame buffer.

        The VDMA cycles a list of four buffers, and a buffer that was never written keeps the
        all-zero frame that start() queued. Filling one buffer therefore makes the display
        alternate between the picture and black - which reads as 'the screen is black' whenever
        the sampled frame happens to be an empty one.
        """
        for _ in range(4):
            buf = out.newframe()
            buf[:] = pixels
            safe_writeframe(out, buf, state, mode)

    prepare_control_files()
    from pynq.lib.video import VideoMode
    mode = VideoMode(width, height, 24, 60)
    hl.start_output(ol, out, width, height, force=args.force_clock)
    fill_all_buffers(render())
    hl.write_preset(cfg, state["preset"])
    # SOF is enabled by default: it is the frame-alignment marker the output core needs, and without
    # it the picture lands at whatever phase start-up happened to produce. The file stays as a
    # diagnostic switch - writing 0 disables it to demonstrate the difference.
    if read_text(SOF_FILE) not in ("0", "1"):
        try:
            with open(SOF_FILE, "w", encoding="utf-8") as fh:
                fh.write("1")
        except OSError:
            pass
    if read_text(SOF_FILE) == "1":
        hl.set_sof_enable(cfg, True, state["preset"])
        state["sof"] = True

    print(f"resident demo up: roll {state['roll']}, preset {state['preset']}, "
          f"latency {hl.read_latency(lat)}", flush=True)
    publish_state(state, width, height)
    print("watching /tmp/hdmi_roll.txt, /tmp/hdmi_preset.txt, /tmp/hdmi_image.txt, "
          "/tmp/hdmi_sof.txt", flush=True)

    last_refresh = time.monotonic()
    clip = {"dir": "", "paths": [], "fps": 0.0, "index": 0, "next": 0.0}
    while True:
        # ---- video playback -------------------------------------------------------------
        # Playing a frame sequence has to happen inside this process: stopping the demo to start a
        # player interrupts the pixel stream, and this capture dongle only re-locks after a physical
        # replug or a board reboot. So the loop below switches modes on the fly, driven by a file.
        play_text = read_text(PLAY_FILE)
        if play_text and os.path.isdir(play_text):
            if play_text != clip["dir"]:
                paths = sorted(glob.glob(os.path.join(play_text, "frame_*.png")))
                if paths:
                    fps_text = read_text(PLAY_FPS_FILE)
                    try:
                        fps = float(fps_text) if fps_text else 30.0
                    except ValueError:
                        fps = 30.0
                    clip.update({"dir": play_text, "paths": paths, "index": 0,
                                 "fps": fps, "next": time.monotonic()})
                    state["playing"] = f"{len(paths)} frames at {fps:g} fps"
                    publish_state(state, width, height)
                    print(f"  play -> {play_text} ({len(paths)} frames at {fps:g} fps)", flush=True)
                else:
                    print(f"  play: no frame_*.png in {play_text}", flush=True)
                    clip["dir"] = ""
                    state["playing"] = ""

            if clip["paths"]:
                frame = clip["paths"][clip["index"] % len(clip["paths"])]
                try:
                    if state["playing"] and clip["index"] % 30 == 0:
                        publish_state(state, width, height)
                    # One buffer, allocated the first time and reused. Allocating a fresh one per
                    # frame (out.newframe()) put the loop about two seconds behind every frame,
                    # because the allocation costs far more than the copy.
                    if play_buf[0] is None:
                        play_buf[0] = out.newframe()
                    # Decoded frames are cached: PNG decoding on the PS is ~10x the cost of the
                    # copy into the buffer, and the whole point of playback is to keep a steady
                    # frame rate. 24-bit 640x480 is 0.9 MB per frame, so 240 frames is ~215 MB.
                    pixels = play_cache.get(frame)
                    if pixels is None:
                        if len(play_cache) >= 240:
                            play_cache.clear()
                        pixels = load_picture(frame, width, height)
                        play_cache[frame] = pixels
                    play_buf[0][:] = roll_rows(pixels, state["roll"])
                    safe_writeframe(out, play_buf[0], state, mode)
                except Exception as exc:                   # noqa: BLE001
                    print(f"  play write failed: {exc}", flush=True)
                    clip["dir"] = ""
                clip["index"] += 1
                interval = 1.0 / max(clip["fps"], 1.0)
                clip["next"] += interval
                sleep = clip["next"] - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
                else:
                    # Only complain when the loop is properly late, not on every frame.
                    if -sleep > 0.25:
                        print(f"  play: behind by {-sleep * 1000:.0f} ms, resynchronising",
                              flush=True)
                    clip["next"] = time.monotonic()
                # Control files still matter while playing, but polling them per frame costs time;
                # every 15 frames is often enough to feel instant.
                if clip["index"] % 15 != 0:
                    continue
        elif clip["dir"]:
            print("  play -> stopped", flush=True)
            clip["dir"] = ""
            state["playing"] = ""
            publish_state(state, width, height)

        time.sleep(args.tick)
        changed = False

        roll_text = read_text(ROLL_FILE)
        if roll_text:
            try:
                value = int(roll_text)
            except ValueError:
                value = state["roll"]
            if value != state["roll"]:
                state["roll"] = value
                changed = True
                print(f"  roll -> {value}", flush=True)

        preset_text = read_text(PRESET_FILE)
        if preset_text and preset_text != state["preset"]:
            if preset_text in hl.PRESETS:
                state["preset"] = preset_text
                hl.write_preset(cfg, preset_text)
                publish_state(state, width, height)   # the preset is part of what is on screen
                print(f"  preset -> {preset_text}  (latency {hl.read_latency(lat)})", flush=True)
            else:
                # Silently ignoring an unknown name looks exactly like 'the hardware does nothing',
                # which is the confusion this whole preset round was about. Say it out loud.
                print(f"  preset '{preset_text}' is not known here; keeping '{state['preset']}'. "
                      f"Valid: {', '.join(sorted(hl.PRESETS))}", flush=True)

        sof_text = read_text(SOF_FILE)
        if sof_text in ("0", "1"):
            want = sof_text == "1"
            if want != state.get("sof"):
                state["sof"] = want
                hi = hl.set_sof_enable(cfg, want, state["preset"])
                print(f"  SOF -> {'on' if want else 'off'} (cfg_hi=0x{hi:08x}); "
                      f"a frame re-push follows so the change takes effect", flush=True)
                changed = True

        image_text = read_text(IMAGE_FILE)
        if image_text and image_text != state["image"]:
            try:
                picture = load_picture(image_text, width, height)
                state["image"] = image_text
                changed = True
                print(f"  image -> {image_text}", flush=True)
            except Exception as exc:                       # noqa: BLE001
                print(f"  image load failed: {exc}", flush=True)

        if changed:
            fill_all_buffers(render())
            publish_state(state, width, height)
            print(f"  frame re-pushed to all buffers (roll {state['roll']})", flush=True)
            last_refresh = time.monotonic()
        elif time.monotonic() - last_refresh >= args.refresh:
            # Keep the VDMA fed; one buffer is enough while nothing has changed.
            buf = out.newframe()
            buf[:] = render()
            safe_writeframe(out, buf, state, mode)
            last_refresh = time.monotonic()


if __name__ == "__main__":
    raise SystemExit(main())
