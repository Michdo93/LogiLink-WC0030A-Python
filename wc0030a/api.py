"""HTTP-Client für die LogiLink WC0030A / Apexis APM-H803-MPC."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterator

import requests

from . import commands as C
from .parser import parse_js_vars

log = logging.getLogger(__name__)

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

# Kandidaten in Reihenfolge; der erste, der ein JPEG liefert, wird gemerkt.
SNAPSHOT_CANDIDATES = [
    "/cgi-bin/video_snapshot.cgi",
    "/cgi-bin/mobile_snapshot.cgi",
    "/snapshot.cgi",
    "/cgi-bin/snapshot.cgi",
]


class CameraError(RuntimeError):
    pass


class Camera:
    """Kapselt alle bekannten CGI-Aufrufe der Kamera.

    Authentifizierung: wie die Original-Weboberfläche per Query-Parameter
    ``user`` und ``pwd`` (siehe main.htm: write_log.cgi?type=..&user=..&pwd=..).
    """

    def __init__(self, host: str, user: str = "admin", password: str = "",
                 port: int = 80, timeout: float = 5.0,
                 invert_v: bool = False, invert_h: bool = False,
                 step_seconds: float = 0.4):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.invert_v = invert_v
        self.invert_h = invert_h
        self.step_seconds = step_seconds
        self.base_url = f"http://{host}" + (f":{port}" if port != 80 else "")
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._snapshot_path: str | None = None
        self._preset_count: int | None = None

    # ------------------------------------------------------------------ Basis
    @property
    def auth(self) -> dict[str, str]:
        return {"user": self.user, "pwd": self.password}

    def url(self, path: str, **params: Any) -> str:
        """Vollständige URL inkl. Zugangsdaten (z. B. für openHAB/VLC)."""
        req = requests.Request("GET", self._abs(path), params={**params, **self.auth}).prepare()
        return req.url

    def _abs(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/cgi-bin/" + path
        return self.base_url + path

    def _get(self, path: str, params: dict[str, Any] | None = None,
             stream: bool = False, timeout: float | None = None) -> requests.Response:
        p = dict(params or {})
        p.update(self.auth)
        try:
            if stream:  # eigene Verbindung, damit der Stream keine Befehle blockiert
                r = requests.get(self._abs(path), params=p, stream=True,
                                 timeout=timeout or self.timeout)
            else:
                with self._lock:
                    r = self._session.get(self._abs(path), params=p,
                                          timeout=timeout or self.timeout)
        except requests.RequestException as exc:
            raise CameraError(f"{path}: {exc}") from exc
        if r.status_code == 401:
            raise CameraError(f"{path}: Benutzername oder Passwort falsch (401)")
        if r.status_code != 200:
            raise CameraError(f"{path}: HTTP {r.status_code}")
        return r

    def raw(self, cgi: str, **params: Any) -> str:
        """Beliebigen CGI-Aufruf absetzen und den Text zurückgeben."""
        name = cgi.rsplit("/", 1)[-1]
        if name in C.DANGEROUS_CGIS and not params.pop("_force", False):
            raise CameraError(f"{name} ist als gefährlich markiert – nur mit --force bzw. _force=True")
        text = self._get(cgi, params).text
        if text.strip().startswith("params error"):
            raise CameraError(f"{cgi}: Kamera meldet 'params error' (Parameter falsch/fehlend)")
        return text

    def get_vars(self, cgi: str, strip_prefix: bool = True, **params: Any) -> dict[str, Any]:
        """get_*.cgi abfragen und als dict zurückgeben."""
        return parse_js_vars(self.raw(cgi, **params), strip_prefix=strip_prefix)

    # ------------------------------------------------------------ Statusdaten
    def status(self) -> dict[str, Any]:
        return self.get_vars("get_status.cgi")

    def real_status(self) -> dict[str, Any]:
        """Laufzeitstatus: Bewegung, Alarm, Eingänge, Auflösung, Framerate …"""
        return self.get_vars("get_real_status.cgi")

    def sd_status(self) -> dict[str, Any]:
        return self.get_vars("get_sdc_status.cgi")

    def preset_status(self) -> dict[str, Any]:
        return self.get_vars("get_preset_status.cgi")

    def camera_vars(self) -> dict[str, Any]:
        """Bildparameter (Helligkeit, Kontrast …). Braucht Login."""
        return self.get_vars("get_camera_vars.cgi")

    def params(self) -> dict[str, Any]:
        """Kompletter Parametersatz. Braucht Admin-Login."""
        return self.get_vars("get_params.cgi")

    def check_user(self) -> dict[str, Any]:
        return self.get_vars("check_user.cgi")

    def cruise_list(self) -> dict[str, Any]:
        return self.get_vars("get_list_cruise.cgi")

    def cruise(self, index: int) -> dict[str, Any]:
        return self.get_vars("get_cruise.cgi", index=index)

    def motion_schedule(self) -> dict[str, Any]:
        return self.get_vars("get_motion_schedule.cgi")

    def alarm_schedule(self) -> dict[str, Any]:
        return self.get_vars("get_alarm_schedule.cgi")

    def log_page(self, page: int = 1) -> dict[str, Any]:
        return self.get_vars("get_log_page.cgi", page=page)

    def all_status(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cgi in C.READ_CGIS:
            try:
                out[cgi] = self.get_vars(cgi)
            except CameraError as exc:
                out[cgi] = {"error": str(exc)}
        return out

    def preset_count(self) -> int:
        if self._preset_count is None:
            try:
                n = int(self.preset_status().get("presetsta_num", 0))
            except (CameraError, ValueError):
                n = 0
            self._preset_count = n if 0 < n <= C.PRESET_MAX else 9
        return self._preset_count

    # --------------------------------------------------------------- PTZ
    def decoder(self, command: int, **extra: Any) -> None:
        self.raw("decoder_control.cgi", command=command, **extra)
        log.debug("decoder_control command=%s", command)

    def _map_dir(self, direction: str) -> str:
        d = direction.lower().replace("-", "_")
        if d not in C.MOVE:
            raise ValueError(f"Unbekannte Richtung '{direction}'. Erlaubt: {', '.join(C.MOVE)}")
        if self.invert_v:
            d = C.INVERT_V.get(d, d)
        if self.invert_h:
            d = C.INVERT_H.get(d, d)
        return d

    def move(self, direction: str) -> None:
        """Dauerbewegung starten (läuft bis stop() oder Endanschlag)."""
        self.decoder(C.MOVE[self._map_dir(direction)][0])

    def stop(self, direction: str | None = None) -> None:
        code = C.MOVE[self._map_dir(direction)][1] if direction else C.STOP
        self.decoder(code)

    def step(self, direction: str, seconds: float | None = None) -> None:
        """Kurz in eine Richtung fahren und wieder anhalten."""
        self.move(direction)
        time.sleep(self.step_seconds if seconds is None else seconds)
        self.stop(direction)

    def center(self) -> None:
        self.decoder(C.CENTER)

    def patrol(self, axis: str, start: bool = True) -> None:
        axis = axis.lower()[:1]
        if axis == "h":
            self.decoder(C.PATROL_H_START if start else C.PATROL_H_STOP)
        elif axis == "v":
            self.decoder(C.PATROL_V_START if start else C.PATROL_V_STOP)
        else:
            raise ValueError("axis muss 'h' oder 'v' sein")

    def patrol_stop(self) -> None:
        self.decoder(C.PATROL_H_STOP)
        self.decoder(C.PATROL_V_STOP)

    def preset_goto(self, n: int) -> None:
        self._check_preset(n)
        self.decoder(C.preset_goto_code(n))

    def preset_set(self, n: int) -> None:
        self._check_preset(n)
        self.decoder(C.preset_set_code(n))

    def _check_preset(self, n: int) -> None:
        if not 1 <= n <= self.preset_count():
            raise ValueError(f"Preset {n} außerhalb 1..{self.preset_count()}")

    def io_output(self, on: bool) -> None:
        """Schaltausgang (in der Weboberfläche: 'Relay an/aus')."""
        self.decoder(C.IO_ON if on else C.IO_OFF)

    # ----------------------------------------------------- Bild/Einstellungen
    def set_camera_vars(self, **values: Any) -> str:
        """Bildparameter setzen – Parameternamen noch unbestätigt.

        Die Namen stehen in der Live-Seite der Kamera, die im Dump fehlt.
        `wc0030a probe` lädt sie herunter und listet die Parameter von
        set_camera_vars.cgi im Bericht auf.
        """
        return self.raw("set_camera_vars.cgi", **values)

    def reboot(self) -> None:
        self.raw("reboot.cgi", _force=True)

    # --------------------------------------------------------------- Bilder
    def snapshot(self) -> bytes:
        """Ein JPEG holen. Der funktionierende Endpunkt wird gemerkt."""
        paths = [self._snapshot_path] if self._snapshot_path else SNAPSHOT_CANDIDATES
        errors = []
        for path in paths:
            try:
                r = self._get(path, timeout=max(self.timeout, 8))
            except CameraError as exc:
                errors.append(str(exc))
                continue
            data = r.content
            if data.startswith(JPEG_SOI):
                self._snapshot_path = path
                return data
            # Manche Firmwares liefern eine HTML-Seite mit <img src=...>
            errors.append(f"{path}: kein JPEG ({r.headers.get('Content-Type')}, {len(data)} Bytes)")
        self._snapshot_path = None
        raise CameraError("Snapshot fehlgeschlagen: " + " | ".join(errors))

    def mjpeg_url(self, **params: Any) -> str:
        return self.url("/cgi-bin/videostream.cgi", **params)

    def mjpeg_frames(self, **params: Any) -> Iterator[bytes]:
        """Liefert einzelne JPEG-Frames aus dem MJPEG-Stream."""
        r = self._get("/cgi-bin/videostream.cgi", params, stream=True, timeout=10)
        buf = b""
        try:
            for chunk in r.iter_content(chunk_size=8192):
                buf += chunk
                while True:
                    a = buf.find(JPEG_SOI)
                    if a < 0:
                        buf = buf[-1:]
                        break
                    b = buf.find(JPEG_EOI, a + 2)
                    if b < 0:
                        buf = buf[a:]
                        break
                    yield buf[a:b + 2]
                    buf = buf[b + 2:]
                if len(buf) > 4_000_000:  # Schutz gegen kaputten Stream
                    buf = b""
        finally:
            r.close()

    def rtsp_url(self, path: str = "/11") -> str:
        """RTSP-URL (Port aus get_status). Pfad mit `wc0030a probe` ermitteln."""
        try:
            port = int(self.status().get("rtsp_port", 554))
        except CameraError:
            port = 554
        return f"rtsp://{self.user}:{self.password}@{self.host}:{port}{path}"
