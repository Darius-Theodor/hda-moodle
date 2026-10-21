# Semester <Semester>

Dieser Ordner ist die Semesterzentrale. Der Nutzer kommt, wenn er Zeit hat, und will nur an der
Aufgabe arbeiten. Organisation übernimmt der Agent (Skill `hda-moodle`). Keine Zeitpläne.

## Einstieg (bei „ich hab Zeit“, „was steht an“ oder zu Sitzungsbeginn)

1. `python3 tools/moodle/moodle.py sync` ausführen und Änderungen lesen.
2. Kalender der nächsten 7 Tage prüfen (falls Zugriff).
3. `SEMESTER.md` lesen.
4. Kurze Nachricht: was neu ist, welcher Block jetzt sinnvoll ist, dann anfangen.
5. Am Ende des Blocks `SEMESTER.md` aktualisieren.

## Kurse

| Kürzel | Kurs | Ordner | Moodle-ID | Art / Prüfung |
|---|---|---|---|---|
| <kürzel> | <Kurs> | `<ordner>/` | <id> | <Vorlesung+Praktikum, Klausur …> |

## Moodle

`tools/moodle/moodle.py` (Token im Schlüsselbund `hda-moodle-token`). `sync` = Struktur + Diff,
`sections <kurs> -v` = Überblick mit Modul-IDs, `fetch <kurs> --section N` = gezielt laden.
Manifest unter `<kursordner>/moodle/manifest.json`, Dateien unter `<kursordner>/moodle/files/`.
