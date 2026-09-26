"""Befehlstabellen für decoder_control.cgi (Apexis/Foscam-MJPEG-kompatibel).

Die Codes folgen dem Foscam-MJPEG-CGI-SDK, das Apexis für die H-Serie
übernommen hat. Jede Bewegung läuft so lange, bis ein Stopp-Code kommt
(oder der Endanschlag erreicht ist).

Status der Codes für die WC0030A (APM-H803-MPC):
  * 0-7, 25-29, 30+/31+ (Presets), 94/95: Foscam-Standard, in der Weboberfläche
    der Kamera als Buttons vorhanden (siehe Sprachdatei: Links oben ... Relay aus).
  * 90-93 (Diagonalen): Foscam-Standard. Das bisherige Skript nutzte 9/11/13/15,
    die in keiner bekannten Doku vorkommen. -> mit `wc0030a probe` gegenprüfen.
"""

from __future__ import annotations

# Richtung -> (Start-Code, Stopp-Code)
MOVE = {
    "up": (0, 1),
    "down": (2, 3),
    "left": (4, 5),
    "right": (6, 7),
    "up_left": (90, 1),
    "up_right": (91, 1),
    "down_left": (92, 1),
    "down_right": (93, 1),
}

# Bei Überkopfmontage bzw. gespiegeltem Bild sind die Achsen vertauscht.
INVERT_V = {"up": "down", "down": "up", "up_left": "down_left", "up_right": "down_right",
            "down_left": "up_left", "down_right": "up_right"}
INVERT_H = {"left": "right", "right": "left", "up_left": "up_right", "up_right": "up_left",
            "down_left": "down_right", "down_right": "down_left"}

STOP = 1
CENTER = 25
PATROL_V_START, PATROL_V_STOP = 26, 27
PATROL_H_START, PATROL_H_STOP = 28, 29
IO_ON, IO_OFF = 94, 95

PRESET_MAX = 16  # Protokollgrenze; die Kamera meldet in get_preset_status ihre Anzahl (WC0030A: 9)


def preset_set_code(n: int) -> int:
    """Code zum Speichern der aktuellen Position auf Preset n (1-basiert)."""
    _check_preset(n)
    return 30 + 2 * (n - 1)


def preset_goto_code(n: int) -> int:
    """Code zum Anfahren von Preset n (1-basiert)."""
    _check_preset(n)
    return 31 + 2 * (n - 1)


def _check_preset(n: int) -> None:
    if not 1 <= n <= PRESET_MAX:
        raise ValueError(f"Preset {n} außerhalb 1..{PRESET_MAX}")


# Nur lesende CGIs – werden von status --all und vom Probe-Tool abgefragt.
READ_CGIS = [
    "get_status.cgi",
    "get_real_status.cgi",
    "get_params.cgi",
    "get_camera_vars.cgi",
    "get_preset_status.cgi",
    "get_sdc_status.cgi",
    "get_list_cruise.cgi",
    "get_cruise.cgi",
    "get_motion_schedule.cgi",
    "get_alarm_schedule.cgi",
    "get_extra_server.cgi",
    "get_log_page.cgi",
    "get_wifi_scan_result.cgi",
    "check_user.cgi",
]

# Schreibende CGIs, deren Parameternamen aus dem Dump nicht ablesbar sind.
# Sie sind über Camera.raw() erreichbar; die Namen liefert `wc0030a probe`.
UNVERIFIED_WRITE_CGIS = [
    "set_camera_vars.cgi", "set_lamp.cgi", "set_video.cgi", "set_audio.cgi",
    "set_motion_alarm.cgi", "set_outer_alarm.cgi", "set_cruise.cgi", "control_cruise.cgi",
    "set_datetime.cgi", "set_alias.cgi", "set_sdc_rec.cgi",
]

# Diese CGIs führt das Programm nie automatisch aus.
DANGEROUS_CGIS = {
    "reboot.cgi", "restore_factory.cgi", "format_sdc.cgi", "upgrade_firmware.cgi",
    "upgrade_webui.cgi", "set_mac.cgi", "set_users.cgi", "set_wifi.cgi",
    "set_static_ip.cgi", "set_dhcp_ip.cgi", "backup_params.cgi", "clear_log.cgi",
    "delete_sdcard_file.cgi",
}
