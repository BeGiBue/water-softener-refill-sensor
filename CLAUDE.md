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
| `__init__.py` | Setup/Unload/Remove des Eintrags, Dienste (`refill`, `set_salt_stock`, `add_regeneration`) |
| `config_flow.py` | Einrichtung und Optionen (Selektoren, Validierung) |
| `entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`, `number.py` | Entitäten (`number.py`: Eingabe der Nachfüllmenge für die Taste; Koordinator-Entitäten, `has_entity_name`, Namen über `translation_key`) |
| `services.yaml`, `translations/{de,en}.json` | Dienstbeschreibung, Texte; **de und en immer gemeinsam pflegen** |
| `manifest.json` | Metadaten; `version` ist die Versionsnummer des Releases |

## Regeln

1. Fachlogik (Zählen, Bestand, Zeitfenster) gehört nach `logic.py` und bekommt Tests in `tests/test_logic.py`.
2. Nach jeder Änderung `python3 -m unittest discover -s tests -v` ausführen. `tests/test_integration_smoke.py` nutzt
   Attrappen der HA-Schnittstellen (`tests/ha_stubs.py`): sie prüfen den eigenen Ablauf, **nicht** die echte HA-API.
   Bei Änderungen an HA-Schnittstellen (Imports, Basisklassen, Signaturen) deshalb in der Dokumentation von Home
   Assistant nachsehen und dem Nutzer sagen, dass ein Test in einer echten Instanz nötig ist.
3. Das Speicherformat (`Store`, Version 1) nicht brechen: neue Felder in `State`/`from_dict` mit Standardwert ergänzen.
4. Neue Option = `const.py` (Schlüssel und Standard), `config_flow.py` (Schema, Validierung), `manager.py`
   (`settings_from_entry`), beide Übersetzungen und `README.md`.
5. Neue Entität = Beschreibung in `sensor.py` (oder eigene Plattform), Übersetzungsname in `de.json` und `en.json`,
   Eintrag in der Tabelle der `README.md`.
6. Mindestversion Home Assistant steht in `hacs.json` (`homeassistant`); `config_entry`-Zugriff im Optionsfluss setzt
   2024.11+ voraus.
7. Texte für den Nutzer sind deutsch; Übersetzungen en gleichwertig halten.

## Veröffentlichen

Version in `manifest.json` erhöhen, Abschnitt `## X.Y.Z` in `CHANGELOG.md` ergänzen, README abgleichen, Tests
ausführen, committen und auf `main` pushen. Der Workflow `.github/workflows/release.yml` legt dann Tag `vX.Y.Z` und
GitHub-Release (Notes aus `CHANGELOG.md`) automatisch an (siehe `.claude/commands/release.md`).
