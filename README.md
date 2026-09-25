# LogiLink-WC0030A-Python

Diese Lösung ist eine **Flask-Webanwendung**. Der entscheidende Vorteil: Sie läuft perfekt **headless** (z. B. auf deinem Raspberry Pi oder Server im Hintergrund), lässt sich aber gleichzeitig von jedem Browser aus (PC, Smartphone, Tablet) bedienen – mitsamt Live-Stream, Steuerungsknöpfen und Snapshot-Downloads.

Zusätzlich bietet das Skript ein **Command-Line-Interface (CLI)** für die reine Headless-Steuerung über das Terminal oder Cronjobs.

---

## Vorbereitung & Installation

Du benötigst lediglich `requests` für die HTTP-Kommunikation und `Flask` für die Weboberfläche:

```bash
pip install flask requests
```

---

## Anwendungsbeispiele & Nutzung

### A. Web-GUI inklusive Stream & Buttons starten

Starte das Skript einfach ohne Parameter (oder mit `--server`):

```bash
python3 camera_control.py
```

Öffne nun deinen Browser unter **`http://<IP-deines-Rechners-oder-RaspberryPi>:5000`**. Du erhältst ein dunkles Dashboard mit Live-Stream, Steuerkreuz, Preset-Tasten und Instant-Snapshot-Download!

---

### B. Headless über Terminal / Skripte nutzen (Ohne GUI)

Du kannst die Kamera mit demselben Skript auch **rein über die Kommandozeile** steuern – ideal für Cronjobs, Bash-Skripte oder Automationen:

* **Kamera schwenken:**
```bash
python3 camera_control.py --cmd left
python3 camera_control.py --cmd preset1
```

* **Nachtsicht einschalten:**
```bash
python3 camera_control.py --cmd ir_on
```

* **Snapshot direkt als Datei abspeichern (ohne Browser):**
```bash
python3 camera_control.py --snapshot /home/pi/haustuer.jpg
```

---

### Alle verfügbaren Befehle (`--cmd`):
`up`, `down`, `left`, `right`, `center`, `preset1`, `preset2`, `preset3`, `preset4`, `ir_on`, `ir_off`, `patrol_h`, `patrol_v`, `stop_patrol`
