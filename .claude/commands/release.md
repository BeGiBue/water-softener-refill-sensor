Bereite eine neue Version vor und veröffentliche sie.

1. Lies `CLAUDE.md` und prüfe, ob `README.md` (Funktionen, Entitäten, Dienste, Einstellungen) zu den Änderungen passt.
2. Erhöhe `version` in `custom_components/water_softener_refill_sensor/manifest.json` (Patch für Fehlerbehebungen, Minor für neue
   Funktionen). Gewünschte Nummer vom Nutzer: $ARGUMENTS
3. Führe `python3 -m unittest discover -s tests -v` aus. Bei Fehlern nicht fortfahren.
4. Ergänze in `CHANGELOG.md` oben einen Abschnitt `## X.Y.Z` mit den Änderungen (daraus werden die Release-Notes).
5. Committe mit einer aussagekräftigen deutschen Nachricht und pushe auf `main`. Der Workflow
   `.github/workflows/release.yml` legt dann automatisch Tag `vX.Y.Z` und das GitHub-Release an.
