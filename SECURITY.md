# Sicherheitsrichtlinie

## Was als Sicherheitslücke gilt

Diese Anwendung verarbeitet EEG-/EKG-Aufzeichnungen, die personenbezogen sein können. Als
Sicherheitslücke gilt insbesondere:

- ein Weg, wie eine hochgeladene Datei oder Teile davon entgegen der Zusicherung dauerhaft
  auf der Platte, im Protokoll oder über eine ausgehende Verbindung landen
- ein Weg, das Passwort-Gate (`EDF_PASSWORD`) zu umgehen oder Sitzungen anderer Nutzer
  einzusehen
- ein Weg, über eine präparierte EDF-Datei Code auszuführen oder Dateien außerhalb des
  Session-Verzeichnisses zu lesen/schreiben
- eine Schwachstelle in einer eingebundenen Bibliothek, die über diese App erreichbar ist

Eine **fachlich fragwürdige Berechnung** — ein Kennwert, der unplausibel wirkt, eine
Artefakterkennung, die zu viel oder zu wenig markiert — ist ein Qualitätsmangel, kein
Sicherheitsproblem. Dafür bitte ein normales
[Issue](https://github.com/maximilianhabs/edf-analyzer/issues) eröffnen.

## Wie melden

Über die private Sicherheitsmeldung von GitHub:
[Security Advisory eröffnen](https://github.com/maximilianhabs/edf-analyzer/security/advisories/new).
Damit bleibt die Meldung unsichtbar, bis eine Korrektur vorliegt.

Ist dieser Weg nicht erreichbar, ersatzweise über das GitHub-Profil
[@maximilianhabs](https://github.com/maximilianhabs) Kontakt aufnehmen.

**Bitte niemals echte Aufnahmen, Header-Auszüge oder Bildschirmfotos mit Personenbezug einer
Meldung beifügen** — auch nicht, um einen Fund zu belegen. Für EDF-Dateien lässt sich mit dem
Begleit-Werkzeug [edf-anonymizer](https://github.com/maximilianhabs/edf-anonymizer) lokal eine
anonymisierte Fassung erzeugen; meist genügt ohnehin eine Beschreibung oder eine synthetische
Datei (siehe `tests/fixtures/`).

## Was zu erwarten ist

Eine Rückmeldung, ob die Meldung angenommen wird, innerhalb einer Woche. Eine feste Frist für
die Behebung kann nicht zugesagt werden — dies ist ein einzeln betreutes Forschungsprojekt
ohne Sicherheitsteam.

## Umfang

Geprüft und behoben werden Lücken im eigenen Quelltext dieses Repositories. Für Schwachstellen
in einer eingebundenen Bibliothek (Streamlit, MNE, SciPy, pyedflib …) bitte zusätzlich das
jeweilige Projekt benachrichtigen — hier hilft in der Regel eine aktualisierte Version in
`requirements.txt`.

## Betriebshinweis

Die App bringt nur ein einfaches Passwort-Gate mit (`EDF_PASSWORD`, Pflicht-Umgebungsvariable).
Das ist als Zugangsschutz für kleine, vertrauenswürdige Nutzerkreise gedacht, **nicht** als
Mehrbenutzer-Authentifizierung: es gibt keine Benutzerkonten, keine Rollen und keine
Zugriffsprotokollierung. Wer die App öffentlich erreichbar macht und dabei personenbezogene
Aufnahmen verarbeitet, ist selbst für TLS, Netzwerkabsicherung und die datenschutzrechtliche
Bewertung verantwortlich.
