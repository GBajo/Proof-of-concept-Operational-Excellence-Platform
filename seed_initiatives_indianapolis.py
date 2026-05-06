"""
seed_initiatives_indianapolis.py — 4 sample initiatives for Indianapolis (English).

Usage:
    python seed_initiatives_indianapolis.py
    python seed_initiatives_indianapolis.py --force   # deletes these 4 first
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = "site_indianapolis.db"
SITE_ID = "indianapolis"


def _ts(date: str, time: str = "08:00:00") -> str:
    return f"{date} {time}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Migrate improvement_initiatives + dependent tables to current schema.
    Handles: old status values, missing columns, missing audit_log table,
    and the SQLite FK-rename side-effect on initiative_documents.
    """
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

        status_map = {
            "planned":     "No iniciado",
            "in_progress": "En progreso",
            "completed":   "Terminado",
            "on_hold":     "Cancelado",
        }
        for row in ini_rows:
            d = dict(zip(ini_cols, row))
            d["status"] = status_map.get(d.get("status", ""), d.get("status", "No iniciado"))
            d.setdefault("category", "Quality")
            d.setdefault("deleted", 0)
            d.setdefault("deleted_at", None)
            d.setdefault("deleted_by", None)
            d.setdefault("deletion_reason", None)
            conn.execute(
                """INSERT INTO improvement_initiatives
                   (id, site_id, line_number, title, description, methodology,
                    status, category, owner, start_date, target_date,
                    completion_date, expected_benefit, actual_benefit,
                    linked_problem_id, deleted, deleted_at, deleted_by, deletion_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d["id"], d["site_id"], d.get("line_number"), d["title"],
                    d["description"], d["methodology"], d["status"], d["category"],
                    d["owner"], d["start_date"], d["target_date"],
                    d.get("completion_date"), d.get("expected_benefit"),
                    d.get("actual_benefit"), d.get("linked_problem_id"),
                    d["deleted"], d["deleted_at"], d["deleted_by"], d["deletion_reason"],
                ),
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
            conn.executemany(
                "INSERT INTO initiative_documents VALUES (?,?,?,?,?,?,?)",
                doc_rows,
            )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_site   ON improvement_initiatives(site_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_status ON improvement_initiatives(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_init_docs_init     ON initiative_documents(initiative_id)")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        print("[ok] improvement_initiatives migrated to new schema")

    # Always ensure dependent tables exist
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
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
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
        titles = [
            "Changeover time standardization",
            "Serialization error reduction Line 3",
            "Autonomous maintenance program Line 1",
            "Reject rate reduction autoinjectors",
        ]
        for title in titles:
            conn.execute(
                "DELETE FROM improvement_initiatives WHERE site_id=? AND title=?",
                (SITE_ID, title),
            )
        conn.commit()

    # ── 1. Terminado — Kaizen — Changeover standardization (network best practice) ──
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date, completion_date,
            expected_benefit, actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "Changeover time standardization",
            "SMED Kaizen project to reduce and standardize format changeover time across "
            "all 3 Indianapolis lines. Average changeover was 72 min (range 55–90 min), "
            "making it the single largest OEE loss driver on site. Indianapolis established "
            "as global network benchmark (45 min avg). Methodology documented as transferable "
            "best practice — Alcobendas deployment started Q1 2026.",
            "Kaizen", "Terminado", "Delivery",
            "Jennifer Taylor",
            "2025-06-01", "2025-12-31", "2025-11-20",
            "Reduce avg changeover from 72 min to <50 min across all 3 lines; "
            "establish transferable network best practice; recover >3 h/week per line",
            "Avg changeover: 72 min → 45 min (−38%). Variability: 55–90 min → 38–55 min. "
            "Hours recovered: 210 h/year (3 lines). OEE +4.1 pp. "
            "SOP v2.3 adopted as network standard — Alcobendas deployment started Q1 2026.",
        ),
    )
    ini1_id = cur.lastrowid

    _audit(conn, ini1_id, [
        ("status", None, "No iniciado",  "Jennifer Taylor", _ts("2025-05-25")),
        ("title",  None, "Changeover time standardization", "Jennifer Taylor", _ts("2025-05-25")),
        ("status", "No iniciado", "En progreso", "Jennifer Taylor", _ts("2025-06-01")),
        ("status_comment", None,
         "SMED analysis kicked off. Video recordings of 12 changeovers scheduled across all "
         "3 lines and 3 shifts. Waste identification workshop booked for June 20.",
         "Jennifer Taylor", _ts("2025-06-01")),
        ("status", "En progreso", "Terminado", "Jennifer Taylor", _ts("2025-11-20")),
        ("status_comment", None,
         "All 3 lines certified on SOP v2.3. Avg changeover confirmed at 45 min over 6-week "
         "monitoring period. Network knowledge-transfer package sent to Alcobendas. "
         "Closing A3 approved by site director.",
         "Jennifer Taylor", _ts("2025-11-20")),
    ])

    # A3 document — initiative 1
    a3_html = """<article class="a3-document">
<h2>Kaizen A3: Changeover Time Standardization — Indianapolis (Global Best Practice)</h2>
<p><strong>Author:</strong> Jennifer Taylor &nbsp;|&nbsp; <strong>Site:</strong> Indianapolis &nbsp;|&nbsp; <strong>Start:</strong> 2025-06-01 &nbsp;|&nbsp; <strong>Closed:</strong> 2025-11-20</p>
<hr>

<section><h3>1. Background</h3>
<p>Format changeover was the single largest OEE loss driver on the Indianapolis site in 2024–2025,
contributing approximately <strong>5.2% annual OEE loss</strong>. With an average changeover time of
72 minutes (range: 55–90 min) across 3 lines and ~3.5 changeovers/week/line, the site was losing
roughly 252 minutes of production per line per week. A SMED Kaizen project was launched with the
dual objective of reducing changeover time and establishing Indianapolis as the global network
knowledge-transfer site.</p>
</section>

<section><h3>2. Current Condition (Baseline)</h3>
<ul>
  <li>Average changeover: <strong>72 min</strong> (range: 55–90 min, all 3 lines)</li>
  <li>OEE loss from changeovers: ~5.2% annually</li>
  <li>~3.5 changeovers/week/line → ~252 min/week lost per line</li>
  <li>Internal vs. external activity split: 68% internal (machine stopped), 32% external</li>
  <li>No standardized kit — each operator follows own sequence (+25 min avg parts retrieval)</li>
  <li>No visual management for changeover progress tracking</li>
</ul>
</section>

<section><h3>3. Goal</h3>
<p>Reduce average changeover from 72 min to <strong>&lt;50 min</strong> with ≤8 min variability
across all shifts and operators by November 30, 2025. Document the methodology as a transferable
best practice for the global network.</p>
</section>

<section><h3>4. Root Cause Analysis</h3>
<ul>
  <li>68% of changeover is internal — 45% of it is convertible to external pre-staging</li>
  <li>No pre-staged kits → operators source parts during changeover (+25 min avg)</li>
  <li>No standardized sequence → high variability between operators and shifts</li>
  <li>Format-specific tooling stored in central warehouse, not at line (&gt;12 min retrieval)</li>
  <li>No countdown timer or visual progress tracking at changeover stations</li>
</ul>
</section>

<section><h3>5. Countermeasures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Owner</th><th>Date</th><th>Status</th></tr>
<tr><td style="padding:0.4rem">Video analysis of 12 changeovers — waste mapping (3 lines × 3 shifts)</td><td>Jennifer Taylor</td><td>2025-07-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Design color-coded changeover kits per format (14 formats)</td><td>Steven Anderson</td><td>2025-08-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Convert internal→external activities (pre-staging protocol)</td><td>Jennifer Taylor</td><td>2025-09-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install dedicated kit trolley at each line position</td><td>Steven Anderson</td><td>2025-09-30</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Develop SOP v2.3 with timed sequence and visual aids</td><td>Karen Martinez</td><td>2025-10-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install digital countdown timer display at each station</td><td>Steven Anderson</td><td>2025-10-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Certify all 9 line operators on SOP v2.3 (OJT sign-off)</td><td>Jennifer Taylor</td><td>2025-11-20</td><td>✅ Done</td></tr>
</table>
</section>

<section><h3>6. Implementation Plan</h3>
<ul>
  <li><strong>Jun–Jul 2025:</strong> SMED analysis, video waste mapping, activity classification</li>
  <li><strong>Aug–Sep 2025:</strong> Kit design &amp; fabrication, pre-staging conversion trials</li>
  <li><strong>Oct 2025:</strong> SOP v2.3 drafting, timer installation, pilot runs per line</li>
  <li><strong>Nov 2025:</strong> Full rollout all 3 lines, operator certification, 6-week monitoring</li>
  <li><strong>Dec 2025+:</strong> Network knowledge transfer — Alcobendas first (Q1 2026)</li>
</ul>
</section>

<section><h3>7. Follow-up KPIs</h3>
<ul>
  <li>Avg changeover time per line per week (target &lt;50 min → achieved: 45 min)</li>
  <li>Changeover time std deviation (target ≤8 min → achieved: ±5 min)</li>
  <li>OEE improvement attributed to changeover (target +2 pp → achieved: +4.1 pp)</li>
  <li>Number of network sites deploying SOP v2.3</li>
</ul>
</section>

<section><h3>8. Results — Global Best Practice</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">
✅ <strong>Project closed November 20, 2025 — Established as Global Network Benchmark.</strong></p>
<ul>
  <li>Average changeover: 72 min → <strong>45 min</strong> (−38%; target was &lt;50 min)</li>
  <li>Variability: 55–90 min → <strong>38–55 min</strong> (std dev: ±5 min)</li>
  <li>Annual production hours recovered: <strong>210 h/year across 3 lines</strong></li>
  <li>OEE improvement: <strong>+4.1 pp</strong> (target: +2 pp)</li>
  <li>SOP v2.3 adopted as global network standard</li>
  <li>Alcobendas benchmark visit completed February 2026; deployment in progress</li>
</ul>
</section>
</article>"""

    conn.execute(
        """INSERT INTO initiative_documents
           (initiative_id, document_type, title, content_html, author)
           VALUES (?,?,?,?,?)""",
        (ini1_id, "A3", "Kaizen A3: Changeover Time Standardization — Indianapolis", a3_html, "Jennifer Taylor"),
    )

    # ── 2. En progreso — DMAIC — Serialization error reduction Line 3 ─────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit, actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 3,
            "Serialization error reduction Line 3",
            "DMAIC project to identify and permanently eliminate the root cause of intermittent "
            "2D camera read errors in the Track & Trace serialization module on Line 3 (vials). "
            "Errors occur 3–4 times per 12-hour shift, averaging 16 min per stop (cleaning, "
            "restart, and GxP revalidation sequence). Pattern analysis shows clustering in "
            "hours 4–6 of the shift. Cross-site: Alcobendas reported a similar issue on the "
            "same camera model — root cause comparison underway.",
            "DMAIC", "En progreso", "Quality",
            "Karen Martinez",
            "2026-01-20", "2026-07-31",
            "Reduce L3 serialization stops from ~3.8/week to ≤0.3/week; "
            "recover ≥55 min/week of lost production; OEE L3 +1.3 pp",
            None,
        ),
    )
    ini2_id = cur.lastrowid

    _audit(conn, ini2_id, [
        ("status", None, "No iniciado",  "Karen Martinez",  _ts("2026-01-10")),
        ("title",  None, "Serialization error reduction Line 3", "Karen Martinez", _ts("2026-01-10")),
        ("status", "No iniciado", "En progreso", "Karen Martinez", _ts("2026-01-20")),
        ("status_comment", None,
         "DMAIC Define phase complete. Baseline confirmed: 3.8 stops/week avg L3, "
         "16 min per event. Pattern: 80% of failures occur 4–6 h into shift. "
         "Measure phase started — data loggers installed on serialization module.",
         "Karen Martinez", _ts("2026-01-20")),
        ("description", None,
         "Analyze phase update (Apr 2026): adhesive aerosol from labeling station "
         "confirmed as primary root cause — same mechanism as Alcobendas L1. "
         "Interim fix (lens cleaning every 4 h) reduced stops to 1.6/week. "
         "Permanent fix: protective air curtain — procurement in progress.",
         "Karen Martinez", _ts("2026-04-15", "14:00:00")),
    ])

    # ── 3. No iniciado — TPM — Autonomous maintenance Line 1 ──────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 1,
            "Autonomous maintenance program Line 1",
            "TPM Autonomous Maintenance (AM) program for Line 1 (autoinjectors). "
            "The goal is to transfer basic maintenance tasks — daily inspection, cleaning, "
            "lubrication, and minor adjustments — from the maintenance team to line operators. "
            "The program follows the 7-step AM methodology: initial cleaning, contamination "
            "source elimination, cleaning/inspection standards, general inspection training, "
            "autonomous inspection, standardization, and full AM implementation. "
            "Seishin plant (Japan) will serve as benchmark — they achieved 30% downtime "
            "reduction with a similar program in 2024.",
            "other", "No iniciado", "People",
            "Steven Anderson",
            "2026-06-02", "2026-12-18",
            "Reduce unplanned downtime on L1 by 35% (from ~22 min/shift to ≤14 min/shift); "
            "increase operator AM capability score from 1.2 to ≥3.5 (5-point scale); "
            "free 8 h/month of maintenance team capacity for preventive work",
        ),
    )
    ini3_id = cur.lastrowid

    _audit(conn, ini3_id, [
        ("status", None, "No iniciado", "Steven Anderson", _ts("2026-05-05")),
        ("title",  None, "Autonomous maintenance program Line 1", "Steven Anderson", _ts("2026-05-05")),
        ("description", None,
         "Scope confirmed after alignment with Seishin plant (AM benchmark). "
         "Kick-off workshop scheduled for June 2, 2026. "
         "Pre-assessment of operator AM skills planned for May 20–30.",
         "Steven Anderson", _ts("2026-05-06", "10:15:00")),
    ])

    # ── 4. Cancelado — Reject rate reduction autoinjectors ────────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 1,
            "Reject rate reduction autoinjectors",
            "DMAIC project to reduce the reject rate on the autoinjector assembly line (L1) "
            "from 2.3% to below 0.5%. Rejects are driven by cosmetic defects (silicone cap "
            "surface marks, 58%) and dimensional out-of-spec on the needle shield (34%). "
            "Initial root cause hypothesis: seal ring variability and assembly force "
            "calibration drift. Project cancelled after Analyze phase confirmed that "
            "root cause lies in incoming material quality (supplier-side defects), "
            "outside the scope of the OpEx team.",
            "DMAIC", "Cancelado", "Quality",
            "James Carter",
            "2025-10-01", "2026-04-30",
            "Reduce autoinjector reject rate from 2.3% to <0.5%; "
            "save ~18,000 units/month; reduce scrap cost by ~$42,000/month",
        ),
    )
    ini4_id = cur.lastrowid

    _audit(conn, ini4_id, [
        ("status", None, "No iniciado",  "James Carter",    _ts("2025-09-22")),
        ("title",  None, "Reject rate reduction autoinjectors", "James Carter", _ts("2025-09-22")),
        ("status", "No iniciado", "En progreso", "James Carter", _ts("2025-10-01")),
        ("status_comment", None,
         "DMAIC Define phase complete. Reject baseline: 2.3% on L1 (12-week avg). "
         "Top defect categories: silicone cap marks 58%, needle shield out-of-spec 34%. "
         "Measure phase started — 100% inspection data collection for 4 weeks.",
         "James Carter", _ts("2025-10-01")),
        ("status", "En progreso", "Cancelado", "Jennifer Taylor", _ts("2026-02-10")),
        ("status_comment", None,
         "Analyze phase completed. Root cause confirmed: defects originate in incoming "
         "silicone cap components from supplier (Batch traceability: SL-2025-44 to SL-2025-61). "
         "Dimensional variability exceeds our assembly process tolerance — this is a supplier "
         "quality issue, not a process issue. Transferred to Supplier Quality team "
         "(ticket SQ-2026-014, owner: Karen Martinez). OpEx resources redeployed to "
         "serialization DMAIC project.",
         "Jennifer Taylor", _ts("2026-02-10")),
    ])

    conn.commit()
    conn.close()

    print(f"[ok] Initiatives inserted in {DB_PATH}:")
    print(f"  #{ini1_id:3d} Terminado   — Changeover time standardization")
    print(f"  #{ini2_id:3d} En progreso — Serialization error reduction Line 3")
    print(f"  #{ini3_id:3d} No iniciado — Autonomous maintenance program Line 1")
    print(f"  #{ini4_id:3d} Cancelado   — Reject rate reduction autoinjectors")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
