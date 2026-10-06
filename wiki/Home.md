# Water Softener Refill Sensor

Eine Home-Assistant-Integration für **Enthärtungsanlagen mit Salzbehälter**. Sie beantwortet drei Fragen, die die Anlage selbst nicht beantwortet:

1. **Wie oft hat die Anlage regeneriert?**
2. **Wie viel Salz ist noch im Behälter?**
3. **Wann muss ich nachfüllen?**

Dafür braucht sie nur einen **Wasserzähler** in Home Assistant. Die Anlage selbst muss nicht angeschlossen werden. Entwickelt und gedacht ist sie für eine Aqmos R2D2-32, sie passt aber zu jeder Anlage, die nachts regeneriert und dabei Wasser verbraucht.

## In 30 Sekunden

- Die Anlage regeneriert nachts (hier: zwischen 2 und 3 Uhr) und verbraucht dabei rund 52 Liter Wasser.
- Die Integration schaut, **wie viel Wasser in diesem Zeitfenster durch den Zähler lief**. Mehr als 45 Liter? Dann hat die Anlage regeneriert.
- Jede Regeneration verbraucht eine bekannte Menge Salz (hier 1,28 kg). Daraus rechnet die Integration den **Salzbestand**.
- Wird der Vorrat knapp (Standard: reicht nur noch für 3 Regenerationen), erscheint eine **Meldung in Home Assistant**. Sie bleibt, bis du **die nachgefüllte Menge in kg bestätigst**.
- Startest du **mitten in einer Füllung**, trägst du den Zustand von Hand ein: die letzte Regeneration (vom Display der Anlage) und die Regenerationen seit dem Nachfüllen (ab Version 1.2.0).
- Zusätzlich kennt sie die **Hygiene-Regel** der Anlage: Spätestens 7 Tage nach der letzten Regeneration regeneriert sie auch ohne Verbrauch. Bleibt das aus, meldet die Integration „Regeneration überfällig“.

## Wegweiser

| Seite | Wofür |
|---|---|
| [Funktionsweise](Funktionsweise) | Wie die Integration denkt, Schritt für Schritt und mit Zahlenbeispielen |
| [Installation und Einrichtung](Installation-und-Einrichtung) | Installieren, einrichten, Werte für die Aqmos R2D2-32 |
| [Bedienung im Alltag](Bedienung-im-Alltag) | Salz nachfüllen, Bestand korrigieren, Dashboard und Automationen |
| [Entitäten und Dienste](Entitaeten-und-Dienste) | Nachschlagewerk aller Sensoren, Tasten, Dienste und Meldungen |
| [Fehlersuche und Grenzen](Fehlersuche-und-Grenzen) | Wenn etwas nicht stimmt, und was die Integration nicht kann |
| [Technische Dokumentation](Technische-Dokumentation) | Aufbau, Datenfluss, Speicherformat, Randfälle |
| [Entwicklung und Release](Entwicklung-und-Release) | Tests, Arbeitsregeln, Veröffentlichen |

## Stand

- Aktuelle Version: **1.2.0**, Mindestversion Home Assistant **2024.12**.
- Das Änderungsprotokoll steht in der Datei [CHANGELOG.md](https://github.com/BeGiBue/water-softener-refill-sensor/blob/main/CHANGELOG.md).
- **Ehrlicher Hinweis:** Die Berechnung ist ausführlich getestet. Laut Änderungsprotokoll wurden Einrichtung, Optionen, Entitäten, Tasten und Dienste ab Version 1.1.1 mit einem echten Home Assistant (2026.2) geprüft. Wie zuverlässig die Erkennung über den Wasserzähler im Alltag arbeitet, zeigt sich erst über mehrere Nächte. Fehler bitte als [Issue](https://github.com/BeGiBue/water-softener-refill-sensor/issues) melden, am besten mit den Zeilen aus dem Protokoll.

## Verwandt

Die Dashboard-Karte [Heizungskeller Schema](https://github.com/BeGiBue/heizungskeller-schema) hat eine Tafel „Enthärtungsanlage“, die ihre Werte von dieser Integration bekommen kann (siehe [Bedienung im Alltag](Bedienung-im-Alltag#anbindung-an-die-karte-heizungskeller-schema)). Die Integration funktioniert aber auch ganz ohne die Karte.
