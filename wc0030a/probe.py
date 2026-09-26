"""Erkundung der echten Kamera (nur lesend).

Der gespeicherte Dump enthält die Seiten mit der eigentlichen Steuerlogik
nicht (ffserver.htm, mobile.htm, Einstellungsseiten), und get_camera_vars /
get_params kamen leer zurück, weil sie ohne Login abgerufen wurden.

`wc0030a probe` holt das mit Login nach:
  1. alle lesenden get_*.cgi  -> JSON
  2. crawlt alle .htm/.js-Seiten ab main.htm/login.htm
  3. extrahiert aus dem JS jeden CGI-Aufruf mit seinen Parameternamen
     und jede decoder_control-Nummer
  4. prüft RTSP-Pfade per DESCRIBE (404 = gibt es nicht, 401/200 = gibt es)
Ergebnis: Ordner + ZIP + report.md. Es werden keine set_*.cgi aufgerufen.
"""

from __future__ import annotations

import json
import re
import socket
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from . import commands as C
from .api import Camera, CameraError

START_PAGES = [
    "index.htm", "index.html", "main.htm", "login.htm", "ffserver.htm", "activex.htm",
    "mobile.htm", "ptz.htm", "video.htm", "media.htm", "setting.htm", "left.htm",
    "right.htm", "top.htm", "quick_install.htm", "vlc_install.htm",
    "language/german.js", "language/english.js", "language/lang.js",
]

REF_RE = re.compile(r"""["'(=\s]([\w./-]+\.(?:htm|html|js))(?:[?#"'\s)])""", re.I)
CGI_RE = re.compile(r"(\w+\.cgi)([^\n]{0,500})", re.I)
PARAM_RE = re.compile(r"[?&](\w+)=")
DECODER_RE = re.compile(r"decoder_control\.cgi\?command=['\"]?\s*\+?\s*(\w+)", re.I)
CALL_NUM_RE = re.compile(r"""on(?:mousedown|mouseup|click|touchstart|touchend)\s*=\s*["']([^"']*?\(\s*\d+[^"']*)["']""", re.I)

RTSP_PATHS = ["/11", "/12", "/live/ch0", "/live/ch1", "/ch0", "/ch1", "/live.sdp",
              "/h264", "/stream1", "/0", "/1", "/"]


def _fetch(cam: Camera, page: str) -> requests.Response | None:
    url = cam.base_url + "/" + page.lstrip("/")
    try:
        r = requests.get(url, params=cam.auth, timeout=cam.timeout)
    except requests.RequestException:
        return None
    return r if r.status_code == 200 else None


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace")


def crawl(cam: Camera, out: Path, limit: int = 200) -> dict[str, str]:
    pages: dict[str, str] = {}
    queue = list(START_PAGES)
    seen: set[str] = set()
    while queue and len(seen) < limit:
        page = queue.pop(0).lstrip("/")
        if page in seen:
            continue
        seen.add(page)
        r = _fetch(cam, page)
        if r is None:
            continue
        text = _decode(r.content)
        pages[page] = text
        dest = out / "web" / page
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        base = "http://x/" + page
        for ref in REF_RE.findall(" " + text):
            p = urlparse(urljoin(base, ref)).path.lstrip("/")
            if p and p not in seen and ".cgi" not in p:
                queue.append(p)
    return pages


def analyse(pages: dict[str, str]) -> dict:
    cgi_params: dict[str, set[str]] = defaultdict(set)
    cgi_where: dict[str, set[str]] = defaultdict(set)
    decoder: dict[str, set[str]] = defaultdict(set)
    handlers: list[str] = []
    for page, text in pages.items():
        for name, rest in CGI_RE.findall(text):
            cgi_where[name].add(page)
            # Parameter bis zum nächsten CGI-Namen in derselben Zeile
            rest = re.split(r"\w+\.cgi", rest, maxsplit=1)[0]
            for p in PARAM_RE.findall(rest):
                if p not in ("user", "pwd", "next_url"):
                    cgi_params[name].add(p)
        for m in DECODER_RE.findall(text):
            decoder[page].add(m)
        for h in CALL_NUM_RE.findall(text):
            handlers.append(f"{page}: {h.strip()}")
    return {
        "cgi_params": {k: sorted(v) for k, v in sorted(cgi_params.items())},
        "cgi_where": {k: sorted(v) for k, v in sorted(cgi_where.items())},
        "decoder_refs": {k: sorted(v) for k, v in decoder.items()},
        "handlers": sorted(set(handlers)),
    }


SECRET_RE = re.compile(r"((?:var\s+)?\w*(?:pwd|pass|psk|key|guid)\w*\s*=\s*)(['\"])[^'\"]*\2", re.I)


def redact(text: str) -> str:
    """Passwörter/Schlüssel aus JS-Antworten entfernen (Bericht ist teilbar)."""
    return SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(2)}", text)


def _redact_obj(obj):
    if isinstance(obj, dict):
        return {k: ("***" if re.search(r"pwd|pass|psk|key|guid", k, re.I) and v not in ("", None)
                    else _redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(v) for v in obj]
    return obj


def rtsp_probe(host: str, port: int) -> dict[str, str]:
    """DESCRIBE ohne Login: 401 heißt 'Pfad existiert, Login nötig'."""
    res = {}
    for path in RTSP_PATHS:
        url = f"rtsp://{host}:{port}{path}"
        req = (f"DESCRIBE {url} RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\n"
               f"User-Agent: wc0030a-probe\r\n\r\n").encode()
        try:
            with socket.create_connection((host, port), timeout=3) as s:
                s.sendall(req)
                line = s.recv(256).split(b"\r\n", 1)[0].decode(errors="replace")
        except OSError as exc:
            line = f"Fehler: {exc}"
        res[path] = line
    return res


def run(cam: Camera, out_dir: str = "probe_out") -> Path:
    out = Path(out_dir)
    (out / "cgi").mkdir(parents=True, exist_ok=True)

    status = {}
    for cgi in C.READ_CGIS:
        try:
            text = cam.raw(cgi)
            (out / "cgi" / cgi).write_text(redact(text), encoding="utf-8")
            status[cgi] = cam.get_vars(cgi) if text.strip() else {}
        except CameraError as exc:
            status[cgi] = {"error": str(exc)}
    status = _redact_obj(status)
    (out / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")

    pages = crawl(cam, out)
    info = analyse(pages)
    (out / "analysis.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        rtsp_port = int(status.get("get_status.cgi", {}).get("rtsp_port", 554))
    except (TypeError, ValueError):
        rtsp_port = 554
    rtsp = rtsp_probe(cam.host, rtsp_port)

    lines = ["# Probe-Bericht WC0030A", ""]
    st = status.get("get_status.cgi", {})
    lines += [f"- Modell: {st.get('prot_mode')}  Firmware: {st.get('server_version')}  WebUI: {st.get('client_version')}",
              f"- Seiten gefunden: {len(pages)}", "", "## CGI-Aufrufe aus der Weboberfläche", ""]
    for name, params in info["cgi_params"].items():
        lines.append(f"- `{name}`: {', '.join(params) or '–'}  _(in {', '.join(info['cgi_where'][name])})_")
    lines += ["", "## decoder_control-Referenzen", ""]
    for page, refs in info["decoder_refs"].items():
        lines.append(f"- {page}: {', '.join(refs)}")
    lines += ["", "## Event-Handler mit Zahlen (PTZ-Buttons)", ""]
    lines += [f"- `{h}`" for h in info["handlers"][:300]]
    lines += ["", "## RTSP DESCRIBE", ""]
    lines += [f"- `{p}` → {r}" for p, r in rtsp.items()]
    lines += ["", "## Status (Login)", "", "```json", json.dumps(status, indent=2, ensure_ascii=False), "```"]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")

    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(out.parent))
    return zip_path
