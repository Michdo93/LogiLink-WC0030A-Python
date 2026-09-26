#!/usr/bin/env python3
"""Kompatibilitäts-Wrapper für die alte Aufrufsyntax.

  python3 camera_control.py                 -> Weboberfläche
  python3 camera_control.py --cmd left      -> Einzelschritt
  python3 camera_control.py --cmd preset1_get
  python3 camera_control.py --snapshot x.jpg

Neu ist `python3 -m wc0030a ...` (siehe README).
"""

import argparse
import re
import sys

from wc0030a.__main__ import main

OLD = {
    "center": ["ptz", "center"], "stop": ["stop"],
    "patrol_h_start": ["patrol", "h", "start"], "patrol_h_stop": ["patrol", "h", "stop"],
    "patrol_v_start": ["patrol", "v", "start"], "patrol_v_stop": ["patrol", "v", "stop"],
    "stop_patrol": ["patrol", "all", "stop"], "patrol_h": ["patrol", "h", "start"],
    "patrol_v": ["patrol", "v", "start"],
    "relay_on": ["relay", "on"], "relay_off": ["relay", "off"],
    "ir_on": ["relay", "on"], "ir_off": ["relay", "off"],
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd")
    ap.add_argument("--snapshot")
    ap.add_argument("--server", action="store_true")
    a, rest = ap.parse_known_args()
    if a.cmd:
        m = re.fullmatch(r"preset(\d+)(?:_(get|set))?", a.cmd)
        if m:
            argv = ["preset", "set" if m.group(2) == "set" else "goto", m.group(1)]
        else:
            argv = OLD.get(a.cmd, ["ptz", a.cmd])
    elif a.snapshot:
        argv = ["snapshot", a.snapshot]
    else:
        argv = ["web"]
    sys.exit(main(rest + argv))
