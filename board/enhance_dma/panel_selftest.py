"""Headless check that the widget tree builds and the first run works."""

from enhance_panel import EnhancePanel

panel = EnhancePanel()
root = panel.show()
print("root widget:", type(root).__name__)
kids = panel._widgets
print("widgets:", sorted(kids))
print("preset widget options:", list(kids["preset"].options))
print("image bytes:", len(kids["image"].value))
print("metrics html chars:", len(kids["metrics"].value))
print("last run:", panel.last["preset"], "mismatched", panel.last["mismatched"],
      "latency", panel.last.get("latency_cycles"))
print("PANEL OK")
