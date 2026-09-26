# LogiLink-WC0030A-Python

Steuerung der Pan/Tilt-IP-Kamera **LogiLink WC0030A** per Python – als Bibliothek, Kommandozeile, Weboberfläche und MQTT-Brücke für openHAB.

Die WC0030A ist ein OEM-Gerät von Apexis. Die Kamera meldet sich in `get_status.cgi` als **APM-H803-MPC** (Firmware `83.2.5.69c3`, WebUI `17.14.5.45`, Sensor OV9710, 1280×720). Die HTTP-Schnittstelle entspricht in den Grundzügen dem Foscam-MJPEG-CGI-SDK, weicht aber an einigen Stellen ab – siehe [Stand der Befehle](#stand-der-befehle).

## Installation

```bash
git clone https://github.com/Michdo93/LogiLink-WC0030A-Python.git
cd LogiLink-WC0030A-Python
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # IP und Passwort eintragen
```

Die Zugangsdaten stehen nicht mehr im Code. Reihenfolge: Defaults < `config.yaml` < Umgebungsvariablen (`WC0030A_HOST`, `WC0030A_PASSWORD`, `MQTT_HOST` …) < CLI-Optionen (`--host`, `--password`).

## Kommandozeile

```bash
python -m wc0030a status                 # Geräte- und Laufzeitstatus als JSON
python -m wc0030a status --all           # alle lesenden CGIs
python -m wc0030a ptz left               # ein kurzer Schritt (camera.step_seconds)
python -m wc0030a ptz left --hold 2      # 2 s fahren
python -m wc0030a ptz up --continuous    # fahren bis ...
python -m wc0030a stop
python -m wc0030a ptz center
python -m wc0030a preset goto 3          # Presets 1–9
python -m wc0030a preset set 3
python -m wc0030a patrol h start         # h | v | all ... start | stop
python -m wc0030a relay on
python -m wc0030a snapshot bild.jpg
python -m wc0030a urls                   # Snapshot-/MJPEG-/RTSP-URL für VLC, openHAB …
python -m wc0030a raw get_camera_vars.cgi
python -m wc0030a probe                  # Kamera erkunden (siehe unten)
python -m wc0030a web                    # Weboberfläche auf Port 5000
python -m wc0030a mqtt                   # MQTT-Brücke
```

Die alte Syntax funktioniert weiter: `python3 camera_control.py --cmd preset1_get`, `--snapshot x.jpg`, ohne Argumente startet die Weboberfläche.

## Weboberfläche

`python -m wc0030a web` → `http://<pi>:5000`

Live-Bild, Steuerkreuz mit acht Richtungen (**gedrückt halten** fährt, loslassen hält an), Presets 1–9 mit Speichermodus, Patrouille, Relais, Statusanzeige mit Bewegungsmeldung. Der MJPEG-Stream wird über `/video_feed` durchgereicht, das Kamera-Passwort verlässt den Pi also nicht.

## Bibliothek

```python
from wc0030a import Camera

cam = Camera("192.168.0.35", "admin", "geheim")
cam.step("right")              # kurz fahren, anhalten
cam.move("up"); cam.stop()     # Dauerfahrt
cam.preset_goto(2)
print(cam.real_status()["realstatus_motion"])
open("x.jpg", "wb").write(cam.snapshot())
for frame in cam.mjpeg_frames():   # einzelne JPEGs, z. B. für OpenCV
    ...
```

## openHAB-Integration

Die Kamera-Logik steckt in **einem** Python-Programm (`python -m wc0030a mqtt`), das HTTP zur Kamera und MQTT zum Broker vereint. openHAB bindet es über das MQTT-Binding an; Regeln verknüpfen nur noch Ereignisse mit Befehlen.

Beispieldateien liegen in `openhab/` (Things, Items, Sitemap, MAP-Transformation, JS-Regel).

### Topics

| Topic | Richtung | Inhalt |
|---|---|---|
| `wc0030a/status` | → openHAB | `online` / `offline` (LWT, retained) |
| `wc0030a/state/motion` | → | `ON` / `OFF` (Poll alle 2 s) |
| `wc0030a/state/alarm`, `input1`, `input2`, `sd_alarm` | → | `ON` / `OFF` |
| `wc0030a/state/resolution`, `framerate`, `ip` | → | Laufzeitwerte |
| `wc0030a/state/model`, `firmware`, `webui`, `alias`, `lamp` | → | Geräteinfo (alle 60 s) |
| `wc0030a/state/sd_ok`, `sd_free_mb`, `sd_total_mb` | → | SD-Karte |
| `wc0030a/state/presets` | → | Anzahl Presets (9) |
| `wc0030a/state/relay`, `patrol` | → | zuletzt gesendeter Zustand (Kamera meldet ihn nicht zurück) |
| `wc0030a/state/camera/<name>` | → | Bildparameter aus `get_camera_vars.cgi` |
| `wc0030a/state/json/<cgi>` | → | vollständige Antwort als JSON |
| `wc0030a/state/last_error` | → | letzte Fehlermeldung |
| `wc0030a/snapshot` | → | JPEG-Bytes (Image-Channel), auf Befehl, bei Bewegung oder im Intervall |
| `wc0030a/cmd/ptz` | ← | `UP` `DOWN` `LEFT` `RIGHT` `UP_LEFT` `UP_RIGHT` `DOWN_LEFT` `DOWN_RIGHT` `CENTER` `STOP` – Einzelschritt |
| `wc0030a/cmd/ptz/move` | ← | Richtung → Dauerfahrt, `STOP` beendet |
| `wc0030a/cmd/preset` | ← | `1`–`9` anfahren |
| `wc0030a/cmd/preset/set` | ← | `1`–`9` speichern |
| `wc0030a/cmd/patrol` | ← | `HORIZONTAL` / `VERTICAL` / `STOP` |
| `wc0030a/cmd/relay` | ← | `ON` / `OFF` |
| `wc0030a/cmd/snapshot` | ← | beliebig → neues Bild |
| `wc0030a/cmd/refresh` | ← | alle Zustände neu lesen |
| `wc0030a/cmd/camera_vars` | ← | JSON → `set_camera_vars.cgi` (Namen per `probe` klären) |
| `wc0030a/cmd/reboot` | ← | `REBOOT` |
| `wc0030a/cmd/raw` | ← | `{"cgi": "...", "params": {...}}`, nur mit `mqtt.allow_raw: true` |

### Video in openHAB

Zwei Wege, beide in den Beispieldateien vorbereitet:

1. **Über den Pi:** `web`-Dienst laufen lassen, in der Sitemap `Video url="http://<pi>:5000/video_feed" encoding="mjpeg"`. Kein Kamera-Passwort in openHAB.
2. **IpCamera-Binding** (`ipcamera:httponly`) mit `snapshotUrl`/`mjpegUrl` direkt zur Kamera. Die URLs gibt `python -m wc0030a urls` aus.

### Dienste

```bash
sudo cp -r . /opt/LogiLink-WC0030A-Python
sudo cp systemd/wc0030a-mqtt.service systemd/wc0030a-web.service /etc/systemd/system/
sudo systemctl enable --now wc0030a-mqtt wc0030a-web
```

## Stand der Befehle

Grundlage: der Web-Dump der Kamera (`cgi-bin`-Liste, `model.js`, Sprachdatei) und das Foscam-MJPEG-SDK.

| Funktion | Aufruf | Stand |
|---|---|---|
| Status, Laufzeitstatus, SD, Presets, Zeitpläne, Kurse | `get_*.cgi` → JS-Variablen | aus dem Dump belegt, Parser getestet |
| Schwenken/Neigen | `decoder_control.cgi?command=0…7` (Start/Stopp je Richtung) | Foscam-Standard; Buttons in der Sprachdatei vorhanden |
| Diagonalen | `command=90…93` | Foscam-Standard; **die alte Version nutzte 9/11/13/15** |
| Mitte, Patrouillen | `25`, `26/27`, `28/29` | Foscam-Standard |
| Presets | setzen `30+2(n−1)`, anfahren `31+2(n−1)` | Kamera meldet 9 Presets (`get_preset_status`) |
| Relais | `94` / `95` | Foscam-Standard |
| Snapshot | `video_snapshot.cgi`, Fallback `mobile_snapshot.cgi`, `/snapshot.cgi` | **`snapshot.cgi` fehlt in der cgi-bin-Liste dieser Firmware** |
| MJPEG | `videostream.cgi` | in der Liste vorhanden |
| Bildparameter | `get_camera_vars.cgi` / `set_camera_vars.cgi` | **`camera_control.cgi` gibt es auf dieser Firmware nicht**; Parameternamen per `probe` klären |
| Status-LED | `set_lamp.cgi` (Menü „Indikator“) | Parameternamen per `probe` klären |
| RTSP | Port 554 laut `get_status` | Pfad per `probe` klären |
| Kurse (Preset-Touren) | `get_list_cruise.cgi`, `get_cruise.cgi`, `set_cruise.cgi`, `control_cruise.cgi` | lesen implementiert, schreiben per `raw` |

Laut `model.js` hat das Modell APM-H803-MPC weder Zoom, Fokus noch Iris, und keine PTZ-Protokolleinstellung (RS485). Infrarot-Steuerung taucht in der Weboberfläche nicht auf; die IR-LEDs schalten automatisch.

### Die fehlenden Befehle ermitteln: `probe`

Im Dump fehlen genau die Seiten mit der Steuerlogik (`ffserver.htm`, `mobile.htm`, die Einstellungsseiten), und `get_camera_vars.cgi` / `get_params.cgi` kamen leer zurück, weil ohne Login abgerufen. `probe` holt das nach – **nur lesend**, es werden keine `set_*.cgi` aufgerufen:

```bash
python -m wc0030a probe
```

Ergebnis: `probe_out/` und `probe_out.zip` mit

- allen `get_*.cgi`-Antworten mit Login (Passwörter und Schlüssel geschwärzt),
- allen erreichbaren `.htm`/`.js`-Seiten der Kamera,
- `report.md`: jeder CGI-Aufruf aus der Weboberfläche mit seinen Parameternamen, alle `decoder_control`-Stellen, alle Button-Handler mit Befehlsnummern, RTSP-Pfadtest (`404` = gibt es nicht, `401`/`200` = gibt es).

Damit lassen sich die offenen Punkte der Tabelle schließen.

## Entwickeln ohne Kamera

`tools/fake_camera.py` simuliert die Kamera mit den Antworten aus dem Dump, protokolliert PTZ-Befehle, liefert Test-JPEGs und einen MJPEG-Stream. Bewegung per `http://localhost:8080/sim/motion?on=1`.

```bash
python tools/fake_camera.py --port 8080 &
WC0030A_HOST=127.0.0.1 WC0030A_PORT=8080 WC0030A_PASSWORD=test python -m wc0030a web
```

## Sicherheit

Die Apexis-Firmware dieser Generation hat bekannte, nicht behobene Lücken (u. a. CVE-2017-17101, CVSS 9.8: Zugriff auf Stream und Konfiguration ohne Login). `get_status.cgi` und `get_real_status.cgi` antworten schon jetzt ohne Anmeldung. Empfehlung: Kamera in ein eigenes VLAN/IoT-Netz ohne Internetzugang, keine Portweiterleitung, UPnP, DDNS (`oipcam.com`) und P2P (TUTK) in der Kamera abschalten. Zugriff von außen nur über openHAB bzw. den Pi.
