// openHAB 5, JavaScript Scripting (automation/js/wc0030a.js)
// Beispiele – die Kamera-Logik selbst steckt in der MQTT-Bridge,
// Regeln verknüpfen nur Ereignisse im Haus mit Kamera-Befehlen.

// Bewegung erkannt -> Zeitstempel loggen (Snapshot macht die Bridge selbst,
// wenn mqtt.snapshot_on_motion=true)
rules.JSRule({
  name: "WC0030A: Bewegung",
  triggers: [triggers.ItemStateChangeTrigger("Cam_Motion", "CLOSED", "OPEN")],
  execute: () => {
    console.info("WC0030A: Bewegung erkannt");
  }
});

// Nach Feierabend Position 2 (z. B. Blick auf den Laboreingang), morgens zurück auf 1
rules.JSRule({
  name: "WC0030A: Position nach Uhrzeit",
  triggers: [
    triggers.GenericCronTrigger("0 0 18 ? * MON-FRI"),
    triggers.GenericCronTrigger("0 0 7 ? * MON-FRI")
  ],
  execute: () => {
    const evening = time.ZonedDateTime.now().hour() >= 12;
    items.Cam_Preset.sendCommand(evening ? 2 : 1);
  }
});
