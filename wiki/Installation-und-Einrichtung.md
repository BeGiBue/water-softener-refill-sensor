# Installation und Einrichtung

## Was du brauchst

- **Home Assistant 2024.12 oder neuer.**
- **Einen Wasserzähler in Home Assistant**, und zwar einen Sensor mit dem **kumulierten Zählerstand** (er zählt nur aufwärts) in **Litern oder Kubikmetern**. Das ist derselbe Sensortyp, den das Energie-Dashboard für Wasser verwendet.
- **Der Zähler muss die Anlage „sehen“**: Er sitzt im Wasserweg vor oder hinter der Enthärtungsanlage, sodass der Spülverbrauch der Regeneration durch ihn läuft. Ein Zähler, der nur einen anderen Teil des Hauses misst, funktioniert nicht.
- **Der Zähler muss seinen Stand laufend melden**, nicht nur einmal pro Stunde. Sonst landet der gesamte Verbrauch einer Stunde in einem einzigen Wert, und die Erkennung wird ungenau (siehe [Fehlersuche und Grenzen](Fehlersuche-und-Grenzen)).

Die Anlage selbst muss **nicht** mit Home Assistant verbunden sein.

## Installation

### Über HACS (empfohlen)

1. In Home Assistant **HACS** öffnen.
2. Oben rechts Menü (⋮) → **Benutzerdefinierte Repositories**.
3. Als Adresse `https://github.com/BeGiBue/water-softener-refill-sensor` eintragen, Kategorie **Integration** wählen, hinzufügen.
4. „Water Softener Refill Sensor“ in HACS suchen und **Herunterladen**.
5. **Home Assistant neu starten.**

Schneller: Die README im Repository enthält einen Knopf „In HACS öffnen“, der das Repository direkt in deiner Home-Assistant-Instanz öffnet.

### Von Hand

Den Ordner `custom_components/water_softener_refill_sensor` aus dem Repository in das Verzeichnis `config/custom_components/` deiner Home-Assistant-Installation kopieren und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → „Water Softener Refill Sensor“.*

Das Formular fragt Folgendes ab:

| Feld | Bedeutung | Standard | Empfehlung für die Aqmos R2D2-32 |
|---|---|---|---|
| **Name** | Name des Geräts in Home Assistant | Enthärtungsanlage | Enthärtungsanlage |
| **Wasserzähler** | Der Sensor mit dem kumulierten Zählerstand | – | dein Wasserzähler-Sensor |
| **Behältergröße (Salz)** | Wie viele kg Salz passen nominell in den Behälter | 25 kg | 25 kg |
| **Salzverbrauch pro Regeneration** | kg Salz je Regeneration | 1,28 kg | 1,28 kg |
| **Aktueller Salzbestand** | Nur bei der Einrichtung, optional. Leer = Behälter ist voll | leer | siehe unten |
| **Schwellwert Wasserverbrauch** | Ab wie viel Liter im Zeitfenster zählt es als Regeneration (mehr als) | 45 Liter | 45 Liter |
| **Zeitfenster von / bis** | Wann die Anlage regeneriert, nur volle Stunden, Ende nach Beginn | 2 bis 3 Uhr | 2 bis 3 Uhr |
| **Warnung bei Restbestand von** | Bei so vielen verbleibenden Regenerationen kommt die Meldung | 3 | 3 |

### Was ist der „aktuelle Salzbestand“?

Wenn du die Integration einrichtest, während der Behälter **nicht voll** ist, trägst du hier ein, wie viel Salz **gerade** drin ist (in kg). Ist der Behälter voll oder frisch befüllt, lässt du das Feld leer.

Schätzen reicht für den Anfang. Du kannst den Bestand später jederzeit mit dem Dienst `set_salt_stock` nachkorrigieren (siehe [Bedienung im Alltag](Bedienung-im-Alltag)).

### Einrichten mitten in einer Füllung (ab Version 1.2.0)

Richtest du die Integration ein, während die Anlage schon einige Regenerationen hinter sich hat, trägst du den Zustand nach der Einrichtung am Gerät von Hand ein:

1. **Letzte Regeneration korrigieren**: Datum und Uhrzeit der letzten Regeneration, zum Beispiel vom Display der Anlage. Damit stimmt die 7-Tage-Frist („Nächste Regeneration spätestens“).
2. **Regenerationen seit Nachfüllen korrigieren**: Anzahl der Regenerationen seit der Behälter zuletzt voll war. Der Salzbestand wird daraus berechnet (Behältergröße − Anzahl × Verbrauch). Das ist genauer als eine Schätzung in kg, wenn du die Anzahl vom Display ablesen kannst.

Beide Eingaben sind im Gerät als Konfiguration eingeordnet. Es gibt sie auch als Dienste (`set_last_regeneration`, `set_regenerations_since_refill`).

### Warum 45 Liter?

Die Anlage verbraucht pro Regeneration meist **52–53 Liter**. Der Schwellwert liegt bewusst darunter, aber über dem, was nachts normalerweise sonst läuft (etwa eine Toilettenspülung). So bleibt der Abstand in beide Richtungen. Wenn du merkst, dass deine Anlage weniger verbraucht, senke den Wert. Wenn nachts regelmäßig andere Verbraucher laufen, hebe ihn an oder verschiebe das Zeitfenster.

## Prüfen, ob es läuft

Nach der Einrichtung findest du ein neues **Gerät** mit dem eingestellten Namen und seinen Entitäten (Liste: [Entitäten und Dienste](Entitaeten-und-Dienste)).

Sofort sichtbar sollten sein:

- **Salzbestand** und **Salzfüllstand** entsprechend deinen Angaben,
- **Restbestand Regenerationen** (bei 25 kg und 1,28 kg: 19),
- „Regenerationen gesamt“ steht auf 0.

Den echten Test macht die erste Nacht. Am Morgen sollte **Verbrauch im Zeitfenster** einen Wert zeigen (bei einer Regeneration um die 52 Liter) und **Regenerationen gesamt** um 1 gestiegen sein.

Wer nicht warten will, kann den Ablauf mit dem Dienst `add_regeneration` durchspielen (Regeneration von Hand eintragen) und danach mit `set_salt_stock` den Bestand wieder richtigstellen. Das testet allerdings nur die Salzrechnung und die Meldungen, nicht die Erkennung über den Wasserzähler.

## Einstellungen später ändern

*Einstellungen → Geräte & Dienste → Water Softener Refill Sensor → Konfigurieren.*

Änderbar sind der Wasserzähler, die Behältergröße, der Salzverbrauch, der Schwellwert, das Zeitfenster und die Warnschwelle. Nach dem Speichern lädt die Integration sich selbst neu. **Zähler und Bestand bleiben dabei erhalten.**

Nicht änderbar sind der Name (am Gerät umbenennen) und der anfängliche Bestand (dafür gibt es `set_salt_stock` oder die Korrektur-Eingaben am Gerät).

Wird die **Behältergröße verkleinert**, wird der Bestand auf die neue Größe begrenzt.

## Entfernen

Beim Löschen des Eintrags werden die gespeicherten Daten (Zähler, Bestand) und beide Meldungen entfernt. Eine spätere Neueinrichtung beginnt wieder bei null.
