#!/usr/bin/env python3
"""Interactive control panel for the enhance kernel (Jupyter / ipywidgets).

What it is for
    The measurements already exist as text: eight presets bit-exact, 15.6 ms per
    frame, 16 pixel clocks of latency. What a panel adds is that a person can
    *see* them happen: pick a preset, watch the picture change, watch the numbers
    move. That is what makes the parameterisation and the low latency
    demonstrable live (and recordable for the five-minute video) rather than
    something the audience has to take from a log.

What it is not
    It is not new hardware evidence. Everything shown here was already verified
    from the command line by board/enhance_dma/enhance_dma.py; the panel drives
    the same code paths.

Design notes
    * The widget layer is thin: all register access, golden-model comparison and
      timing come from enhance_dma.py, so the panel and the CLI cannot drift apart.
    * Images are passed to the widget as in-memory PNG bytes, so the panel works
      no matter what the notebook's working directory is.
    * Loading the overlay is lazy: constructing the panel does not touch hardware
      until you first press a button, which keeps the notebook importable.

Usage in a notebook (see panel.ipynb)
    from enhance_panel import EnhancePanel
    EnhancePanel().show()

Headless check without a browser (what CI and the board test do):
    python3 -c "from enhance_panel import EnhancePanel; p = p or EnhancePanel(); \
                print(p.apply('reading'))"
"""

from __future__ import annotations

import io
import time

import numpy as np

from enhance_dma import (
    find_dma,
    find_kernel,
    find_latency_mon,
    pack_rgb,
    preset_to_regs,
    resolve_regs,
    run_preset,
    unpack_rgb,
)

try:  # the golden model is optional: the panel still demos without it
    import golden_enhance as golden
except Exception:  # noqa: BLE001
    golden = None

try:
    import ipywidgets as widgets
    from IPython.display import display
except Exception:  # noqa: BLE001  (lets the module import off-board)
    widgets = None
    display = None


def _png_bytes(rgb: np.ndarray) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return buf.getvalue()


class EnhancePanel:
    """Preset picker + live metrics for the enhance kernel over AXI-DMA."""

    def __init__(self, bitstream: str = "enhance_dma.bit",
                 image: str = "test_dim_720p.png",
                 width: int = 1280, height: int = 720,
                 clock_mhz: float = 100.0,
                 compare_with_golden: bool = True):
        self.bitstream = bitstream
        self.image_path = image
        self.width = width
        self.height = height
        self.clock_mhz = clock_mhz
        self.compare_with_golden = compare_with_golden and golden is not None

        self._ol = None
        self._dma = None
        self._kern = None
        self._offsets = None
        self._mon = None
        self._in_buf = None
        self._out_buf = None
        self._rgb = None

        self._widgets = {}
        self.last = {}

    # ---------------------------------------------------------------- hardware
    @property
    def loaded(self) -> bool:
        return self._ol is not None

    def load(self):
        """Load the overlay and allocate the DMA buffers (idempotent)."""
        if self.loaded:
            return self
        from PIL import Image
        from pynq import Overlay, allocate

        self._ol = Overlay(self.bitstream)
        self._dma = find_dma(self._ol)
        name, self._kern = find_kernel(self._ol)
        self._offsets = resolve_regs(self._ol, name)
        self._mon = find_latency_mon(self._ol, self.clock_mhz * 1e6)

        rgb = np.asarray(Image.open(self.image_path).convert("RGB"))
        if rgb.shape[0] != self.height or rgb.shape[1] != self.width:
            raise ValueError(
                f"{self.image_path} is {rgb.shape[1]}x{rgb.shape[0]}, "
                f"panel is {self.width}x{self.height}")
        self._rgb = rgb
        self._in_buf = allocate(shape=(self.width * self.height,), dtype=np.uint32)
        self._out_buf = allocate(shape=(self.width * self.height,), dtype=np.uint32)
        self._in_buf[:] = pack_rgb(rgb)
        self._in_buf.flush()
        return self

    @property
    def presets(self) -> list[str]:
        if golden is not None:
            return sorted(golden.PRESETS)
        return ["pass", "clarity", "reading", "document", "night", "invert",
                "binarize", "split"]

    # --------------------------------------------------------------- operation
    def apply(self, preset: str, frames: int = 3) -> dict:
        """Run one preset, return the metrics that the panel displays."""
        self.load()
        regs = preset_to_regs(preset, self.width)

        times = [run_preset(self._dma, self._kern, self._in_buf, self._out_buf,
                            self.width, self.height, regs, self._offsets)
                 for _ in range(max(1, frames))]
        best_ms = min(times) * 1000.0
        got = unpack_rgb(self._out_buf, self.width, self.height)

        result = {
            "preset": preset,
            "frame_ms": round(best_ms, 2),
            "fps": round(1000.0 / best_ms, 2),
            "mpixel_s": round(self.width * self.height / (best_ms / 1000) / 1e6, 2),
            "image": got,
        }

        if self._mon is not None:
            cycles = self._mon.latency_cycles
            result["latency_cycles"] = cycles
            result["latency_ns"] = round(self._mon.ns(cycles), 1)

        if self.compare_with_golden:
            expected = golden.render(self._rgb, preset, "wrap")
            diff = np.abs(got.astype(np.int16) - expected.astype(np.int16))
            result["mismatched"] = int(np.count_nonzero(diff))
            result["channels"] = int(diff.size)

        self.last = result
        return result

    # ------------------------------------------------------------------ widgets
    def _metrics_html(self, r: dict) -> str:
        rows = [
            ("preset", r["preset"]),
            ("frame", f"{r['frame_ms']} ms  ({r['fps']} fps, {r['mpixel_s']} Mpixel/s)"),
        ]
        if "latency_cycles" in r:
            rows.append(("latency", f"{r['latency_cycles']} pixel clocks "
                                    f"(~{r['latency_ns']} ns at {self.clock_mhz} MHz)"))
        if "mismatched" in r:
            ok = r["mismatched"] == 0
            colour = "#1b5e20" if ok else "#b71c1c"
            rows.append(("bit-exact",
                         f"<span style='color:{colour}'>{r['mismatched']} / "
                         f"{r['channels']} channels differ</span>"))
        body = "".join(
            f"<tr><td style='padding:2px 10px 2px 0;color:#555'>{k}</td>"
            f"<td style='padding:2px 0'><b>{v}</b></td></tr>" for k, v in rows)
        return f"<table style='font-family:monospace;font-size:13px'>{body}</table>"

    def show(self):
        """Build and display the panel. Returns the root widget."""
        if widgets is None:
            raise RuntimeError("ipywidgets is not available in this kernel")
        self.load()

        preset = widgets.Dropdown(options=self.presets, value="document",
                                  description="preset", layout=widgets.Layout(width="320px"))
        frames = widgets.IntSlider(value=3, min=1, max=20, step=1,
                                   description="frames", layout=widgets.Layout(width="320px"))
        run = widgets.Button(description="Run", button_style="primary",
                             layout=widgets.Layout(width="120px"))
        bench = widgets.Button(description="Benchmark x20",
                               layout=widgets.Layout(width="150px"))
        status = widgets.HTML("<i>press Run to send a frame through the kernel</i>")
        metrics = widgets.HTML("")
        image = widgets.Image(format="png", width=640)

        def _run(_=None):
            r = self.apply(preset.value, frames.value)
            image.value = _png_bytes(r["image"])
            metrics.value = self._metrics_html(r)
            status.value = f"<span style='color:#1b5e20'>ran {r['preset']}</span>"

        def _bench(_=None):
            r = self.apply(preset.value, 20)
            image.value = _png_bytes(r["image"])
            metrics.value = self._metrics_html(r)
            status.value = (f"<span style='color:#1b5e20'>benchmark: best of 20 frames "
                            f"= {r['frame_ms']} ms</span>")

        run.on_click(_run)
        bench.on_click(_bench)

        # A first run so the panel is never empty.
        _run()

        controls = widgets.VBox([
            widgets.HBox([preset, frames]),
            widgets.HBox([run, bench]),
            status,
        ])
        body = widgets.HBox([
            controls,
            widgets.VBox([image, widgets.HTML(
                "<small>left: original &nbsp;|&nbsp; this image is the kernel's "
                "actual DMA readback</small>")]),
            metrics,
        ], layout=widgets.Layout(align_items="flex-start"))
        root = widgets.VBox([body])

        self._widgets = dict(preset=preset, frames=frames, run=run, bench=bench,
                             status=status, metrics=metrics, image=image, root=root)
        display(root)
        return root


if __name__ == "__main__":
    # Headless smoke test: no widgets, just prove the hardware path works.
    panel = EnhancePanel()
    for name in ("pass", "document"):
        r = panel.apply(name, 1)
        print(f"{name:<9} {r['frame_ms']:6.1f} ms  "
              f"mismatched {r.get('mismatched', 'n/a')}  "
              f"latency {r.get('latency_cycles', 'n/a')} clocks")
