# Entwicklung und Release

## Tests

Nur die Standardbibliothek von Python wird benötigt:

```bash
python3 -m unittest discover -s tests -v
```

Die Anzahl der Tests zeigt die Ausgabe von `unittest`. Seit 1.1.1 gibt es zusätzlich einen Test, der leere Einheiten in den Formularen erkennt.

| Datei | Prüft |
|---|---|
| `tests/test_logic.py` | Die reine Berechnung: Zeitfenster, Erkennung, Bestand, Nachfüllen, Hygieneregel, Speichern und Laden |
| `tests/test_integration_smoke.py` | Den Ablauf der Anbindung mit Attrappen: eine ganze Nacht, Meldungen, Tasten, Dienste, Neustart, Einheiten |
| `tests/ha_stubs.py` | Minimale Attrappen der Home-Assistant-Schnittstellen |

**Wichtig:** Die Attrappen prüfen den eigenen Code, **nicht** die echte Home-Assistant-API. Der Fehler in 1.1.0 („400: Bad Request“ bei der Einrichtung) blieb ihnen verborgen und fiel erst in einer echten Instanz auf. Wer Formulare, Importe, Basisklassen oder Signaturen ändert, sieht in der Dokumentation von Home Assistant nach und prüft die Änderung in einer echten Instanz.

## Arbeitsregeln

1. **Fachlogik** (Zählen, Bestand, Zeitfenster) gehört nach `logic.py` und bekommt Tests in `tests/test_logic.py`.
2. **Nach jeder Änderung** die Tests ausführen.
3. Das **Speicherformat** nicht brechen: neue Felder mit Standardwert (siehe [Technische Dokumentation](Technische-Dokumentation#zustand-und-speicherformat)).
4. **Neue Option:** `const.py` (Schlüssel, Standard), `config_flow.py` (Schema, Prüfung), `manager.py` (`settings_from_entry`), beide Übersetzungen, README.
5. **Neue Entität:** Beschreibung in `sensor.py` (oder eigene Plattform), Name in `de.json` und `en.json`, Eintrag in der Entitätentabelle der README und im Wiki.
6. **Übersetzungen:** `de.json` und `en.json` immer gemeinsam pflegen.
7. **Mindestversion** steht in `hacs.json` (`homeassistant`).
8. **Texte für Nutzer** sind deutsch, die englischen Übersetzungen gleichwertig.

Diese Regeln stehen auch in der Datei `CLAUDE.md` im Repository. Sie ist die Arbeitsanweisung für Claude Code.

## Veröffentlichen

1. Version in `custom_components/water_softener_refill_sensor/manifest.json` erhöhen (Patch für Fehlerbehebungen, Minor für neue Funktionen).
2. In `CHANGELOG.md` oben einen Abschnitt `## X.Y.Z` mit den Änderungen ergänzen. Daraus werden die Release-Notes.
3. README (und dieses Wiki) mit den Änderungen abgleichen.
4. Tests ausführen.
5. Committen und auf `main` pushen.

Den Rest übernimmt der Workflow `release.yml`: Er legt den Tag `vX.Y.Z` und das GitHub-Release an (Notes aus dem Änderungsprotokoll), sobald diese Version auf `main` liegt und noch kein Release dafür existiert. Gibt es das Release schon, werden nur seine Notes aktualisiert.

## Automatische Prüfungen (GitHub Actions)

Der Workflow `validate.yml` läuft bei relevanten Änderungen auf `main` und bei Pull Requests:

| Prüfung | Was sie sicherstellt |
|---|---|
| **Hassfest** | Die Integration erfüllt die Vorgaben von Home Assistant (Manifest, Übersetzungen, Struktur) |
| **HACS** | Die Anforderungen von HACS (zum Beispiel Beschreibung und Themen des Repositorys) sind erfüllt. Die Prüfung der Marken (`brands`) ist ausgeschaltet |
| **Tests** | Die Testsuite läuft unter Python 3.13 |

## Wiki pflegen

Dieses Wiki ist ein eigenes Git-Repository (`water-softener-refill-sensor.wiki.git`). Seiten sind Markdown-Dateien, der Dateiname ist der Seitenname (Bindestriche statt Leerzeichen). Ändert sich das Verhalten, sind diese Seiten mit anzupassen:

| Änderung | Seiten |
|---|---|
| Neue oder geänderte Entität, Taste, Dienst | [Entitäten und Dienste](Entitaeten-und-Dienste), ggf. [Bedienung im Alltag](Bedienung-im-Alltag) |
| Neue Einstellung | [Installation und Einrichtung](Installation-und-Einrichtung) |
| Geänderte Rechenregel | [Funktionsweise](Funktionsweise) und [Technische Dokumentation](Technische-Dokumentation) |
| Neue Version | Versionsangabe auf der Startseite ([Home](Home)) |
