#!/usr/bin/env python3
"""Minimaler Kamera-Simulator zum Entwickeln/Testen ohne Hardware.

Liefert die im Dump gespeicherten get_*.cgi-Antworten, protokolliert
decoder_control-Befehle, erzeugt ein Test-JPEG und einen MJPEG-Stream.
Bewegung kann über /sim/motion?on=1 simuliert werden.

  python tools/fake_camera.py --port 8080
  WC0030A_HOST=127.0.0.1 WC0030A_PORT=8080 WC0030A_PASSWORD=test python -m wc0030a status
"""

import argparse
import io
import re
import time
from pathlib import Path

from flask import Flask, Response, request

HERE = Path(__file__).parent / "fake_responses"
USER, PWD = "admin", "test"
app = Flask(__name__)
state = {"motion": 0, "log": []}


def jpeg(text: str) -> bytes:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 360), (30, 40, 55))
        ImageDraw.Draw(img).text((20, 20), text, fill=(230, 230, 230))
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        return buf.getvalue()
    except ImportError:
        return b"\xff\xd8\xff\xe0" + text.encode() + b"\xff\xd9"


def authed() -> bool:
    return request.args.get("user") == USER and request.args.get("pwd") == PWD


@app.route("/cgi-bin/<name>")
def cgi(name):
    if name in ("get_status.cgi", "get_real_status.cgi"):  # wie im Original ohne Login lesbar
        pass
    elif not authed():
        return "var ret_check_user=3;\nvar ret_user_right=-1;\n" if name == "check_user.cgi" else "params error.\r\n"
    if name == "decoder_control.cgi":
        if "command" not in request.args:
            return "params error.\r\n"
        state["log"].append((time.time(), int(request.args["command"])))
        print("decoder_control", request.args["command"])
        return "ok.\r\n"
    if name in ("video_snapshot.cgi", "mobile_snapshot.cgi"):
        return Response(jpeg(time.strftime("%H:%M:%S")), mimetype="image/jpeg")
    if name == "videostream.cgi":
        def gen():
            for _ in range(10000):
                f = jpeg("LIVE " + time.strftime("%H:%M:%S"))
                yield b"--ipcamera\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(f) + f + b"\r\n"
                time.sleep(0.2)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=ipcamera")
    if name == "get_camera_vars.cgi":
        # ERFUNDENE Variablennamen – nur für den Simulator, nicht die echte Firmware!
        return "var ret_camvars_result=1;\nvar bright=128;\nvar contrast=153;\nvar hue=0;\nvar satura=120;\nvar ptzspeed=60;\n"
    if name == "get_preset_status.cgi":
        return "var ret_presetsta_result=1;\nvar ret_presetsta_num=9;\nvar ret_presetsta_enable=new Array();\n" + \
               "".join(f"ret_presetsta_enable[{i}]={1 if i < 3 else 0};\n" for i in range(9))
    f = HERE / name
    if f.exists():
        text = f.read_text(encoding="utf-8", errors="replace")
        if name == "get_real_status.cgi":
            text = re.sub(r"realstatus_motion=\d", f"realstatus_motion={state['motion']}", text)
        return Response(text, mimetype="text/plain")
    return "params error.\r\n"


@app.route("/ffserver.htm")
def ffserver():
    return ('<script>function ptz(c){action_zone.location="/cgi-bin/decoder_control.cgi?command="+c+"&onestep=0&user="+top.user+"&pwd="+top.pwd;}'
            'function set_bright(v){action_zone.location="/cgi-bin/set_camera_vars.cgi?bright="+v+"&user="+top.user+"&pwd="+top.pwd;}</script>'
            '<img onmousedown="ptz(0)" onmouseup="ptz(1)"><a href="setting.htm">x</a>')


@app.route("/setting.htm")
def setting():
    return '<script src="js/model.js"></script><script>x="/cgi-bin/set_lamp.cgi?lamp="+v;</script>'


@app.route("/sim/motion")
def sim_motion():
    state["motion"] = int(request.args.get("on", 1))
    return str(state["motion"])


@app.route("/sim/log")
def sim_log():
    return {"log": state["log"][-50:]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    app.run(port=ap.parse_args().port, threaded=True)
