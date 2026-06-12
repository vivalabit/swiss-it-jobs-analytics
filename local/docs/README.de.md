# Swiss IT Jobs Analytics

[English](../../README.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Italiano](README.it.md)

Swiss IT Jobs Analytics ist ein Tool, das Tausende von Stellenanzeigen auf dem Schweizer Arbeitsmarkt analysiert, um die gefragtesten Fähigkeiten, Technologien und Karrierewege zu erkennen. So können Sie besser einschätzen, was Sie heute lernen sollten, um morgen wettbewerbsfähig zu bleiben.

Direkt ansehen - https://vivalabit.github.io/swiss-it-jobs-analytics/

Aktuelle Quellen:

- `LinkedIn`
- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`
- `swissdevjobs.ch`

Der Datensatz wird quellenübergreifend auf Stellenebene dedupliziert.
Wenn dieselbe Stelle auf mehreren Jobbörsen veröffentlicht wird, zählt sie in den öffentlichen Statistiken nur einmal.

Das Projekt befindet sich noch in Arbeit, daher können sich Statistiken und Struktur ändern.

Die öffentliche Website veröffentlicht aggregierte Momentaufnahmen des Schweizer IT-Arbeitsmarkts, die aus verarbeiteten Stellendatensätzen mehrerer Jobbörsen erstellt werden. Sie zeigt übergreifende Signale wie Stellenvolumen, Arbeitgeberaktivität, Nachfrage nach Fähigkeiten, Gehaltsspannen, geografische Konzentration, Senioritätsmix und Verteilung der Arbeitsmodelle.


## Was dieses Projekt abdeckt

Dieses Projekt soll praktische, datenbasierte Fragen zum Arbeitsmarkt beantworten:

- Welche Rollen derzeit am stärksten nachgefragt werden
- Welche Fähigkeiten und Technologien am häufigsten vorkommen
- Welche Kantone und Städte die höchste Konzentration an Stellenanzeigen haben
- Wie sich die Nachfrage über Senioritätsstufen verteilt
- Wie vergleichbare Gehaltsspannen je nach Rollenkategorie variieren
- Welche Fähigkeiten Arbeitgeber tatsächlich am Markt bewerten

<img src="../img/image.png" width="900">

**Die Statistiken decken Stellenanzeigen ab, die ab 2026 veröffentlicht wurden.**


***Personalvermittlungen sind ausgeschlossen.***

## Methodik

Wir sammeln Stellenanzeigen aus mehreren Quellen (LinkedIn, jobs.ch, jobscout24.ch, jobup.ch, swissdevjobs.ch), speichern sie in lokalen Datenbanken für jeden Anbieter, ordnen sie anschließend einem gemeinsamen Schema zu und erzeugen aggregierte Statistiken auf Basis des kombinierten Datensatzes. Während der Konsolidierungsphase verwenden wir eine Deduplizierung auf Grundlage der Stellenidentität innerhalb jeder Quelle, damit doppelte Importe die Statistiken nicht verfälschen.

Danach wird jede Stellenanzeige normalisiert: Unternehmen, Standort, Kanton, Seniorität, Arbeitsmodell und Gehaltsfelder werden standardisiert, während Rollenkategorie, Fähigkeiten, Programmiersprachen, Frameworks/Bibliotheken und weitere analytische Attribute aus Texten und strukturierten Feldern extrahiert werden. Gehälter werden, sofern verfügbar, in ein vergleichbares jährliches Format in CHF umgerechnet, damit Zusammenfassungen und Aufschlüsselungen nach Rolle und Seniorität berechnet werden können.

Anschließend werden Agenturen und Rekrutierungsvermittler aus der Gesamtstichprobe ausgeschlossen. Das ist wichtig: In unseren öffentlichen Statistiken wollen wir gezielt den direkten Arbeitsmarkt abbilden und nicht die Aktivität von Vermittlern, die ähnliche Stellen mehrfach erneut veröffentlichen und so das Bild der Nachfrage verzerren können. Ausnahmen werden auf Basis einer normalisierten Liste bekannter Personalvermittlungs- und Rekrutierungsunternehmen sowie ihrer Aliasnamen vorgenommen.

Stellenanzeigen werden zusätzlich mit KI analysiert: Standardsoftwarefilter erkennen oft nicht alle relevanten Informationen und können wichtige Details übersehen. KI ersetzt diese Filter nicht und erfindet keine Daten, sondern arbeitet ergänzend zu ihnen, um eine tiefere und genauere Analyse zu ermöglichen.

[Technical usage](local/docs/TECHNICAL_USAGE.md)<br>
[Local App](local/docs/LOCAL_APP.md)
