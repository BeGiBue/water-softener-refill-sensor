# CLAUDE.md – Arbeitsanweisungen für dieses Repository

## Projekt

Home-Assistant-Integration „Water Softener Refill Sensor“, Domain **`water_softener_refill_sensor`**, Repository `BeGiBue/water-softener-refill-sensor` (HACS-Kategorie *Integration*): zählt die Regenerationen einer
Enthärtungsanlage über den Wasserzähler und rechnet den Salzbestand mit. Zugehörige Dashboard-Karte:
`BeGiBue/heizungskeller-schema` (Tafel „Enthärtungsanlage“, Felder `softener_regeneration` und `softener_salt`).

## Aufbau (`custom_components/water_softener_refill_sensor/`)

| Datei | Zweck |
|---|---|
| `logic.py` | **Reine Logik ohne Home-Assistant-Importe**: Zeitfenster, Erkennung, Salzbestand, (De-)Serialisierung |
| `manager.py` | Verbindet die Logik mit Home Assistant: Zähler beobachten, Zeitplan, Speicher, Meldung, Koordinator |
| `__init__.py` | Setup/Unload/Remove des Eintrags, Dienste (`refill`, `set_salt_stock`, `add_regeneration`, `set_last_regeneration`, `set_regenerations_since_refill`) |
| `config_flow.py` | Einrichtung und Optionen (Selektoren, Validierung) |
| `entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`, `number.py`, `datetime.py` | Entitäten (`number.py`: Eingabe der Nachfüllmenge für die Taste und Korrektur „Regenerationen seit Nachfüllen“; `datetime.py`: Korrektur „Letzte Regeneration“; Koordinator-Entitäten, `has_entity_name`, Namen über `translation_key`) |
| `services.yaml`, `translations/{de,en}.json` | Dienstbeschreibung, Texte; **de und en immer gemeinsam pflegen** |
| `manifest.json` | Metadaten; `version` ist die Versionsnummer des Releases |

## Regeln

1. Fachlogik (Zählen, Bestand, Zeitfenster) gehört nach `logic.py` und bekommt Tests in `tests/test_logic.py`.
2. Nach jeder Änderung `python3 -m unittest discover -s tests -v` ausführen. `tests/test_integration_smoke.py` nutzt
   Attrappen der HA-Schnittstellen (`tests/ha_stubs.py`): sie prüfen den eigenen Ablauf, **nicht** die echte HA-API.
   **Maßgeblich** für die Anbindung sind die Tests mit echtem Home Assistant in `tests_ha/`
   (`pip install -r requirements_test.txt`, dann `python3 -m pytest`; die CI prüft 2024.12 und 2026.2). Bei Änderungen
   an HA-Schnittstellen (Imports, Basisklassen, Signaturen, Formulare) dort einen Test ergänzen. Die Attrappen liefern nur
   Module aus `ALLOWED_MODULES` in `tests/ha_stubs.py`; ein neues HA-Modul dort bewusst ergänzen.
3. Das Speicherformat (`Store`, Version 1) nicht brechen: neue Felder in `State`/`from_dict` mit Standardwert ergänzen.
4. Neue Option = `const.py` (Schlüssel und Standard), `config_flow.py` (Schema, Validierung), `manager.py`
   (`settings_from_entry`), beide Übersetzungen und `README.md`.
5. Neue Entität = Beschreibung in `sensor.py` (oder eigene Plattform), Übersetzungsname in `de.json` und `en.json`,
   Eintrag in der Tabelle der `README.md`.
6. Mindestversion Home Assistant steht in `hacs.json` (`homeassistant`); `config_entry`-Zugriff im Optionsfluss setzt
   2024.11+ voraus.
7. Texte für den Nutzer sind deutsch; Übersetzungen en gleichwertig halten. Fehler der Dienste als
   `ServiceValidationError` mit `translation_key` (Texte unter `exceptions`, Hilfsfunktion `service_error` in
   `manager.py`); `tests/test_translations.py` prüft, dass de/en deckungsgleich und alle Schlüssel vorhanden sind.
8. Zeitfenster (in `logic.py` festgehalten, bitte nicht „reparieren“):
   - Erfasst wird vom Fensterbeginn bis **Fensterende + 1 Minute** (= Auswertezeitpunkt), damit verspätet gemeldete
     Zählerwerte noch zählen. Ein Wert genau zum Auswertezeitpunkt zählt nicht mehr.
   - Fenster in echter Zeit: Beginn = eingestellte Stunde in Ortszeit (doppelte Zeit: die erste; fehlende Zeit: nach
     vorn verschoben), Länge = Ende − Beginn in echten Stunden, alle Vergleiche in UTC. Tatsache: Die Anlage stellt
     ihre Uhr nicht selbst um, der Nutzer stellt sie nach der Umstellungsnacht von Hand um; in dieser Nacht läuft sie
     noch auf der alten Zeit, und genau dazu passt das berechnete Fenster (März 03–04 MESZ, Oktober erste 02-Uhr-Stunde).
     Der Manager plant die Auswertung mit `async_track_point_in_utc_time`.
   - Einheiten des Wasserzählers rechnet nur der Manager um (`VolumeConverter`); `logic.py` bleibt ohne HA-Importe.

## Veröffentlichen

Version in `manifest.json` erhöhen, Abschnitt `## X.Y.Z` in `CHANGELOG.md` ergänzen, README abgleichen, Tests
ausführen, committen und auf `main` pushen. Der Workflow `.github/workflows/release.yml` legt dann Tag `vX.Y.Z` und
GitHub-Release (Notes aus `CHANGELOG.md`) automatisch an (siehe `.claude/commands/release.md`).
