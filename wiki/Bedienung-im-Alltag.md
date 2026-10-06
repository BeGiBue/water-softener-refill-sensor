# Bedienung im Alltag

Nach der Einrichtung läuft die Zählung von selbst. Du musst nur eingreifen, wenn **Salz nachgefüllt** wird oder wenn die Rechnung **von der Wirklichkeit abweicht**.

## Salz nachfüllen

Die Integration meldet sich, wenn das Salz nur noch für wenige Regenerationen reicht (Standard: 3). Dann:

1. **Salz in den Behälter füllen.** Notiere dir, wie viel Kilogramm es waren (Sackgewicht).
2. In Home Assistant das Gerät öffnen und bei **„Nachgefüllte Salzmenge“** die Menge in kg eintragen, zum Beispiel `20`.
3. Die Taste **„Salz nachgefüllt“** drücken.

Danach ist die Menge zum Bestand addiert, die Eingabe springt wieder auf 0, und die Meldung verschwindet, sobald der Bestand über der Warnschwelle liegt.

### Wenn nicht der ganze Sack hineinpasst

Das ist bei dieser Anlage der Normalfall: Der Sack (25 kg) passt oft nicht komplett hinein, weil noch Restsalz im Behälter liegt. Das ist kein Problem:

1. Füll so viel ein, wie hineinpasst, und trage diese Menge ein (zum Beispiel 20 kg). Taste drücken.
2. Später, wenn wieder Platz ist, füllst du den Rest nach, trägst wieder die Menge ein (zum Beispiel 5 kg) und drückst die Taste erneut.

Jede Menge wird **addiert**. Mehr als die Behältergröße kann der Bestand nie werden. Ist ein Rest über, wird er einfach abgeschnitten (im Protokoll steht dann ein Hinweis).

Der Zähler **„Regenerationen seit Nachfüllen“** springt erst auf 0, wenn der Behälter nach dem Nachfüllen **voll** ist.

### Wenn der Behälter ganz voll ist

Hast du den Behälter bis oben gefüllt, nimmst du die Taste **„Behälter voll“**. Sie setzt den Bestand auf die Behältergröße und braucht **keine Mengeneingabe**. Das ist der schnellste Weg, wenn du nicht rechnen willst.

### Warum muss man eine Menge angeben?

Damit der Bestand stimmt, auch wenn man in mehreren Schritten nachfüllt, und damit niemand die Warnung „wegklickt“, ohne wirklich Salz nachgefüllt zu haben. Die Taste „Salz nachgefüllt“ tut bei Menge 0 deshalb nichts und zeigt eine Fehlermeldung.

### Die Meldung bleibt, obwohl ich nachgefüllt habe

Dann war die Menge zu klein: Der Restbestand liegt nach dem Nachfüllen immer noch **bei oder unter der Warnschwelle**. Beispiel mit den Standardwerten (1,28 kg je Regeneration, Warnschwelle 3): Bei 1,5 kg Bestand (Restbestand 1) bringt ein Nachfüllen von 3 kg nur 4,5 kg (Restbestand 3). Das ist noch nicht genug, die Meldung bleibt und zeigt den neuen Stand. Mit weiteren 2 kg (6,5 kg, Restbestand 5) verschwindet sie. Prüfe im Zweifel den Sensor **Restbestand Regenerationen**.

## Der Bestand stimmt nicht mehr

Mit der Zeit kann die Rechnung von der Wirklichkeit abweichen (zum Beispiel weil eine Regeneration nicht erkannt wurde). Schau dann in den Behälter und stelle den Bestand ein:

```yaml
action: water_softener_refill_sensor.set_salt_stock
data:
  kg: 12
```

Alternativ in *Entwicklerwerkzeuge → Aktionen* die Aktion **„Salzbestand setzen“** auswählen.

## Eine Regeneration wurde nicht erkannt

Hat die Anlage regeneriert, die Integration aber nicht (zum Beispiel weil der Wasserzähler ausgefallen war), trägst du sie nach:

```yaml
action: water_softener_refill_sensor.add_regeneration
data:
  count: 1
```

Das erhöht beide Zähler, zieht Salz ab und setzt „Letzte Regeneration“ auf **jetzt**. Damit beginnt auch die 7-Tage-Frist neu, und die Meldung „Regeneration überfällig“ verschwindet.

Umgekehrt: Wurde fälschlich eine Regeneration gezählt, stellst du den Salzbestand mit `set_salt_stock` richtig. Den Zähler „Regenerationen seit Nachfüllen“ kannst du mit `set_regenerations_since_refill` einstellen (siehe unten). Der Gesamtzähler lässt sich nicht zurückdrehen.

## Zustand von Hand eintragen

Seit Version 1.2.0 kannst du den Zustand korrigieren oder beim Einrichten mitten in einer Füllung vorgeben. Das geht über zwei Eingabefelder am Gerät („Letzte Regeneration korrigieren“, „Regenerationen seit Nachfüllen korrigieren“) oder über Dienste.

### Letzte Regeneration

```yaml
action: water_softener_refill_sensor.set_last_regeneration
data:
  datetime: "2026-10-04 02:40:00"
```

Setzt nur den Zeitpunkt. Er bestimmt „Nächste Regeneration spätestens“ und „Regeneration überfällig“. Zähler und Salzbestand bleiben unverändert, es wird keine Regeneration gezählt. Eine Angabe ohne Zeitzone gilt als Ortszeit. Ein Zeitpunkt in der Zukunft wird mit einer Fehlermeldung abgelehnt.

### Regenerationen seit Nachfüllen

```yaml
action: water_softener_refill_sensor.set_regenerations_since_refill
data:
  count: 12
```

Setzt die Anzahl der Regenerationen seit dem letzten Füllen bis voll und **berechnet den Salzbestand neu**: Behältergröße − Anzahl × Verbrauch pro Regeneration. Der Gesamtzähler wird bei Bedarf auf mindestens diese Anzahl angehoben. Die Meldung „Salz nachfüllen“ wird sofort neu bewertet.

## Meldungen

| Meldung | Wann | Wie sie verschwindet |
|---|---|---|
| **Salz nachfüllen** | Restbestand ≤ Warnschwelle | Nachfüllen mit Menge bestätigen, sodass der Restbestand wieder über der Schwelle liegt (oder „Behälter voll“) |
| **Regeneration überfällig** | Am 7-Tage-Fälligkeitstag wurde nach der Auswertung keine Regeneration erkannt | Sobald wieder eine Regeneration gezählt wird (automatisch bei der nächsten erkannten oder per `add_regeneration`) |

Die Meldungen erscheinen in der **Glocke** der Seitenleiste. Nach einem Neustart von Home Assistant werden sie bei Bedarf automatisch neu angelegt. Die Sprache folgt der Home-Assistant-Sprache (Deutsch oder Englisch).

## Benachrichtigung aufs Handy

Die Meldung in der Seitenleiste siehst du nur, wenn du Home Assistant öffnest. Für eine Nachricht aufs Handy nimmst du die Binärsensoren als Auslöser:

```yaml
automation:
  - alias: Enthärtung Salz nachfüllen
    triggers:
      - trigger: state
        entity_id: binary_sensor.enthaertungsanlage_salz_nachfullen
        to: "on"
    actions:
      - action: notify.mobile_app_dein_handy
        data:
          title: Salz nachfüllen
          message: "Das Salz der Enthärtungsanlage reicht nur noch für wenige Regenerationen."
```

Entitäts-ID und Notify-Dienst sind Beispiele. Die genauen Entitäts-IDs findest du unter *Einstellungen → Geräte & Dienste → Entitäten*, den Notify-Dienst unter *Entwicklerwerkzeuge → Aktionen*. Das Gleiche geht mit **„Regeneration überfällig“**.

## Dashboard

Eine einfache Karte mit den wichtigsten Werten:

```yaml
type: entities
title: Enthärtungsanlage
entities:
  - entity: sensor.enthaertungsanlage_salzfullstand
  - entity: sensor.enthaertungsanlage_restbestand_regenerationen
  - entity: sensor.enthaertungsanlage_letzte_regeneration
  - entity: sensor.enthaertungsanlage_nachste_regeneration_spatestens
  - entity: number.enthaertungsanlage_nachgefullte_salzmenge
  - entity: button.enthaertungsanlage_salz_nachgefullt
  - entity: button.enthaertungsanlage_behalter_voll
```

Auch hier sind die Entitäts-IDs Beispiele und müssen an deine angepasst werden.

## Anbindung an die Karte „Heizungskeller Schema“

Die Karte [Heizungskeller Schema](https://github.com/BeGiBue/heizungskeller-schema) hat eine Tafel **„Enthärtungsanlage“** mit zwei Zeilen. Im Karteneditor, Bereich *Enthärtungsanlage*, wählst du:

- **Regeneration** → zum Beispiel „Regenerationen gesamt“ oder „Restbestand Regenerationen“,
- **Salz** → „Salzfüllstand“ (in Prozent).

Die Tafel liest nur Werte. Nachfüllen bestätigst du weiterhin über das Gerät der Integration.
