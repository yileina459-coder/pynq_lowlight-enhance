#!/usr/bin/env python3
"""Video in, video out - over HTTP, without HDMI and without a codec on the board.

What it is
    A tiny HTTP server on the board. The browser on the laptop opens one page, the
    operator picks a video file, and then:

        browser draws frame -> POST /frame -> pack_rgb -> AXI-DMA -> enhance (PL)
        -> DMA back -> unpack_rgb -> POST response -> browser shows it and records

    The board never sees a container format: no MP4, no H.264, no ffmpeg. The
    laptop's own video decoder plays the file, and the laptop's own MediaRecorder
    writes the result (WebM). That is the whole trick - it keeps the board side to
    numpy + PIL + the DMA driver that is already proven bit-exact.

Why not HDMI (the two-day version)
    The HDMI path on this board is measurably limited: the output only drives
    640x480, the input cannot lock 640x480, and a live link additionally needs a
    downscaler plus a clock-domain line buffer. None of that is required to show
    "a real video goes through the FPGA kernel and comes back changed", which is
    what a school-round demo has to show. See docs/video_demo.md.

Usage
    # on the board, DMA path (the real thing)
    sudo -E env HOME=/root /usr/local/share/pynq-venv/bin/python3 \
        enhance_video_server.py --size 640x480 --preset document

    # on any PC, no board: the golden model stands in for the PL, so the page,
    # the transport and the recording can all be exercised before touching hardware
    python enhance_video_server.py --mode mock

    # then open http://<board-ip>:8000/ in Chrome or Edge

Transport
    --transport jpeg (default) keeps the link small: ~40 kB per 640x480 frame, so
    the round trip is limited by the kernel, not the 100 Mbit Ethernet. The pixels
    that reach the kernel are JPEG-decoded, so this mode is for demo footage.
    --transport raw sends 3 bytes per pixel and is the bit-exact transport: the
    bytes the kernel produced are the bytes the browser receives.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
# On the board only this directory is copied over; on the PC the golden model and
# the shared border policy live in the repository, so look in both places.
for _extra in (os.path.join(_HERE, "..", "..", "sim", "enhance"),
               os.path.join(_HERE, "..", "..", "sim", "common"),
               _HERE):
    if os.path.isdir(_extra) and _extra not in sys.path:
        sys.path.insert(0, _extra)


# -----------------------------------------------------------------------------
# Engines: one interface, two implementations (PL over DMA / software golden)
# -----------------------------------------------------------------------------
class Engine:
    name = "?"

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._lock = threading.Lock()

    def presets(self) -> list[str]:
        return ["pass", "clarity", "reading", "document", "night",
                "invert", "binarize", "split"]

    def process(self, rgb: np.ndarray, preset: str) -> tuple[np.ndarray, float]:
        raise NotImplementedError

    def handle(self, body: bytes, preset: str, transport: str):
        """Bytes in, bytes out. Returns (payload, frame_ms, content_type).

        ``transport`` comes from the request's Content-Type, so one server speaks
        both: ``image/jpeg`` for the fast demo link, anything else (the page sends
        ``application/octet-stream``) for the bit-exact raw link.
        """
        with self._lock:
            if transport == "jpeg":
                img = Image.open(io.BytesIO(body)).convert("RGB")
                if img.size != (self.width, self.height):
                    img = img.resize((self.width, self.height), Image.BILINEAR)
                rgb = np.asarray(img, dtype=np.uint8)
                out, ms = self.process(rgb, preset)
                buf = io.BytesIO()
                Image.fromarray(out).save(buf, format="JPEG", quality=92)
                return buf.getvalue(), ms, "image/jpeg"

            rgb = np.frombuffer(body, dtype=np.uint8)
            pixels = self.width * self.height
            if rgb.size == pixels * 3:
                stride = 3
                rgb = rgb.reshape(self.height, self.width, 3)
            elif rgb.size == pixels * 4:
                # Browsers hand canvas pixels over as RGBA; drop alpha on the way in
                # and put it back on the way out so the page can putImageData directly.
                stride = 4
                rgb = rgb.reshape(self.height, self.width, 4)[:, :, :3]
            else:
                raise ValueError(f"raw body is {rgb.size} bytes, expected "
                                 f"{pixels * 3} (RGB) or {pixels * 4} (RGBA)")
            out, ms = self.process(rgb, preset)
            if stride == 4:
                out4 = np.empty((self.height, self.width, 4), dtype=np.uint8)
                out4[:, :, :3] = out
                out4[:, :, 3] = 255
                return out4.tobytes(), ms, "application/octet-stream"
            return out.tobytes(), ms, "application/octet-stream"

    def close(self) -> None:
        pass


class MockEngine(Engine):
    """Software stand-in for the PL, for exercising the page without a board."""

    name = "mock(golden model)"

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        try:
            import golden_enhance
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                f"mock mode needs sim/enhance/golden_enhance.py: {exc}"
            ) from exc
        self._golden = golden_enhance

    def presets(self) -> list[str]:
        return sorted(self._golden.PRESETS)

    def process(self, rgb: np.ndarray, preset: str) -> tuple[np.ndarray, float]:
        t0 = time.perf_counter()
        # "wrap" is the border policy of a continuous stream (line buffers), which
        # is what the hardware does; a still image would use "replicate".
        out = self._golden.render(rgb, preset, "wrap")
        return out, (time.perf_counter() - t0) * 1000.0


class DmaEngine(Engine):
    """The real path: AXI-DMA into the enhance kernel and back."""

    name = "dma(PL enhance kernel)"

    def __init__(self, width: int, height: int, bitstream: str, clock_mhz: float):
        super().__init__(width, height)
        from pynq import Overlay, allocate

        from enhance_dma import (find_dma, find_kernel, find_latency_mon,
                                 pack_rgb, preset_to_regs, resolve_regs,
                                 run_preset, unpack_rgb)

        self._pack = pack_rgb
        self._unpack = unpack_rgb
        self._preset_to_regs = preset_to_regs
        self._run = run_preset

        self.clock_mhz = clock_mhz
        print(f"loading {bitstream} ...", flush=True)
        self._ol = Overlay(bitstream)
        self._dma = find_dma(self._ol)
        name, self._kern = find_kernel(self._ol)
        self._offsets = resolve_regs(self._ol, name)
        self._mon = find_latency_mon(self._ol, clock_mhz * 1e6)

        n = width * height
        self._in_buf = allocate(shape=(n,), dtype=np.uint32)
        self._out_buf = allocate(shape=(n,), dtype=np.uint32)
        print(f"  DMA buffers: 2 x {n * 4 / 1e6:.2f} MB at {width}x{height}",
              flush=True)

    def process(self, rgb: np.ndarray, preset: str) -> tuple[np.ndarray, float]:
        regs = self._preset_to_regs(preset, self.width)
        self._in_buf[:] = self._pack(rgb)
        self._in_buf.flush()
        ms = self._run(self._dma, self._kern, self._in_buf, self._out_buf,
                       self.width, self.height, regs, self._offsets) * 1000.0
        return self._unpack(self._out_buf, self.width, self.height), ms

    def latency_clocks(self) -> int:
        if self._mon is None:
            return -1
        return int(self._mon.latency_cycles)


# -----------------------------------------------------------------------------
# HTTP layer
# -----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "enhance-video/1.0"
    protocol_version = "HTTP/1.1"          # keep-alive: matters for 30 fps

    def log_message(self, fmt, *args):     # one line per frame is noise
        pass

    # ---- helpers ------------------------------------------------------------
    def _send(self, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code: int, message: str) -> None:
        body = message.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- routes -------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/info":
            engine = self.server.engine
            info = {
                "width": engine.width,
                "height": engine.height,
                "mode": engine.name,
                "transport": self.server.transport,
                "presets": engine.presets(),
                "preset": self.server.preset,
                "clock_mhz": getattr(engine, "clock_mhz", None),
            }
            self._send(json.dumps(info).encode("utf-8"), "application/json")
            return
        self._fail(404, f"no route {path}")

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path != "/frame":
            self._fail(404, f"no route {url.path}")
            return
        query = parse_qs(url.query)
        preset = (query.get("preset") or [self.server.preset])[0]
        # The client declares how it encoded the frame; the server never assumes.
        sent = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        transport = "jpeg" if sent == "image/jpeg" else "raw"
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            if not body:
                self._fail(400, "empty request body")
                return
            payload, ms, ctype = self.server.engine.handle(body, preset, transport)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._fail(500, f"{type(exc).__name__}: {exc}")
            return

        extra = {"X-Frame-Ms": f"{ms:.3f}", "X-Preset": preset}
        engine = self.server.engine
        if isinstance(engine, DmaEngine):
            extra["X-Latency-Clocks"] = engine.latency_clocks()
        self._send(payload, ctype, extra)


# -----------------------------------------------------------------------------
# The page: one file, no dependencies, works offline from the board
# -----------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>FPGA 视频增强 - 板上实时处理</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; background:#12151a; color:#e8eaf0;
         font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif; }
  header { padding:14px 20px; border-bottom:1px solid #262c36;
           display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
  h1 { font-size:16px; margin:0; font-weight:600; }
  .pill { padding:2px 10px; border-radius:999px; background:#1d2530;
          border:1px solid #2c3542; font-family:ui-monospace,Consolas,monospace;
          font-size:12px; color:#9fb0c8; }
  main { padding:16px 20px; display:flex; flex-direction:column; gap:14px; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  button, select, label.file { background:#1d2530; color:#e8eaf0;
    border:1px solid #334155; border-radius:8px; padding:7px 14px; font-size:13px; }
  button { cursor:pointer; border:1px solid #334155; }
  button.primary { background:#1f6feb; border-color:#1f6feb; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  select { padding:7px 10px; }
  label.file { cursor:pointer; }
  label.file input { display:none; }
  canvas { display:block; max-width:100%; image-rendering:pixelated;
           background:#000; border-radius:8px; }
  #views { display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap; }
  #hud { font-family:ui-monospace,Consolas,monospace; font-size:12px;
         color:#8fa3bf; white-space:pre-line; }
  #log { font-family:ui-monospace,Consolas,monospace; font-size:12px;
         color:#f0a; min-height:1.2em; white-space:pre-wrap; }
  a#dl { color:#7ee787; }
  .hint { color:#7c8ba1; font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>FPGA 视频增强</h1>
  <span class="pill" id="meta">连接中…</span>
  <span class="pill" id="hud"></span>
</header>
<main>
  <div class="bar">
    <label class="file">选择视频<input type="file" id="file" accept="video/*"></label>
    <select id="preset" title="增强预设"></select>
    <button id="selftest" title="用内置测试图跑一帧，确认板子和传输都通">自检</button>
    <button class="primary" id="start" disabled>开始处理</button>
    <button id="stop" disabled>停止并生成录像</button>
    <a id="dl" href="#" hidden>下载处理后的视频 (.webm)</a>
  </div>
  <div class="hint">
    浏览器解码你选的视频，逐帧交给板上的 PL 核处理，再把处理后的帧录制下来。
    录像的帧率就是板子的真实处理速度，不是 30 fps 的假象。
  </div>
  <div id="views">
    <div>
      <div class="pill">处理结果（板子回传）</div>
      <canvas id="out"></canvas>
    </div>
    <div>
      <div class="pill">录像画面（左：原始　右：增强）</div>
      <canvas id="comp"></canvas>
    </div>
  </div>
  <div id="log"></div>
  <video id="src" muted playsinline
         style="position:fixed;left:-10px;top:-10px;width:2px;height:2px;opacity:0.01"></video>
  <canvas id="stage" hidden></canvas>
</main>
<script>
"use strict";
const $ = (id) => document.getElementById(id);
const src = $("src"), out = $("out"), comp = $("comp"), stage = $("stage");
const octx = out.getContext("2d", { willReadFrequently: true });
const cctx = comp.getContext("2d", { willReadFrequently: true });
const sctx = stage.getContext("2d", { willReadFrequently: true });
let info = null, running = false, frames = 0, msSum = 0, rtSum = 0, t0 = 0;
let rec = null, chunks = [], compTrack = null, usedPreset = "document";

function log(msg) { $("log").textContent = msg || ""; }
function hud(text) { $("hud").textContent = text; }

async function boot() {
  try {
    info = await (await fetch("/info", { cache: "no-store" })).json();
  } catch (e) { log("无法连接板子：" + e); return; }
  $("meta").textContent = `${info.width}x${info.height} · ${info.mode} · ${info.transport}`;
  $("preset").innerHTML = info.presets
    .map((p) => `<option${p === info.preset ? " selected" : ""}>${p}</option>`).join("");
  out.width = info.width; out.height = info.height;
  stage.width = info.width; stage.height = info.height;
  comp.width = info.width * 2 + 6; comp.height = info.height;
  octx.fillStyle = "#000"; octx.fillRect(0, 0, out.width, out.height);
  cctx.fillStyle = "#000"; cctx.fillRect(0, 0, comp.width, comp.height);
  $("start").disabled = false;
  hud(`${info.width}x${info.height} · 待机`);
}

// the frame that goes to the board: video letterboxed into the kernel's size
function renderStage() {
  const W = stage.width, H = stage.height;
  const vw = src.videoWidth || 4, vh = src.videoHeight || 3;
  const scale = Math.min(W / vw, H / vh);
  const dw = Math.round(vw * scale), dh = Math.round(vh * scale);
  sctx.fillStyle = "#000"; sctx.fillRect(0, 0, W, H);
  sctx.drawImage(src, Math.round((W - dw) / 2), Math.round((H - dh) / 2), dw, dh);
}

function toBlobPixels(canvas) {
  // canvas pixels are RGBA; the server accepts both strides and mirrors it back
  const d = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
  return new Blob([d.data], { type: "application/octet-stream" });
}
function toBlobJpeg(canvas) {
  return new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.92));
}

async function showResult(res) {
  if (res.headers.get("Content-Type") === "image/jpeg") {
    const bmp = await createImageBitmap(await res.blob());
    octx.drawImage(bmp, 0, 0);
    if (bmp.close) bmp.close();
  } else {
    const ab = await res.arrayBuffer();
    octx.putImageData(new ImageData(new Uint8ClampedArray(ab), out.width, out.height), 0, 0);
  }
}

function label(ctx, text, x, y) {
  ctx.font = "600 13px Consolas,monospace";
  ctx.fillStyle = "rgba(0,0,0,.55)";
  const w = ctx.measureText(text).width + 12;
  ctx.fillRect(x, y, w, 20);
  ctx.fillStyle = "#dfe7f5";
  ctx.fillText(text, x + 6, y + 15);
}

function drawRecordingFrame(preset) {
  const W = out.width, H = out.height;
  cctx.fillStyle = "#0a0c10"; cctx.fillRect(0, 0, comp.width, H);
  cctx.drawImage(stage, 0, 0);
  cctx.drawImage(out, W + 6, 0);
  label(cctx, "原始", 6, 6);
  label(cctx, preset, W + 12, 6);
}

function startRecording() {
  const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
    .find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m));
  if (!mime) { log("这个浏览器不支持 MediaRecorder，无法生成录像（换 Chrome/Edge）"); return; }
  const stream = comp.captureStream(0);
  compTrack = stream.getVideoTracks()[0];
  chunks = [];
  rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8e6 });
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = () => {
    const blob = new Blob(chunks, { type: "video/webm" });
    const d = $("dl");
    if (d.href) URL.revokeObjectURL(d.href);
    d.href = URL.createObjectURL(blob);
    d.download = `enhanced_${usedPreset}_${new Date().toISOString().slice(11, 19).replace(/:/g, "")}.webm`;
    d.hidden = false;
    log(`录像完成：${frames} 帧，${(blob.size / 1e6).toFixed(2)} MB — 点右上链接下载`);
  };
  rec.start();
}

async function start() {
  const f = $("file").files[0];
  if (!f) { log("先选一个视频文件"); return; }
  if (src.src) URL.revokeObjectURL(src.src);
  src.src = URL.createObjectURL(f);
  src.currentTime = 0;
  try {
    if (src.readyState < 2) await new Promise((r, j) => {
      src.onloadeddata = r; src.onerror = () => j(new Error("视频无法解码"));
    });
  } catch (e) { log(String(e)); return; }

  $("dl").hidden = true;
  $("start").disabled = true; $("file").disabled = true;
  $("stop").disabled = false;
  frames = 0; msSum = 0; rtSum = 0; t0 = performance.now();
  usedPreset = $("preset").value;
  running = true;
  startRecording();
  await src.play().catch(() => {});
  log("处理中…（切预设会立刻改变画面，并写进录像）");

  while (running && !src.ended) {
    const preset = $("preset").value;
    renderStage();
    const blob = info.transport === "jpeg" ? await toBlobJpeg(stage) : toBlobPixels(stage);
    const t1 = performance.now();
    let res;
    try {
      res = await fetch(`/frame?preset=${encodeURIComponent(preset)}`,
                        { method: "POST", body: blob });
    } catch (e) { log("请求失败：" + e); break; }
    if (!res.ok) { log("板子报错：" + (await res.text())); break; }
    rtSum += performance.now() - t1;
    msSum += parseFloat(res.headers.get("X-Frame-Ms") || "0");
    await showResult(res);
    drawRecordingFrame(preset);
    if (compTrack) compTrack.requestFrame();
    frames += 1;
    const secs = (performance.now() - t0) / 1000;
    hud(`${info.width}x${info.height} · 板上 ${(msSum / frames).toFixed(1)} ms/帧 · ` +
        `往返 ${(rtSum / frames).toFixed(1)} ms · ${(frames / secs).toFixed(1)} fps · ${frames} 帧`);
  }
  stop();
}

function stop() {
  running = false;
  try { src.pause(); } catch (e) {}
  if (rec && rec.state !== "inactive") rec.stop();
  rec = null; compTrack = null;
  $("start").disabled = false; $("file").disabled = false;
  $("stop").disabled = true;
}

// One frame through the board, no video file needed: the on-site "is it alive?"
// check. The picture is a gradient with dark bars, so the tone curve and the
// binarise preset both produce an obvious change.
async function selftest() {
  if (!info) { log("还没连上板子"); return; }
  const W = out.width, H = out.height;
  const g = sctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, "#0d0d0d"); g.addColorStop(1, "#ececec");
  sctx.fillStyle = g; sctx.fillRect(0, 0, W, H);
  sctx.fillStyle = "#3a3a3a";
  for (let y = 50; y < H - 50; y += 32) sctx.fillRect(36, y, W - 72, 11);
  const preset = $("preset").value;
  const t1 = performance.now();
  let res;
  try {
    const blob = info.transport === "jpeg" ? await toBlobJpeg(stage) : toBlobPixels(stage);
    res = await fetch(`/frame?preset=${encodeURIComponent(preset)}`,
                      { method: "POST", body: blob });
  } catch (e) { log("自检失败（网络）：" + e); return; }
  if (!res.ok) { log("自检失败（板子）：" + (await res.text())); return; }
  const rt = performance.now() - t1;
  await showResult(res);
  log(`自检通过：${info.transport} 往返 ${rt.toFixed(1)} ms，板上处理 ` +
      `${res.headers.get("X-Frame-Ms")} ms，预设 ${preset}，引擎 ${info.mode}`);
}

$("start").onclick = () => start().catch((e) => { log("出错：" + e); stop(); });
$("stop").onclick = () => stop();
$("selftest").onclick = () => selftest();
boot();
</script>
</body>
</html>
"""


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
def parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except Exception:  # noqa: BLE001
        raise SystemExit(f"--size wants WxH, got {text!r}") from None
    if w % 2 or h % 2:
        raise SystemExit("width and height must be even")
    if w * h > 1280 * 720:
        raise SystemExit("bigger than 720p: keep the DMA buffer small for a demo")
    return w, h


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="dma", choices=["dma", "mock"],
                    help="dma = the PL kernel on the board; mock = golden model, no board")
    ap.add_argument("--size", default="640x480", help="WxH, must match what the kernel is fed")
    ap.add_argument("--bitstream", default="enhance_dma.bit")
    ap.add_argument("--preset", default="document")
    ap.add_argument("--transport", default="jpeg", choices=["jpeg", "raw"],
                    help="jpeg = fast demo link, raw = bit-exact bytes")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--clock-mhz", type=float, default=100.0)
    args = ap.parse_args(argv)

    width, height = parse_size(args.size)

    if args.mode == "mock":
        engine: Engine = MockEngine(width, height)
    else:
        try:
            engine = DmaEngine(width, height, args.bitstream, args.clock_mhz)
        except ModuleNotFoundError as exc:
            print(f"FAIL: missing module {exc.name!r}.")
            print("      enhance_dma.py imports golden_enhance (and sim/common/image_ops.py)")
            print("      at import time; copy them next to it, or use the deploy layout in")
            print("      docs/video_demo.md. If panel.ipynb runs on the board, they are")
            print("      already in place - check the working directory instead.")
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: could not bring up the DMA path: {type(exc).__name__}: {exc}")
            print("      run 'python3 enhance_dma.py --presets document' first: that is")
            print("      the hardware baseline this server reuses.")
            return 1

    if args.preset not in engine.presets():
        raise SystemExit(f"--preset {args.preset!r} not in {engine.presets()}")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    httpd.engine = engine
    httpd.transport = args.transport
    httpd.preset = args.preset

    print(f"engine      : {engine.name}")
    print(f"frames      : {width}x{height} ({width * height * 3 / 1024:.0f} kB raw)")
    print(f"transport   : {args.transport}")
    print(f"preset      : {args.preset}")
    print()
    print(f"open  http://{local_ip()}:{args.port}/   (or http://pynq:{args.port}/)")
    print("Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        engine.close()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
