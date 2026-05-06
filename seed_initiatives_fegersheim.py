"""
seed_initiatives_fegersheim.py — 4 initiatives de démonstration pour Fegersheim (français).

Usage:
    python seed_initiatives_fegersheim.py
    python seed_initiatives_fegersheim.py --force
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = "site_fegersheim.db"
SITE_ID = "fegersheim"


def _ts(date: str, time: str = "08:00:00") -> str:
    return f"{date} {time}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Migrate to current schema (handles old status values, missing columns, broken FK)."""
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
            for k, v in [("category","Quality"),("deleted",0),("deleted_at",None),
                         ("deleted_by",None),("deletion_reason",None)]:
                d.setdefault(k, v)
            conn.execute(
                """INSERT INTO improvement_initiatives
                   (id,site_id,line_number,title,description,methodology,status,category,
                    owner,start_date,target_date,completion_date,expected_benefit,
                    actual_benefit,linked_problem_id,deleted,deleted_at,deleted_by,deletion_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d["id"],d["site_id"],d.get("line_number"),d["title"],d["description"],
                 d["methodology"],d["status"],d["category"],d["owner"],d["start_date"],
                 d["target_date"],d.get("completion_date"),d.get("expected_benefit"),
                 d.get("actual_benefit"),d.get("linked_problem_id"),
                 d["deleted"],d["deleted_at"],d["deleted_by"],d["deletion_reason"]),
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
        print("[ok] improvement_initiatives migré vers le nouveau schéma")

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
            "Réduction des micro-arrêts Ligne 1",
            "Transfert des pratiques TPM de Seishin",
            "Amélioration de la fiabilité sérialisation L3",
            "Standardisation du nettoyage entre lots",
        ]:
            conn.execute(
                "DELETE FROM improvement_initiatives WHERE site_id=? AND title=?",
                (SITE_ID, title),
            )
        conn.commit()

    # ── 1. En progreso — A3 — Réduction des micro-arrêts Ligne 1 ──────────────
    # Fegersheim a le pire OEE du réseau (79%). Les micro-arrêts sur L1 en sont
    # la première cause: 12 arrêts/poste < 3 min chacun → −3,8 pp d'OEE.
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 1,
            "Réduction des micro-arrêts Ligne 1",
            "Projet A3 pour éliminer les micro-arrêts récurrents sur la ligne 1 (ampoules). "
            "Fréquence actuelle: 12 micro-arrêts/poste d'une durée moyenne de 2,5 min chacun, "
            "soit 30 min de production perdue par poste. Ce problème est la première cause "
            "de perte d'OEE sur le site de Fegersheim (OEE actuel 79%, pire réseau). "
            "Les micro-arrêts sont principalement localisés au niveau de l'alimentateur "
            "de bouchons (46%) et du convoyeur principal (31%). Phase diagnostic en cours: "
            "enregistrement vidéo et analyse Pareto des modes de défaillance.",
            "A3", "En progreso", "Delivery",
            "Claire Rousseau",
            "2026-02-03", "2026-08-31",
            "Réduire les micro-arrêts L1 de 12/poste à ≤3/poste (−75%); "
            "récupérer ≥22 min de production/poste; OEE L1 +2,5 pp",
            None,
        ),
    )
    ini1_id = cur.lastrowid

    _audit(conn, ini1_id, [
        ("status", None,          "No iniciado",  "Claire Rousseau",  _ts("2026-01-22")),
        ("title",  None,          "Réduction des micro-arrêts Ligne 1",
                                                  "Claire Rousseau",  _ts("2026-01-22")),
        ("status", "No iniciado", "En progreso",  "Claire Rousseau",  _ts("2026-02-03")),
        ("status_comment", None,
         "Phase diagnostic démarrée. Mesure fréquence micro-arrêts confirmée: 12/poste "
         "sur L1 (moyenne 8 semaines). Caméra installée sur alimentateur bouchons et "
         "convoyeur principal. Analyse Pareto des modes de défaillance en cours.",
         "Claire Rousseau", _ts("2026-02-03")),
        ("description", None,
         "Avancement phase analyse (avril 2026): Pareto finalisé — alimentateur bouchons "
         "46% des micro-arrêts (cause: ressort de rappel fatigué), convoyeur 31% "
         "(cause: accumulation résidu produit sur rails). Contre-mesures en cours "
         "de définition avec François Moreau.",
         "Claire Rousseau", _ts("2026-04-08", "14:30:00")),
    ])

    # ── 2. En progreso — Kaizen — Transfert des pratiques TPM de Seishin ───────
    # Initiative cross-site: Seishin (Japon) est le benchmark TPM du réseau
    # (OEE 90%, programme AM déployé en 2024). Fegersheim adapte les standards.
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "Transfert des pratiques TPM de Seishin",
            "Initiative cross-site Kaizen pour adapter et déployer les pratiques TPM "
            "(Total Productive Maintenance) du site de Seishin (Japon) à Fegersheim. "
            "Seishin a atteint un OEE de 90% grâce à un programme de maintenance autonome "
            "(AM) complet déployé en 2024 — benchmark réseau. L'initiative couvre: "
            "1) visite benchmark Seishin (mars 2026, 3 jours, 2 personnes), "
            "2) adaptation des standards AM au contexte Fegersheim (réglementation EU, "
            "contraintes GMP pharma), 3) formation des opérateurs sur les 3 lignes, "
            "4) mise en place des check-lists AM quotidiennes. Pilote sur L2 en mai 2026.",
            "Kaizen", "En progreso", "People",
            "François Moreau",
            "2026-03-01", "2026-09-30",
            "Déployer AM sur les 3 lignes; réduire pannes non planifiées de 25% "
            "(de 58 min/poste à ≤44 min/poste); augmenter score AM opérateurs de 1,0 à ≥3,0/5",
            None,
        ),
    )
    ini2_id = cur.lastrowid

    _audit(conn, ini2_id, [
        ("status", None,          "No iniciado",  "François Moreau",  _ts("2026-02-12")),
        ("title",  None,          "Transfert des pratiques TPM de Seishin",
                                                  "François Moreau",  _ts("2026-02-12")),
        ("status", "No iniciado", "En progreso",  "François Moreau",  _ts("2026-03-01")),
        ("status_comment", None,
         "Visite benchmark Seishin confirmée: 10–12 mars 2026, participants: "
         "François Moreau (maintenance) et Pierre Dupont (opérateur L2). "
         "Programme de visite reçu: observation AM quotidien, formation standards 5S, "
         "revue des check-lists et des OPL (One Point Lessons).",
         "François Moreau", _ts("2026-03-01")),
        ("description", None,
         "Retour visite Seishin (mars 2026): 14 standards AM identifiés à adapter. "
         "Points clés: nettoyage-inspection quotidien 15 min, 8 check-lists par ligne, "
         "management visuel des anomalies (étiquettes rouges/bleues). "
         "Adaptation GMP en cours avec Sophie Lefebvre. Pilote L2 confirmé mai 2026.",
         "François Moreau", _ts("2026-04-02", "09:00:00")),
    ])

    # ── 3. No iniciado — DMAIC — Amélioration fiabilité sérialisation L3 ───────
    # Problème partagé avec Alcobendas et Indianapolis (caméra 2D sérialisation).
    # Fegersheim L3 démarre le projet après les enseignements des autres sites.
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 3,
            "Amélioration de la fiabilité sérialisation L3",
            "Projet DMAIC pour réduire les arrêts liés aux erreurs de lecture de la caméra 2D "
            "dans le module de sérialisation Track & Trace de la ligne 3. Fréquence actuelle: "
            "3,5 arrêts/semaine, durée moyenne 18 min (nettoyage + redémarrage + revalidation GxP). "
            "Ce projet bénéficiera des enseignements des projets déjà en cours à Alcobendas (A3) "
            "et Indianapolis (DMAIC), qui ont identifié la condensation et l'aérosol adhésif "
            "comme causes racines sur le même modèle de caméra. "
            "Démarrage prévu en juin 2026 après libération des ressources qualité "
            "de l'initiative nettoyage entre lots.",
            "DMAIC", "No iniciado", "Quality",
            "Sophie Lefebvre",
            "2026-06-02", "2026-12-18",
            "Réduire les arrêts sérialisation L3 de 3,5/semaine à ≤0,3/semaine; "
            "récupérer ≥57 min de production/semaine; OEE L3 +1,4 pp",
        ),
    )
    ini3_id = cur.lastrowid

    _audit(conn, ini3_id, [
        ("status", None, "No iniciado", "Sophie Lefebvre", _ts("2026-05-04")),
        ("title",  None, "Amélioration de la fiabilité sérialisation L3",
                                        "Sophie Lefebvre", _ts("2026-05-04")),
        ("description", None,
         "Scope élargi: intégrer les résultats des contre-mesures Alcobendas (purge air sec) "
         "et Indianapolis (rideau d'air) avant de lancer la phase Define. "
         "Appel cross-site planifié avec Karen Martinez (Indianapolis) le 15 mai 2026.",
         "Sophie Lefebvre", _ts("2026-05-06", "11:00:00")),
    ])

    # ── 4. Terminado — 5Why — Standardisation du nettoyage entre lots ──────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,completion_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "Standardisation du nettoyage entre lots",
            "Analyse 5 Pourquoi et standardisation de la procédure de nettoyage entre lots "
            "sur les 3 lignes de Fegersheim. Problème initial: durées de nettoyage très "
            "variables (45 à 95 min selon l'équipe et la ligne), incidents de contamination "
            "croisée documentés (2 déviations qualité en Q3 2025), et absence de procédure "
            "unifiée entre les équipes matin/après-midi/nuit. "
            "La cause racine identifiée était l'absence d'un standard opératoire détaillé "
            "et l'absence de critères visuels clairs pour valider la fin du nettoyage.",
            "5Why", "Terminado", "Quality",
            "Pierre Dupont",
            "2025-10-06", "2026-02-28", "2026-02-12",
            "Réduire le temps de nettoyage moyen de 68 min à ≤50 min (−26%); "
            "éliminer les déviations qualité liées au nettoyage (objectif: 0 en 6 mois); "
            "standardiser la procédure sur les 3 lignes et 3 équipes",
            "Durée nettoyage: 68 min → 48 min (−29% — objectif dépassé). "
            "Déviations qualité nettoyage: 2 en Q3-2025 → 0 depuis novembre 2025. "
            "SOP-NET-001 v2.0 déployé sur les 3 lignes, 18 opérateurs formés.",
        ),
    )
    ini4_id = cur.lastrowid

    _audit(conn, ini4_id, [
        ("status", None,          "No iniciado",  "Pierre Dupont",    _ts("2025-09-25")),
        ("title",  None,          "Standardisation du nettoyage entre lots",
                                                  "Pierre Dupont",    _ts("2025-09-25")),
        ("status", "No iniciado", "En progreso",  "Pierre Dupont",    _ts("2025-10-06")),
        ("status_comment", None,
         "Phase diagnostic démarrée: chronométrage de 24 nettoyages sur 3 lignes × 3 équipes. "
         "Durée moyenne: 68 min (min 45, max 95 min). Variabilité principale entre équipes "
         "(±18 min) et entre lignes (L1 plus longue: 74 min vs L3: 62 min).",
         "Pierre Dupont", _ts("2025-10-06")),
        ("status", "En progreso", "Terminado",    "Claire Rousseau",  _ts("2026-02-12")),
        ("status_comment", None,
         "SOP-NET-001 v2.0 déployé sur les 3 lignes. Formation de 18 opérateurs complétée. "
         "Suivi 8 semaines: durée nettoyage 48 min (−29%). Aucune déviation qualité nettoyage "
         "depuis novembre 2025. Clôture 5 Pourquoi approuvée par responsable qualité.",
         "Claire Rousseau", _ts("2026-02-12")),
    ])

    # Document A3 (5Why write-up) — initiative 4
    a3_html = """<article class="a3-document">
<h2>Analyse 5 Pourquoi : Standardisation du nettoyage entre lots — Fegersheim</h2>
<p><strong>Auteur :</strong> Pierre Dupont &nbsp;|&nbsp; <strong>Site :</strong> Fegersheim &nbsp;|&nbsp;
   <strong>Début :</strong> 2025-10-06 &nbsp;|&nbsp; <strong>Clôture :</strong> 2026-02-12</p>
<hr>

<section><h3>1. Background / Contexte</h3>
<p>Les 3 lignes de Fegersheim présentent des durées de nettoyage entre lots très variables :
de 45 à 95 minutes selon l'équipe et la ligne. Cette variabilité a généré
<strong>2 déviations qualité</strong> en Q3 2025 (contamination croisée partielle) et représente
une perte de capacité estimée à <strong>~3,5 h/semaine</strong> par rapport à un nettoyage
standardisé à 50 minutes.</p>
</section>

<section><h3>2. État Actuel (baseline)</h3>
<ul>
  <li>Durée moyenne de nettoyage : <strong>68 min</strong> (range : 45–95 min)</li>
  <li>Variabilité inter-équipes : ±18 min</li>
  <li>Variabilité inter-lignes : L1 = 74 min, L2 = 68 min, L3 = 62 min</li>
  <li>Déviations qualité liées au nettoyage : 2 en Q3 2025 (contamination croisée)</li>
  <li>Absence de procédure standard écrite commune aux 3 équipes</li>
  <li>Critères visuels de fin de nettoyage non définis</li>
</ul>
</section>

<section><h3>3. Objectif</h3>
<p>Standardiser la procédure de nettoyage sur les 3 lignes et 3 équipes ;<br>
réduire la durée moyenne à <strong>≤50 min</strong> avant le 28 février 2026 ;<br>
atteindre <strong>0 déviation qualité</strong> liée au nettoyage sur 6 mois consécutifs.</p>
</section>

<section><h3>4. Analyse 5 Pourquoi</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
Pourquoi les durées de nettoyage sont-elles si variables ?
  → Parce que chaque équipe applique sa propre séquence de nettoyage
    Pourquoi chaque équipe a-t-elle sa propre séquence ?
      → Parce qu'il n'existe pas de SOP unique et détaillé pour le nettoyage entre lots
        Pourquoi n'existe-t-il pas de SOP unique ?
          → Parce que la procédure historique (PRC-CLN-02 v1.0, 2019) est trop générique
            et n'a pas été mise à jour lors de l'extension du site en 2022
              → CAUSE RACINE 1 : SOP obsolète, non adapté aux 3 lignes actuelles

Pourquoi y a-t-il des déviations qualité (contamination croisée) ?
  → Parce que la validation de fin de nettoyage repose sur le jugement individuel
    Pourquoi le jugement individuel est-il insuffisant ?
      → Parce qu'il n'existe pas de critères visuels standardisés (seuils d'acceptation)
        ni de check-list de vérification obligatoire avant redémarrage
          → CAUSE RACINE 2 : Absence de critères visuels et de check-list de validation
</pre>
</section>

<section><h3>5. Contre-mesures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Responsable</th><th>Date</th><th>Statut</th></tr>
<tr><td style="padding:0.4rem">Chronométrer 24 nettoyages (3 lignes × 3 équipes × 2,67 obs)</td>
    <td>Pierre Dupont</td><td>2025-10-25</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Rédiger SOP-NET-001 v2.0 — séquence standard en 12 étapes par ligne</td>
    <td>Sophie Lefebvre</td><td>2025-11-28</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Créer check-list visuelle de validation fin de nettoyage (affichage en ligne)</td>
    <td>Pierre Dupont</td><td>2025-12-10</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Former les 18 opérateurs des 3 équipes sur SOP-NET-001 v2.0</td>
    <td>Claire Rousseau</td><td>2026-01-15</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Suivi 8 semaines : chronométrage aléatoire 2/semaine + audit qualité</td>
    <td>Sophie Lefebvre</td><td>2026-02-12</td><td>✅ Fait</td></tr>
</table>
</section>

<section><h3>6. Plan d'implémentation</h3>
<ul>
  <li><strong>Oct 6–25 :</strong> Diagnostic — chronométrage des 24 nettoyages, cartographie des écarts</li>
  <li><strong>Oct 26 – Nov 28 :</strong> Rédaction SOP-NET-001 v2.0 et check-list visuelle</li>
  <li><strong>Déc 2025 :</strong> Pilote L2 équipe matin — ajustements SOP si nécessaire</li>
  <li><strong>Jan 2026 :</strong> Déploiement toutes lignes et équipes, formation 18 opérateurs</li>
  <li><strong>Jan–Fév 2026 :</strong> Suivi 8 semaines, mesures, clôture</li>
</ul>
</section>

<section><h3>7. Suivi / KPIs</h3>
<ul>
  <li>Durée nettoyage moyenne/semaine par ligne (objectif ≤50 min → résultat : 48 min)</li>
  <li>Variabilité (écart-type) entre équipes (objectif ≤5 min → résultat : ±4 min)</li>
  <li>Déviations qualité liées au nettoyage (objectif 0 → résultat : 0 depuis nov. 2025)</li>
</ul>
</section>

<section><h3>8. Résultats</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">
✅ <strong>Projet clôturé le 12 février 2026. Objectif dépassé.</strong></p>
<ul>
  <li>Durée nettoyage : 68 min → <strong>48 min</strong> (−29% ; objectif −26%)</li>
  <li>Variabilité inter-équipes : ±18 min → <strong>±4 min</strong></li>
  <li>Déviations qualité : 2 en Q3-2025 → <strong>0 depuis novembre 2025</strong></li>
  <li>Capacité récupérée : <strong>~4,2 h/semaine</strong> sur les 3 lignes</li>
  <li>SOP-NET-001 v2.0 déployé — 18 opérateurs formés et certifiés</li>
</ul>
</section>
</article>"""

    conn.execute(
        """INSERT INTO initiative_documents
           (initiative_id,document_type,title,content_html,author)
           VALUES (?,?,?,?,?)""",
        (ini4_id, "A3",
         "5 Pourquoi : Standardisation du nettoyage entre lots — Fegersheim",
         a3_html, "Pierre Dupont"),
    )

    conn.commit()
    conn.close()

    print(f"[ok] Initiatives insérées dans {DB_PATH} :")
    print(f"  #{ini1_id:3d} En progreso — Réduction des micro-arrêts Ligne 1")
    print(f"  #{ini2_id:3d} En progreso — Transfert des pratiques TPM de Seishin")
    print(f"  #{ini3_id:3d} No iniciado — Amélioration de la fiabilité sérialisation L3")
    print(f"  #{ini4_id:3d} Terminado   — Standardisation du nettoyage entre lots")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
