"""
seed_initiatives_sesto.py — 4 iniziative di esempio per Sesto S.G. (italiano).

Uso:
    python seed_initiatives_sesto.py
    python seed_initiatives_sesto.py --force
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = "site_sesto.db"
SITE_ID = "sesto"


def _ts(date: str, time: str = "08:00:00") -> str:
    return f"{date} {time}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Migra al schema attuale (status, colonne mancanti, FK rotta su _ini_old)."""
    ddl_ini = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='improvement_initiatives'"
    ).fetchone()[0]
    ddl_docs = (conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='initiative_documents'"
    ).fetchone() or ("",))[0]

    needs_migration = "'planned'" in ddl_ini or '"_ini_old"' in ddl_docs

    if not needs_migration:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(improvement_initiatives)")}
        for col_sql in [
            "ALTER TABLE improvement_initiatives ADD COLUMN category TEXT NOT NULL DEFAULT 'Quality'",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted_at TEXT",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted_by TEXT",
            "ALTER TABLE improvement_initiatives ADD COLUMN deletion_reason TEXT",
        ]:
            col_name = col_sql.split("ADD COLUMN ")[1].split()[0]
            if col_name not in cols:
                conn.execute(col_sql)
    else:
        conn.execute("PRAGMA foreign_keys = OFF")
        ini_rows = conn.execute("SELECT * FROM improvement_initiatives").fetchall()
        ini_cols = [r[1] for r in conn.execute("PRAGMA table_info(improvement_initiatives)")]
        doc_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='initiative_documents'"
        ).fetchone()
        doc_rows = []
        if doc_table:
            doc_rows = conn.execute("SELECT * FROM initiative_documents").fetchall()

        conn.execute("DROP TABLE IF EXISTS initiative_documents")
        conn.execute("DROP TABLE IF EXISTS initiative_audit_log")
        conn.execute("DROP TABLE IF EXISTS _ini_old")
        conn.execute("DROP TABLE IF EXISTS improvement_initiatives")
        conn.commit()

        conn.execute("""
            CREATE TABLE improvement_initiatives (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id           TEXT NOT NULL,
                line_number       INTEGER CHECK(line_number BETWEEN 1 AND 20),
                title             TEXT NOT NULL,
                description       TEXT NOT NULL,
                methodology       TEXT NOT NULL DEFAULT 'Kaizen'
                                  CHECK(methodology IN ('A3','Kaizen','DMAIC','5Why','other')),
                status            TEXT NOT NULL DEFAULT 'No iniciado'
                                  CHECK(status IN ('No iniciado','En progreso','Terminado','Cancelado')),
                category          TEXT NOT NULL DEFAULT 'Quality'
                                  CHECK(category IN ('Safety','Quality','Delivery','Cost','People')),
                owner             TEXT NOT NULL,
                start_date        TEXT NOT NULL,
                target_date       TEXT NOT NULL,
                completion_date   TEXT,
                expected_benefit  TEXT,
                actual_benefit    TEXT,
                linked_problem_id INTEGER REFERENCES top_problems(id) ON DELETE SET NULL,
                deleted           INTEGER NOT NULL DEFAULT 0,
                deleted_at        TEXT,
                deleted_by        TEXT,
                deletion_reason   TEXT
            )
        """)
        status_map = {"planned": "No iniciado", "in_progress": "En progreso",
                      "completed": "Terminado", "on_hold": "Cancelado"}
        for row in ini_rows:
            d = dict(zip(ini_cols, row))
            d["status"] = status_map.get(d.get("status", ""), d.get("status", "No iniciado"))
            for k, v in [("category", "Quality"), ("deleted", 0), ("deleted_at", None),
                         ("deleted_by", None), ("deletion_reason", None)]:
                d.setdefault(k, v)
            conn.execute(
                """INSERT INTO improvement_initiatives
                   (id,site_id,line_number,title,description,methodology,status,category,
                    owner,start_date,target_date,completion_date,expected_benefit,
                    actual_benefit,linked_problem_id,deleted,deleted_at,deleted_by,deletion_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d["id"], d["site_id"], d.get("line_number"), d["title"], d["description"],
                 d["methodology"], d["status"], d["category"], d["owner"], d["start_date"],
                 d["target_date"], d.get("completion_date"), d.get("expected_benefit"),
                 d.get("actual_benefit"), d.get("linked_problem_id"),
                 d["deleted"], d["deleted_at"], d["deleted_by"], d["deletion_reason"]),
            )
        conn.execute("""
            CREATE TABLE initiative_documents (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
                document_type TEXT NOT NULL DEFAULT 'A3'
                              CHECK(document_type IN ('A3','project_charter','report','SOP_update')),
                title         TEXT NOT NULL,
                content_html  TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                author        TEXT NOT NULL
            )
        """)
        if doc_rows:
            conn.executemany("INSERT INTO initiative_documents VALUES (?,?,?,?,?,?,?)", doc_rows)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_site   ON improvement_initiatives(site_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_status ON improvement_initiatives(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_init_docs_init     ON initiative_documents(initiative_id)")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        print("[ok] improvement_initiatives migrato al nuovo schema")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS initiative_documents (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
            document_type TEXT NOT NULL DEFAULT 'A3'
                          CHECK(document_type IN ('A3','project_charter','report','SOP_update')),
            title         TEXT NOT NULL,
            content_html  TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            author        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_init_docs_init ON initiative_documents(initiative_id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS initiative_audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
            field_changed TEXT NOT NULL,
            old_value     TEXT,
            new_value     TEXT,
            changed_by    TEXT NOT NULL,
            changed_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _audit(conn, initiative_id: int, entries: list[tuple]) -> None:
    for field, old_v, new_v, who, ts in entries:
        conn.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id,field_changed,old_value,new_value,changed_by,changed_at)
               VALUES (?,?,?,?,?,?)""",
            (initiative_id, field, old_v, new_v, who, ts),
        )


def run(force: bool = False) -> None:
    with sqlite3.connect(DB_PATH) as _mig:
        _migrate_schema(_mig)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    if force:
        for title in [
            "Risoluzione vibrazioni incajonatrice L2",
            "Riduzione scarti flaconi orali L2",
            "Implementazione manutenzione autonoma L1",
            "Miglioramento OEE linea buste L3",
        ]:
            conn.execute(
                "DELETE FROM improvement_initiatives WHERE site_id=? AND title=?",
                (SITE_ID, title),
            )
        conn.commit()

    # ── 1. Terminado — A3 — Risoluzione vibrazioni incajonatrice L2 ───────────
    # Cuscinetti usurati nel gruppo di trasmissione principale causavano
    # vibrazioni a 18 Hz → fermate non pianificate e micro-difetti di confezionamento.
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,completion_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 2,
            "Risoluzione vibrazioni incajonatrice L2",
            "Progetto A3 per eliminare le vibrazioni anomale dell'incajonatrice sulla linea 2 "
            "(flaconi orali). Vibrazione misurata a 18 Hz nel gruppo di trasmissione principale, "
            "con frequenza di 2,8 fermate non pianificate/settimana e durata media 22 min/evento. "
            "Impatto: OEE L2 −2,1 pp, rischio di difetti di confezionamento (scatole non "
            "chiuse correttamente, 0,4% dei lotti). Causa radice identificata: cuscinetti "
            "usurati nel gruppo di trasmissione, assenza di monitoraggio vibrazioni in continuo.",
            "A3", "Terminado", "Cost",
            "Francesco Romano",
            "2025-12-01", "2026-04-30", "2026-03-18",
            "Eliminare le fermate per vibrazione (da 2,8/sett a ≤0,3/sett); "
            "OEE L2 +2,1 pp; eliminare i difetti di confezionamento correlati",
            "Fermate per vibrazione: 2,8/sett → 0,2/sett (−93%). "
            "Vibrazione residua: <1,5 Hz (spettro normale). OEE L2 +2,0 pp. "
            "Difetti confezionamento correlati: 0 da febbraio 2026. "
            "Sistema IoT monitoraggio vibrazioni installato su 3 punti critici.",
        ),
    )
    ini1_id = cur.lastrowid

    _audit(conn, ini1_id, [
        ("status", None,          "No iniciado",  "Francesco Romano", _ts("2025-11-20")),
        ("title",  None,          "Risoluzione vibrazioni incajonatrice L2",
                                                  "Francesco Romano", _ts("2025-11-20")),
        ("status", "No iniciado", "En progreso",  "Francesco Romano", _ts("2025-12-01")),
        ("status_comment", None,
         "Fase diagnosi avviata. Vibrazione confermata a 18 Hz tramite analisi spettrale. "
         "Cuscinetti gruppo trasmissione principale identificati come causa primaria: "
         "usura visibile, gioco assiale 0,8 mm (limite: 0,3 mm). "
         "Sostituzione pianificata per la prossima fermata programmata (gennaio 2026).",
         "Francesco Romano", _ts("2025-12-01")),
        ("status", "En progreso", "Terminado",    "Chiara Ricci",     _ts("2026-03-18")),
        ("status_comment", None,
         "Cuscinetti sostituiti (gennaio 2026). Monitoraggio IoT installato su 3 punti. "
         "Suivi 6 settimane: vibrazione <1,5 Hz, 0,2 fermate/settimana. "
         "Nessun difetto confezionamento correlato da febbraio 2026. Chiusura A3 approvata.",
         "Chiara Ricci", _ts("2026-03-18")),
    ])

    # Documento A3 — iniziativa 1
    a3_html = """<article class="a3-document">
<h2>A3: Risoluzione vibrazioni incajonatrice L2 — Sesto S.G.</h2>
<p><strong>Autore:</strong> Francesco Romano &nbsp;|&nbsp; <strong>Linea:</strong> L2 Flaconi orali &nbsp;|&nbsp;
   <strong>Inizio:</strong> 2025-12-01 &nbsp;|&nbsp; <strong>Chiusura:</strong> 2026-03-18</p>
<hr>

<section><h3>1. Background / Contesto</h3>
<p>L'incajonatrice della linea 2 (flaconi orali) di Sesto S.G. presenta vibrazioni anomale
a <strong>18 Hz</strong> nel gruppo di trasmissione principale. Con una frequenza di
2,8 fermate non pianificate/settimana e una durata media di 22 min/evento, questo problema
causa una perdita di OEE stimata in <strong>−2,1 pp</strong> e genera difetti di confezionamento
(scatole non chiuse correttamente) sullo 0,4% dei lotti prodotti.</p>
</section>

<section><h3>2. Condizione Attuale (baseline)</h3>
<ul>
  <li>Frequenza fermate per vibrazione: <strong>2,8/settimana</strong> su L2</li>
  <li>Durata media per evento: 22 min (ispezione + riallineamento + riavvio)</li>
  <li>Produzione persa: ~62 min/settimana (~1.240 unità a velocità nominale)</li>
  <li>Difetti confezionamento correlati: 0,4% dei lotti (scatole non chiuse)</li>
  <li>Impatto OEE L2: −2,1 pp</li>
  <li>Vibrazione misurata: 18 Hz (picco spettrale) — valore normale: &lt;3 Hz</li>
</ul>
</section>

<section><h3>3. Obiettivo</h3>
<p>Eliminare le vibrazioni anomale e ridurre le fermate correlate da 2,8/settimana a
<strong>≤0,3/settimana</strong> entro il 30 aprile 2026. Recuperare ≥55 min/settimana
di produzione e portare l'OEE L2 a +2,1 pp.</p>
</section>

<section><h3>4. Analisi delle Cause Radice — Diagramma Ishikawa</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
PROBLEMA: Vibrazioni anomale incajonatrice L2 (18 Hz)

MACCHINA:
  → Cuscinetti gruppo trasmissione principale usurati
    Gioco assiale: 0,8 mm (limite accettabile: 0,3 mm)
    Vita attesa secondo fornitore: 18.000 h — effettiva: ~11.000 h
    ROOT CAUSE 1: Cuscinetti usurati per cicli termici accelerati (T° zona 45°C)

METODO:
  → Intervallo sostituzione preventiva (18 mesi) non aggiornato dopo aumento produzione 2023
    Nessun monitoraggio vibrazioni in continuo — rilevazione solo su guasto
    ROOT CAUSE 2: Piano manutenzione preventiva obsoleto rispetto ai volumi attuali

MISURA:
  → Nessun sensore vibrazioni installato — diagnosi solo su sintomo (rumore/fermate)
    ROOT CAUSE 3: Assenza di sistema di monitoraggio predittivo
</pre>
</section>

<section><h3>5. Contromisure</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Azione</th><th>Responsabile</th><th>Data</th><th>Stato</th></tr>
<tr><td style="padding:0.4rem">Sostituzione cuscinetti gruppo trasmissione (fermata programmata)</td>
    <td>Francesco Romano</td><td>2026-01-15</td><td>✅ Fatto</td></tr>
<tr><td style="padding:0.4rem">Installare sensori IoT vibrazioni su 3 punti critici (allarme >5 Hz)</td>
    <td>Francesco Romano</td><td>2026-02-10</td><td>✅ Fatto</td></tr>
<tr><td style="padding:0.4rem">Ridurre intervallo sostituzione preventiva da 18 a 10 mesi</td>
    <td>Francesco Romano</td><td>2026-01-20</td><td>✅ Fatto</td></tr>
<tr><td style="padding:0.4rem">Aggiornare piano manutenzione preventiva (versione 2026)</td>
    <td>Chiara Ricci</td><td>2026-02-28</td><td>✅ Fatto</td></tr>
<tr><td style="padding:0.4rem">Monitoraggio 6 settimane — conferma risultati</td>
    <td>Francesco Romano</td><td>2026-03-18</td><td>✅ Fatto</td></tr>
</table>
</section>

<section><h3>6. Piano di Implementazione</h3>
<ul>
  <li><strong>1–20 dic 2025:</strong> Diagnosi, analisi spettrale, identificazione cuscinetti da sostituire</li>
  <li><strong>15 gen 2026:</strong> Sostituzione cuscinetti in fermata programmata (2 h pianificate)</li>
  <li><strong>16 gen – 10 feb 2026:</strong> Installazione sensori IoT, aggiornamento piano manutenzione</li>
  <li><strong>11 feb – 18 mar 2026:</strong> Monitoraggio continuo 6 settimane, verifica risultati</li>
</ul>
</section>

<section><h3>7. Indicatori di Controllo (KPI)</h3>
<ul>
  <li>Fermate per vibrazione/settimana L2 (obiettivo ≤0,3 → risultato: 0,2)</li>
  <li>Livello di vibrazione in continuo (allarme IoT se >5 Hz → nessun allarme da gen 2026)</li>
  <li>Difetti confezionamento correlati (obiettivo 0 → risultato: 0 da feb 2026)</li>
  <li>OEE L2 (contributo atteso +2,1 pp → risultato: +2,0 pp)</li>
</ul>
</section>

<section><h3>8. Risultati</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">
✅ <strong>Progetto chiuso il 18 marzo 2026. Obiettivo raggiunto.</strong></p>
<ul>
  <li>Fermate per vibrazione: 2,8/sett → <strong>0,2/sett</strong> (−93%)</li>
  <li>Vibrazione residua: <strong>&lt;1,5 Hz</strong> (spettro normale)</li>
  <li>Produzione recuperata: <strong>~60 min/settimana</strong> (~1.200 unità)</li>
  <li>OEE L2: <strong>+2,0 pp</strong></li>
  <li>Difetti confezionamento correlati: <strong>0</strong> da febbraio 2026</li>
  <li>Sistema IoT vibrazioni operativo — 3 sensori attivi, allarme configurato a 5 Hz</li>
</ul>
</section>
</article>"""

    conn.execute(
        """INSERT INTO initiative_documents
           (initiative_id,document_type,title,content_html,author)
           VALUES (?,?,?,?,?)""",
        (ini1_id, "A3",
         "A3: Risoluzione vibrazioni incajonatrice L2 — Sesto S.G.",
         a3_html, "Francesco Romano"),
    )

    # ── 2. En progreso — DMAIC — Riduzione scarti flaconi orali L2 ────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 2,
            "Riduzione scarti flaconi orali L2",
            "Progetto DMAIC per ridurre il tasso di scarto sui flaconi orali della linea 2. "
            "Tasso attuale: 1,8% (obiettivo: ≤0,5%). Le principali categorie di scarto sono: "
            "peso fuori tolleranza ±2% (61%), difetti di tappatura (24%), etichetta non conforme (15%). "
            "La causa sospettata per la categoria peso è la deriva termica del sensore bilancia "
            "dopo 4 ore di funzionamento — stesso meccanismo identificato su L1 nel progetto "
            "precedente. La DMAIC è stata aperta dopo la chiusura del progetto vibrazioni "
            "incajonatrice per ottimizzare l'utilizzo delle risorse qualità.",
            "DMAIC", "En progreso", "Quality",
            "Laura Colombo",
            "2026-03-24", "2026-09-30",
            "Ridurre tasso di scarto L2 da 1,8% a ≤0,5%; "
            "risparmio stimato ≥10.800 unità/mese; riduzione costo non qualità di ≥€13.000/mese",
            None,
        ),
    )
    ini2_id = cur.lastrowid

    _audit(conn, ini2_id, [
        ("status", None,          "No iniciado",  "Laura Colombo",    _ts("2026-03-10")),
        ("title",  None,          "Riduzione scarti flaconi orali L2",
                                                  "Laura Colombo",    _ts("2026-03-10")),
        ("status", "No iniciado", "En progreso",  "Laura Colombo",    _ts("2026-03-24")),
        ("status_comment", None,
         "Fase Define completata. Baseline confermata: 1,8% scarto L2 (media 12 settimane). "
         "Stratificazione difetti: peso ±2% = 61%, tappatura = 24%, etichetta = 15%. "
         "Fase Measure avviata: raccolta dati 100% ispezione per 4 settimane.",
         "Laura Colombo", _ts("2026-03-24")),
        ("description", None,
         "Aggiornamento fase Analyze (maggio 2026): deriva sensore bilancia confermata "
         "(+0,7 g/h a T° >22°C). Correlazione con tasso scarto peso r=0,91. "
         "Ricalibrazione ogni 2h implementata come contromisura provvisoria: "
         "scarto peso ridotto da 1,1% a 0,6%. Contromisura definitiva (bilancia termocompensata) "
         "in fase di valutazione acquisti.",
         "Laura Colombo", _ts("2026-05-05", "15:00:00")),
    ])

    # ── 3. No iniciado — TPM — Implementazione manutenzione autonoma L1 ───────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 1,
            "Implementazione manutenzione autonoma L1",
            "Programma TPM di Manutenzione Autonoma (AM) per la linea 1 (compresse). "
            "L'obiettivo è trasferire agli operatori le attività di manutenzione di base — "
            "ispezione giornaliera, pulizia, lubrificazione e piccole regolazioni — "
            "riducendo la dipendenza dal team manutenzione per interventi di primo livello. "
            "Il programma segue la metodologia AM in 7 fasi (JIPM). "
            "Il sito benchmark di riferimento è Seishin (OEE 90%, AM completato nel 2024). "
            "Il responsabile manutenzione Francesco Romano ha partecipato alla visita "
            "Seishin organizzata da Fegersheim a marzo 2026 e porterà il know-how acquisito. "
            "Avvio previsto giugno 2026 dopo conclusione formazione DMAIC scarti L2.",
            "other", "No iniciado", "People",
            "Francesco Romano",
            "2026-06-01", "2026-12-18",
            "Ridurre fermate non pianificate L1 del 30% (da ~35 min/turno a ≤25 min/turno); "
            "punteggio AM operatori da 1,0 a ≥3,0/5; liberare 6 h/mese del team manutenzione",
        ),
    )
    ini3_id = cur.lastrowid

    _audit(conn, ini3_id, [
        ("status", None, "No iniciado", "Francesco Romano",  _ts("2026-05-04")),
        ("title",  None, "Implementazione manutenzione autonoma L1",
                                        "Francesco Romano",  _ts("2026-05-04")),
        ("description", None,
         "Perimetro confermato dopo allineamento con Chiara Ricci: pilota su L1, "
         "poi estensione a L2 e L3 in base ai risultati. "
         "Assessment iniziale competenze AM operatori L1 pianificato per fine maggio 2026. "
         "Standard Seishin ricevuti (14 check-list AM) — adattamento al contesto GMP europeo "
         "in corso con Laura Colombo.",
         "Francesco Romano", _ts("2026-05-06", "10:30:00")),
    ])

    # ── 4. Cancelado — Miglioramento OEE linea buste L3 ──────────────────────
    # Iniziativa assorbita nel progetto più ampio di automazione L3
    # approvato dal board nel marzo 2026 (investimento €2,1M).
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 3,
            "Miglioramento OEE linea buste L3",
            "Progetto Kaizen per migliorare l'OEE della linea 3 (bustine monodose) "
            "attualmente al 78%, il valore più basso dei tre linee del sito. "
            "Le principali perdite identificate erano: micro-fermate alimentatore bustine "
            "(38% delle perdite), changeover lento (27%) e scarti per sigillatura non conforme (20%). "
            "L'iniziativa è stata cancellata perché assorbita nel progetto più ampio di "
            "automazione della linea 3 (progetto AUTO-L3-2026), approvato dal board di "
            "Lilly Manufacturing nel marzo 2026 con un investimento di €2,1M. "
            "Il nuovo impianto automatizzato affronterà strutturalmente tutte le perdite "
            "identificate, rendendo inutile un intervento Kaizen sull'equipaggiamento attuale.",
            "Kaizen", "Cancelado", "Delivery",
            "Marco Rossi",
            "2026-01-15", "2026-06-30",
            "Migliorare OEE L3 da 78% a ≥83%; ridurre micro-fermate da 15/turno a ≤5/turno; "
            "ridurre tempo changeover da 52 min a ≤38 min",
        ),
    )
    ini4_id = cur.lastrowid

    _audit(conn, ini4_id, [
        ("status", None,          "No iniciado",  "Marco Rossi",      _ts("2026-01-08")),
        ("title",  None,          "Miglioramento OEE linea buste L3",
                                                  "Marco Rossi",      _ts("2026-01-08")),
        ("status", "No iniciado", "En progreso",  "Marco Rossi",      _ts("2026-01-15")),
        ("status_comment", None,
         "Fase diagnosi avviata su L3. OEE baseline confermato: 78% (media 10 settimane). "
         "Pareto perdite: micro-fermate alimentatore 38%, changeover 27%, scarti sigillatura 20%. "
         "Analisi video changeover in corso (4 registrazioni pianificate).",
         "Marco Rossi", _ts("2026-01-15")),
        ("status", "En progreso", "Cancelado",    "Chiara Ricci",     _ts("2026-04-03")),
        ("status_comment", None,
         "Iniziativa cancellata e assorbita nel progetto AUTO-L3-2026 (automazione completa L3), "
         "approvato dal board Lilly Manufacturing il 18 marzo 2026 (investimento €2,1M, "
         "delivery prevista Q1 2027). Il nuovo impianto risolverà strutturalmente tutte le "
         "perdite identificate in questa iniziativa. Le analisi Kaizen già prodotte "
         "(Pareto, video changeover) sono state consegnate al team progetto AUTO-L3-2026 "
         "come input per la specifica tecnica. Risorse OpEx ridispiegate su DMAIC scarti L2.",
         "Chiara Ricci", _ts("2026-04-03")),
    ])

    conn.commit()
    conn.close()

    print(f"[ok] Iniziative inserite in {DB_PATH}:")
    print(f"  #{ini1_id:3d} Terminado   — Risoluzione vibrazioni incajonatrice L2")
    print(f"  #{ini2_id:3d} En progreso — Riduzione scarti flaconi orali L2")
    print(f"  #{ini3_id:3d} No iniciado — Implementazione manutenzione autonoma L1")
    print(f"  #{ini4_id:3d} Cancelado   — Miglioramento OEE linea buste L3")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
