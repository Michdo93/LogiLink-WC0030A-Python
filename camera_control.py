import argparse
import io
import sys
import requests
from flask import Flask, Response, render_template_string, send_file, request

# ==================== KONFIGURATION ====================
CAM_IP = "192.168.0.35"
CAM_USER = "admin"
CAM_PASS = "Passwort"
FLASK_PORT = 5000
# =======================================================

BASE_URL = f"http://{CAM_IP}/cgi-bin"

# Zuordnung aller verfügbaren Foscam/LogiLink CGI-Befehle (decoder_control.cgi)
COMMANDS = {
    # 9 Richtungen & Stopp
    "up": 0,
    "up_right": 9,
    "right": 6,
    "down_right": 11,
    "down": 2,
    "down_left": 13,
    "left": 4,
    "up_left": 15,
    "center": 25,
    "stop": 1,

    # Presets Abrufen
    "preset1_get": 31,
    "preset2_get": 33,
    "preset3_get": 35,
    "preset4_get": 37,

    # Presets Festlegen (Speichern)
    "preset1_set": 30,
    "preset2_set": 32,
    "preset3_set": 34,
    "preset4_set": 36,

    # Patrouillen
    "patrol_h_start": 28,
    "patrol_h_stop": 29,
    "patrol_v_start": 26,
    "patrol_v_stop": 27,

    # Relay (Schaltausgang)
    "relay_on": 94,
    "relay_off": 95
}

# Mapping für camera_control.cgi Einstellungen (param-ID)
PARAM_IDS = {
    "speed": 18,       # 1 bis 100 (Default: 50)
    "brightness": 1,  # 0 bis 255 (Default: 123)
    "contrast": 2,    # 0 bis 255 (Default: 147)
    "hue": 3,         # -128 bis 127 (Default: 1)
    "saturation": 4   # 0 bis 200 (Default: 110)
}

def send_cam_command(cmd_key):
    """Sendet ein Steuerungskommando an die IP-Kamera (decoder_control.cgi)."""
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

def set_camera_param(param_name, value):
    """Setzt Bildeinstellungen oder PTZ-Geschwindigkeit (camera_control.cgi)."""
    if param_name not in PARAM_IDS:
        print(f"[FEHLER] Unbekannter Parameter: {param_name}")
        return False

    param_id = PARAM_IDS[param_name]
    url = f"{BASE_URL}/camera_control.cgi"
    params = {
        "param": param_id,
        "value": value,
        "user": CAM_USER,
        "pwd": CAM_PASS
    }
    try:
        res = requests.get(url, params=params, timeout=3)
        print(f"[CAM OK] Param '{param_name}' (ID {param_id}) auf {value} gesetzt.")
        return res.status_code == 200
    except Exception as e:
        print(f"[CAM FEHLER] Parameter-Setting fehlgeschlagen: {e}")
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
    """Liest den MJPEG-Stream der Kamera aus und reicht ihn Frames-weise an den Browser weiter."""
    url = f"{BASE_URL}/videostream.cgi"
    params = {"user": CAM_USER, "pwd": CAM_PASS}
    
    try:
        with requests.get(url, params=params, stream=True, timeout=10) as r:
            if r.status_code != 200:
                print(f"[STREAM FEHLER] Kamera antwortet mit Status code: {r.status_code}")
                return

            bytes_buffer = b''
            for chunk in r.iter_content(chunk_size=1024):
                bytes_buffer += chunk
                
                a = bytes_buffer.find(b'\xff\xd8')
                b = bytes_buffer.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = bytes_buffer[a:b+2]
                    bytes_buffer = bytes_buffer[b+2:]
                    
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
    except Exception as e:
        print(f"[STREAM FEHLER] Verbindung abgebrochen: {e}")

# ==================== FLASK WEB-GUI ====================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LogiLink WC0030A Control Center</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #181818; color: #fff; text-align: center; margin: 0; padding: 20px; }
        .main-wrapper { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; max-width: 1200px; margin: 0 auto; }
        .card { background: #242424; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .stream-card { flex: 1; min-width: 320px; max-width: 680px; }
        .control-card { flex: 1; min-width: 300px; max-width: 450px; text-align: left; }
        
        .stream-box { width: 100%; height: 480px; background: #000; border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
        .stream-box img { width: 100%; height: 100%; object-fit: contain; }
        
        /* 3x3 Steuerkreuz */
        .controls-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 240px; margin: 15px auto; }
        .btn { padding: 12px; font-size: 14px; font-weight: bold; background: #007bff; color: white; border: none; border-radius: 6px; cursor: pointer; transition: 0.2s; text-align: center; }
        .btn:hover { background: #0056b3; }
        .btn-secondary { background: #495057; }
        .btn-secondary:hover { background: #343a40; }
        .btn-success { background: #28a745; }
        .btn-success:hover { background: #218838; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #bd2130; }

        .section-title { font-size: 16px; border-bottom: 1px solid #444; padding-bottom: 5px; margin-top: 15px; margin-bottom: 10px; color: #17a2b8; }
        .btn-group { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
        
        /* Slider Styling */
        .slider-group { margin-bottom: 12px; }
        .slider-group label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
        .slider-group input { width: 100%; }
    </style>
</head>
<body>
    <h2>📷 LogiLink WC0030A Control Center</h2>
    
    <div class="main-wrapper">
        <!-- Live Video Stream Card -->
        <div class="card stream-card">
            <div class="stream-box">
                <img src="/video_feed" alt="Live Stream wird geladen..." />
            </div>
            <div style="margin-top: 15px;">
                <a href="/snapshot" target="_blank" class="btn btn-danger" style="text-decoration: none; display: inline-block;">📸 Schnappschuss (Snapshot)</a>
            </div>
        </div>

        <!-- Kamera Steuerung Card -->
        <div class="card control-card">
            
            <!-- PTZ Steuerkreuz (9 Richtungen) -->
            <div class="section-title">🧭 PTZ Steuerung</div>
            <div class="controls-grid">
                <button class="btn" onclick="sendCmd('up_left')">↖</button>
                <button class="btn" onclick="sendCmd('up')">▲</button>
                <button class="btn" onclick="sendCmd('up_right')">↗</button>
                <button class="btn" onclick="sendCmd('left')">◄</button>
                <button class="btn btn-secondary" onclick="sendCmd('center')">⌂</button>
                <button class="btn" onclick="sendCmd('right')">►</button>
                <button class="btn" onclick="sendCmd('down_left')">↙</button>
                <button class="btn" onclick="sendCmd('down')">▼</button>
                <button class="btn" onclick="sendCmd('down_right')">↘</button>
            </div>

            <!-- Voreinstellungen (Presets) -->
            <div class="section-title">📍 Voreinstellungen (Presets)</div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="sendCmd('preset1_get')">Pos 1</button>
                <button class="btn btn-secondary" onclick="sendCmd('preset2_get')">Pos 2</button>
                <button class="btn btn-secondary" onclick="sendCmd('preset3_get')">Pos 3</button>
                <button class="btn btn-secondary" onclick="sendCmd('preset4_get')">Pos 4</button>
            </div>
            <div class="btn-group">
                <button class="btn btn-danger" style="font-size:11px;" onclick="sendCmd('preset1_set')">Pos 1 Speichern</button>
                <button class="btn btn-danger" style="font-size:11px;" onclick="sendCmd('preset2_set')">Pos 2 Speichern</button>
                <button class="btn btn-danger" style="font-size:11px;" onclick="sendCmd('preset3_set')">Pos 3 Speichern</button>
                <button class="btn btn-danger" style="font-size:11px;" onclick="sendCmd('preset4_set')">Pos 4 Speichern</button>
            </div>

            <!-- Patrouillen & Relay -->
            <div class="section-title">🔄 Patrouille & Schaltausgang</div>
            <div class="btn-group">
                <button class="btn btn-success" onclick="sendCmd('patrol_h_start')">Horiz. Patrouille Start</button>
                <button class="btn btn-secondary" onclick="sendCmd('patrol_h_stop')">Stopp</button>
            </div>
            <div class="btn-group">
                <button class="btn btn-success" onclick="sendCmd('patrol_v_start')">Vertik. Patrouille Start</button>
                <button class="btn btn-secondary" onclick="sendCmd('patrol_v_stop')">Stopp</button>
            </div>
            <div class="btn-group">
                <button class="btn btn-success" onclick="sendCmd('relay_on')">Relay AN</button>
                <button class="btn btn-danger" onclick="sendCmd('relay_off')">Relay AUS</button>
            </div>

            <!-- Schieberegler -->
            <div class="section-title">⚙️ Bild- & Bewegungseinstellungen</div>
            
            <div class="slider-group">
                <label>PTZ Geschwindigkeit: <span id="val_speed">50</span></label>
                <input type="range" min="1" max="100" value="50" onchange="updateParam('speed', this.value)">
            </div>
            <div class="slider-group">
                <label>Helligkeit: <span id="val_brightness">123</span></label>
                <input type="range" min="0" max="255" value="123" onchange="updateParam('brightness', this.value)">
            </div>
            <div class="slider-group">
                <label>Kontrast: <span id="val_contrast">147</span></label>
                <input type="range" min="0" max="255" value="147" onchange="updateParam('contrast', this.value)">
            </div>
            <div class="slider-group">
                <label>Farbton: <span id="val_hue">1</span></label>
                <input type="range" min="-128" max="127" value="1" onchange="updateParam('hue', this.value)">
            </div>
            <div class="slider-group">
                <label>Sättigung: <span id="val_saturation">110</span></label>
                <input type="range" min="0" max="200" value="110" onchange="updateParam('saturation', this.value)">
            </div>

        </div>
    </div>

    <script>
        function sendCmd(cmd) {
            fetch('/api/cmd/' + cmd)
                .then(r => r.json())
                .then(data => console.log('Befehl Status:', data));
        }

        function updateParam(param, value) {
            document.getElementById('val_' + param).innerText = value;
            fetch(`/api/param?name=${param}&value=${value}`)
                .then(r => r.json())
                .then(data => console.log('Parameter Status:', data));
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
    """Streamt das Live-Video über MJPEG."""
    return Response(
        generate_mjpeg_stream(), 
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/snapshot')
def snapshot():
    """Liefert den aktuellen Snapshot als JPG-Datei zurück."""
    img_bytes = get_snapshot_bytes()
    if img_bytes:
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg', as_attachment=True, download_name='snapshot.jpg')
    return "Fehler beim Laden des Snapshots", 500

@app.route('/api/cmd/<cmd_key>')
def api_cmd(cmd_key):
    """REST-Endpunkt für Buttons (decoder_control.cgi)."""
    success = send_cam_command(cmd_key)
    return {"command": cmd_key, "success": success}

@app.route('/api/param')
def api_param():
    """REST-Endpunkt für Schieberegler (camera_control.cgi)."""
    param_name = request.args.get('name')
    value = request.args.get('value')
    if param_name and value:
        success = set_camera_param(param_name, int(value))
        return {"param": param_name, "value": value, "success": success}
    return {"success": False, "error": "Ungültige Parameter"}, 400


# ==================== CLI / MAIN ====================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Steuerung & Web-Server für LogiLink WC0030A IP-Kamera")
    parser.add_argument("--cmd", type=str, help="Führt ein direktes Command im Headless-Modus aus (z.B. up, center, preset1_get, relay_on)")
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

    # Option 3: Web-GUI Server starten
    else:
        print(f"\n==================================================")
        print(f" Starte Kamera Web-GUI & Live-Stream...")
        print(f" Erreichbar unter: http://localhost:{FLASK_PORT}")
        print(f"==================================================\n")
        app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
