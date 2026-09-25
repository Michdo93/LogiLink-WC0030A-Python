import argparse
import io
import sys
import requests
from flask import Flask, Response, render_template_string, send_file

# ==================== KONFIGURATION ====================
CAM_IP = "192.168.0.35"
CAM_USER = "admin"
CAM_PASS = "DEIN_PASSWORT"
FLASK_PORT = 5000
# =======================================================

BASE_URL = f"http://{CAM_IP}"

# Zuordnung aller verfügbaren Foscam/LogiLink CGI-Befehle
COMMANDS = {
    "up": 0,
    "stop_up": 1,
    "down": 2,
    "stop_down": 3,
    "left": 4,
    "stop_left": 5,
    "right": 6,
    "stop_right": 7,
    "center": 25,
    "preset1": 31,
    "preset2": 33,
    "preset3": 35,
    "preset4": 37,
    "ir_on": 95,
    "ir_off": 94,
    "patrol_h": 28,  # Horizontale Patrouille
    "patrol_v": 26,  # Vertikale Patrouille
    "stop_patrol": 29
}

def send_cam_command(cmd_key):
    """Sendet ein Steuerungskommando an die IP-Kamera."""
    if cmd_key not in COMMANDS:
        print(f"[FEHLER] Unbekannter Befehl: {cmd_key}")
        return False
    
    code = COMMANDS[cmd_key]
    url = f"{BASE_URL}/decoder_control.cgi"
    params = {
        "command": code,
        "user": CAM_USER,
        "pwd": CAM_PASS
    }
    try:
        res = requests.get(url, params=params, timeout=3)
        print(f"[CAM OK] Befehl '{cmd_key}' (Code {code}) gesendet. Status: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[CAM FEHLER] Verbindung fehlgeschlagen: {e}")
        return False

def get_snapshot_bytes():
    """Holt ein einzelnes JPG-Bild direkt aus der Kamera."""
    url = f"{BASE_URL}/snapshot.cgi"
    params = {"user": CAM_USER, "pwd": CAM_PASS}
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return res.content
    except Exception as e:
        print(f"[CAM FEHLER] Snapshot fehlgeschlagen: {e}")
    return None

def generate_mjpeg_stream():
    """Liest den MJPEG-Stream der Kamera aus und reicht ihn an den Browser weiter."""
    url = f"{BASE_URL}/videostream.cgi"
    params = {"user": CAM_USER, "pwd": CAM_PASS}
    try:
        # Stream öffnen mit stream=True
        with requests.get(url, params=params, stream=True, timeout=10) as r:
            for chunk in r.iter_content(chunk_size=1024):
                yield chunk
    except Exception as e:
        print(f"[STREAM FEHLER] Stream unterbrochen: {e}")

# ==================== FLASK WEB-GUI ====================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LogiLink WC0030A - Steuerung</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a1a; color: #fff; text-align: center; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #2a2a2a; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .stream-box { width: 100%; max-width: 640px; height: 480px; background: #000; margin: 0 auto 20px auto; border-radius: 8px; overflow: hidden; }
        .stream-box img { width: 100%; height: 100%; object-fit: contain; }
        
        .controls { display: grid; grid-template-columns: repeat(3, 80px); gap: 10px; justify-content: center; margin-bottom: 20px; }
        .btn { padding: 12px; font-size: 16px; font-weight: bold; background: #007bff; color: white; border: none; border-radius: 6px; cursor: pointer; transition: 0.2s; }
        .btn:hover { background: #0056b3; }
        .btn-secondary { background: #6c757d; }
        .btn-secondary:hover { background: #545b62; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #bd2130; }

        .action-bar { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>📷 LogiLink WC0030A Control Center</h2>
        
        <div class="stream-box">
            <img src="/video_feed" alt="Live Stream wird geladen..." />
        </div>

        <!-- Steuerkreuz -->
        <div class="controls">
            <div></div>
            <button class="btn" onclick="sendCmd('up')">▲</button>
            <div></div>
            <button class="btn" onclick="sendCmd('left')">◄</button>
            <button class="btn btn-secondary" onclick="sendCmd('center')">⌂</button>
            <button class="btn" onclick="sendCmd('right')">►</button>
            <div></div>
            <button class="btn" onclick="sendCmd('down')">▼</button>
            <div></div>
        </div>

        <!-- Presets & Funktionen -->
        <div class="action-bar">
            <button class="btn btn-secondary" onclick="sendCmd('preset1')">Position 1</button>
            <button class="btn btn-secondary" onclick="sendCmd('preset2')">Position 2</button>
            <button class="btn btn-secondary" onclick="sendCmd('ir_on')">🌙 Nachtsicht AN</button>
            <button class="btn btn-secondary" onclick="sendCmd('ir_off')">☀️ Nachtsicht AUS</button>
            <a href="/snapshot" target="_blank" class="btn btn-danger">📸 Snapshot herunterladen</a>
        </div>
    </div>

    <script>
        function sendCmd(cmd) {
            fetch('/api/cmd/' + cmd)
                .then(r => r.json())
                .then(data => console.log('Status:', data));
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    """Streamt das Live-Video über MJPEG im Browser."""
    return Response(generate_mjpeg_stream(), mimetype='multipart/x-mixed-replace; boundary=123456789000000000000987654321')

@app.route('/snapshot')
def snapshot():
    """Liefert das aktuelle Einzelbild als JPG-Datei aus."""
    img_bytes = get_snapshot_bytes()
    if img_bytes:
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg', as_attachment=True, download_name='snapshot.jpg')
    return "Fehler beim Laden des Snapshots", 500

@app.route('/api/cmd/<cmd_key>')
def api_cmd(cmd_key):
    """REST-Endpunkt für die Buttons."""
    success = send_cam_command(cmd_key)
    return {"command": cmd_key, "success": success}


# ==================== CLI / MAIN ====================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Steuerung & Web-Server für LogiLink IP-Kamera")
    parser.add_argument("--cmd", type=str, help="Führt ein direktes Command im Headless-Modus aus (z.B. up, down, preset1, ir_on)")
    parser.add_argument("--snapshot", type=str, help="Speichert einen Snapshot direkt in die angegebene Datei (z.B. image.jpg)")
    parser.add_argument("--server", action="store_true", help="Startet die Flask Web-GUI inklusive Live-Stream")

    args = parser.parse_args()

    # Option 1: Einzelner Befehl per CLI
    if args.cmd:
        send_cam_command(args.cmd)
    
    # Option 2: Snapshot per CLI speichern
    elif args.snapshot:
        data = get_snapshot_bytes()
        if data:
            with open(args.snapshot, "wb") as f:
                f.write(data)
            print(f"✅ Snapshot erfolgreich unter '{args.snapshot}' gespeichert!")
        else:
            print("❌ Fehler beim Speichern des Snapshots.")

    # Option 3: Web-GUI Server starten (Standard, falls keine Argumente)
    else:
        print(f"\n==================================================")
        print(f" Starte Kamera Web-GUI & Live-Stream...")
        print(f" Erreichbar unter: http://localhost:{FLASK_PORT}")
        print(f"==================================================\n")
        app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
