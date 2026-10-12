# Senior Data Analyst — Aufgabe

## Ziel

Wir möchten dein Verständnis von SQL, dbt und Datenmodellierungsprinzipien bewerten —
sowie deine Fähigkeit, mit „schmutzigen" realen Daten zu arbeiten, technische
Entscheidungen unter Unsicherheit zu treffen und aus Daten geschäftliche
Schlussfolgerungen abzuleiten.

Uns interessiert nicht nur, ob du das angeforderte Modell gebaut hast, sondern auch,
**welche Entscheidungen du unterwegs getroffen und wie du sie begründet hast**. Ein
Teil der Vorgaben ist hier bewusst dir überlassen — das ist Teil der Aufgabe.

---

## Kontext

Das Unternehmen liefert medizinische Produkte im Abonnement aus (mehrere Marken,
Markt: Deutschland). Im CRM wird der Kundenpfad festgehalten: Anfrage (Lead) →
Konversion in eine Opportunity → Patienten-Abonnement → regelmäßige Lieferungen.

---

## Datenzugriff und Einrichtung der Umgebung

Die Daten werden als lokale Datei `interview_assignment.duckdb` (DuckDB) im Schema
`assignment` bereitgestellt. Der Aufgabe liegt ein dbt-Starterprojekt bei — mit bereits
konfiguriertem Profil, deklarierten `sources` und einem Beispiel-(Test-)Modell. Es dient
dazu, die Umgebung schnell hochzufahren und zu prüfen, dass alles läuft, um anschließend
deine eigenen Modelle darauf aufzubauen.

Schritte zum Start:

1. Entpacke das Starterprojekt aus der ZIP-Datei, die du per E-Mail erhalten hast.
2. Lege die Datei `interview_assignment.duckdb` in das Projektverzeichnis (Pfad steht in `profiles.yml`).
3. Erstelle eine virtuelle Python-Umgebung (empfohlen).
4. Installiere `dbt-core` und `dbt-duckdb` via `pip` (falls noch nicht vorhanden):
   `pip install dbt-core dbt-duckdb`.
5. Prüfe die Verbindung: `dbt debug`.
6. Führe das Beispielmodell und den Test aus: `dbt run` und `dbt test`. Wenn im Ziel-
   schema die Ergebnistabelle des Beispielmodells erscheint und der Test besteht, ist
   die Umgebung korrekt eingerichtet und du kannst mit der Aufgabe beginnen.

---

## Verfügbare Tabellen

Im Glossar sind die wichtigsten Felder aufgeführt; die Tabellen enthalten weitere
Spalten — untersuche das Schema selbst, nicht alle nützlichen Felder sind unten genannt.

| Tabelle | Beschreibung | Wichtige Felder |
|---|---|---|
| `LEAD` | Leads (Anfragen) | `ID`, `CREATED_DATE`, `LAST_MODIFIED_DATE`, `STATUS`, `IS_CONVERTED`, `CONVERTED_OPPORTUNITY_ID`, `CONVERTED_ACCOUNT_ID`, `LEAD_SOURCE`, `BRAND__C`, `UTM_SOURCE__C`, `UTM_MEDIUM__C`, `UTM_CAMPAIGN__C`, `IS_DELETED` |
| `OPPORTUNITY` | Opportunities (Lead-Konversion) | `ID`, `CREATED_DATE`, `LAST_STAGE_CHANGE_DATE`, `STAGE_NAME`, `LEAD__C`, `ACCOUNT_ID`, `IS_WON`, `IS_CLOSED`, `BRAND__C`, `IS_DELETED` |
| `SUBSCRIPTION__C` | Patienten-Abonnements | `ID`, `CREATED_DATE`, `LAST_MODIFIED_DATE`, `START_DATE__C`, `END_DATE__C`, `STATUS__C`, `LEAD__C`, `BRAND__C`, `CANCELLATION_REASON__C`, `IS_DELETED` |
| `DELIVERY__C` | Lieferungen (Fakten) | `ID`, `CREATED_DATE`, `SUBSCRIPTION__C`, `STATUS__C`, `BRAND__C`, `IS_DELETED` |
| `ACCOUNT` | Patienten-Accounts | `ID`, `CREATED_DATE`, `NAME`, `BRAND__C`, `IS_DELETED` |

Die Beziehungen zwischen den Entitäten ermittelst du selbst, indem du die Daten untersuchst.

---

## Aufgabe 1: Reporting-Modell `rep_conversion_funnel_monthly`

Monatlicher Konversionstrichter vom Anlegen des Leads bis zur ersten Lieferung.

### Granularität

Der Trichter wird **kohortenbasiert** aufgebaut: Ein Lead wird durch alle Stufen
verfolgt und dem **Monat seiner Erstellung** (`LEAD.CREATED_DATE`) zugeordnet. Das
Erreichen der Stufen 4–6 (die auf anderen Entitäten leben) bezieht sich also auf den
Erstellungsmonat des ursprünglichen Leads, nicht auf das Datum von
Opportunity/Abonnement/Lieferung.

### Trichterstufen

| Stufe | Name | Logik (angewendet auf den Lead der Kohorte) |
|---|---|---|
| 1 | Lead Created | Lead in diesem Monat erstellt |
| 2 | Lead Qualified | `STATUS = 'Qualified'` |
| 3 | Lead Converted | `IS_CONVERTED = true` |
| 4 | Opportunity Won | der Lead hat eine verknüpfte Opportunity mit `STAGE_NAME = 'Closed Won'` |
| 5 | Subscription Active | der Lead hat ein Abonnement mit `STATUS__C = 'Active'` |
| 6 | First Delivery | zu diesem Abonnement existiert mindestens eine Lieferung |

### Entscheidungen, die dir überlassen bleiben

In den Daten treten **stufenübergreifende Inkonsistenzen** auf: Ein Lead kann die
Bedingung von Stufe N erfüllen, ohne Stufe N-1 zu erfüllen. Wie du den Trichter
interpretierst, ist deine technische Entscheidung:

- strenge Sequenz (jede Stufe ist Teilmenge der vorherigen) oder
- unabhängige Zählung jeder Stufe nach ihrer eigenen Bedingung.

Es gibt keine eindeutig „richtige" Variante. Wähle einen Ansatz, **beschreibe seine
Auswirkungen auf die Metrik** (Monotonie, Wertebereich der Konversion, Menge der
herausgefilterten Datensätze) und begründe die Wahl im README.

### Zielschema des Ergebnisses

| Spalte | Typ | Beschreibung |
|---|---|---|
| `month` | date | Erstellungsmonat des Leads (Monatsanfang) |
| `kpi_name` | string | Name der Stufe (wie in der Tabelle oben) |
| `funnel_step` | int | Nummer der Stufe 1–6 |
| `count` | int | Anzahl der Leads der Kohorte, die die Stufe erreicht haben |
| `conversion_from_previous_pct` | numeric | `count / count(vorherige Stufe) * 100`; `NULL` für Stufe 1 |

Zeilengranularität: eine Zeile pro (`month`, `funnel_step`). Beispiel (Zahlen illustrativ):

```
month       | kpi_name        | funnel_step | count | conversion_from_previous_pct
2024-03-01  | Lead Created    | 1           | 180   | NULL
2024-03-01  | Lead Qualified  | 2           | 126   | 70.0
2024-03-01  | Lead Converted  | 3           | 80    | 63.5
...
```

### Betrieb des Modells

Beschreibe im README kurz, wie dieses Modell in der Produktion leben würde: wie du es
inkrementell aktualisieren würdest, was bei spät eintreffenden Daten (late-arriving) und
bei Reaktivierungen von Abonnements passiert, und wie idempotent das Ergebnis bei einem
täglichen Neuberechnen ist.

---

## Aufgabe 2: Ergebnis-Bericht für das Management

Neben dem Modell möchten wir sehen, wie du Ergebnisse aufbereitest und kommunizierst.
Erstelle einen kurzen Bericht — zum Beispiel als Foliensatz/Präsentation oder als
kompaktes Dokument —, den du uns im Gespräch vorstellst, so wie du ihn dem Management
präsentieren würdest.

Wichtig: Das Management interessiert sich nicht dafür, wie du die Lösung technisch gebaut
hast, sondern dafür, was du aus den Daten verstanden hast und was das fürs Geschäft
bedeutet. Stell dir ein nicht-technisches Publikum vor — klare Kernaussagen,
verständliche Visualisierungen und konkrete Empfehlungen zählen hier mehr als jede
technische Erklärung.

Was einen überzeugenden Bericht ausmacht und welche Erkenntnisse aus den Daten es wert
sind, gezeigt zu werden, überlassen wir dir.

---

## Technische Anforderungen

1. Baue das bereitgestellte dbt-Starterprojekt aus (Adapter `dbt-duckdb`); das finale
   Ergebnis veröffentlichst du in einem **öffentlichen GitHub-Repository** und schickst den Link.
2. Deklarierte `sources` für das Schema `assignment` (teilweise im Starterprojekt vorhanden — ergänze sie).
3. Als Ergebnis das Reporting-Modell `rep_conversion_funnel_monthly`. Die Gliederung des
   Projekts in Modelle und Schichten entscheidest du selbst — die Struktur und ihre
   Begründung sind Teil der Bewertung.
4. Tests (`dbt run` und `dbt test` müssen durchlaufen): Eindeutigkeit/Not-NULL von
   Schlüsseln, `relationships`, `accepted_values` sowie mindestens ein sinnvoller Test
   auf dem finalen Modell `rep_conversion_funnel_monthly`, der sich aus deinen
   Entscheidungen zur Trichter-Semantik ergibt.
5. Ein funktionierendes `README` (siehe unten).

---

## Was ins README gehört

- Welche Tabellen verwendet wurden und warum; wie die Beziehungen zwischen den Entitäten definiert sind.
- Wie jede Trichterstufe definiert ist und wie du die stufenübergreifenden Inkonsistenzen
  behandelt hast (mit Begründung des gewählten Ansatzes).
- Welche Datenqualitätsprobleme gefunden und wie sie gelöst wurden (mit Mengenangabe).
- Betrieb des Modells: Inkrementalität, late-arriving data, Reaktivierungen, Idempotenz.
- Annahmen und Kompromisse, die du bewusst getroffen hast.

---

## Abgabe

Veröffentliche dein Projekt in einem öffentlichen GitHub-Repository und schicke uns den
Link — zusammen mit deinem Bericht aus Aufgabe 2 (im Repository beigelegt oder separat).
