# hda-moodle

Agent-Skill für Studierende der Hochschule Darmstadt: Moodle (lernen.h-da.de) über die
REST-API lesen, Änderungen erkennen, Material gezielt laden und das Semester organisieren.
Kein Browser-Scraping, Zugangsdaten nur einmal im Terminal, danach läuft alles über ein Token
im macOS-Schlüsselbund.

## Installation

```
npx skills add Darius-Theodor/hda-moodle
```

Alternativ für Claude Code von Hand: den Ordner `skills/hda-moodle` nach `~/.claude/skills/` kopieren.

## Benutzung

Im Uni-Ordner den Agenten starten und `/hda-moodle` aufrufen (oder „Moodle einrichten“ sagen).
Beim ersten Mal richtet der Skill alles ein; der einzige manuelle Schritt ist ein
`python3 tools/moodle/moodle.py login` im Terminal. Danach bei jedem Aufruf: was ist neu, was
ist als Nächstes sinnvoll, los.

Details und Hintergrund: `skills/hda-moodle/HINTERGRUND.md`.

## Lizenz

MIT
