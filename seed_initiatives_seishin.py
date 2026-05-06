"""
seed_initiatives_seishin.py — 4 改善活動サンプルデータ（Seishin / 製茎）

Usage:
    python seed_initiatives_seishin.py
    python seed_initiatives_seishin.py --force
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = "site_seishin.db"
SITE_ID = "seishin"


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _ts(date: str, time: str = "08:00:00") -> str:
    return f"{date} {time}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Migrate to current schema (old status values, missing columns, broken FK)."""
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
        _safe_print("[ok] improvement_initiatives を新スキーマに移行しました")

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
            "TPM自主保全プログラムの標準化",
            "自動注射器組立精度の向上",
            "ライン切替時間のさらなる短縮",
            "検査カメラキャリブレーション改善",
        ]:
            conn.execute(
                "DELETE FROM improvement_initiatives WHERE site_id=? AND title=?",
                (SITE_ID, title),
            )
        conn.commit()

    # ── 1. Terminado — TPM — TPM自主保全プログラムの標準化 ─────────────────────
    # ネットワーク全体のTPMベンチマーク。2024年に完了し、OEE 90%を達成。
    # Sesto・Indianapolis・Fegersheimが本プログラムを参照している。
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,completion_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "TPM自主保全プログラムの標準化",
            "製茎サイト全3ラインにおけるTPM自主保全（AM）プログラムの標準化・展開プロジェクト。"
            "JIPM方式7ステップに従い、オペレーターが日常点検・清掃・給油・増し締め・"
            "異常の早期発見を自律的に実施できる体制を構築する。"
            "背景：不定期停止が多発（平均35分/シフト）し、OEEが87%にとどまっていた。"
            "本プログラム完了後、製茎はグローバルネットワークのTPMベンチマークサイトとなり、"
            "Sesto（伊）・Indianapolis（米）・Fegersheim（仏）への横展開の起点となっている。",
            "other", "Terminado", "People",
            "Ito Masashi",
            "2024-04-01", "2024-12-31", "2024-11-28",
            "不定期停止を35分/シフトから≤25分/シフトに削減（−29%）；"
            "オペレーターAMスコアを1.2から≥3.5/5.0に向上；OEE +3pp（目標90%）",
            "不定期停止：35分→24分/シフト（−31%、目標超過）。"
            "オペレーターAMスコア：1.2→4.1/5.0（全員3.5以上達成）。"
            "OEE：87%→90%（目標達成）。ネットワークベンチマーク認定（2025年1月）。"
            "Sesto・Indianapolis・Fegersheimへの横展開用標準パッケージ作成済み。",
        ),
    )
    ini1_id = cur.lastrowid

    _audit(conn, ini1_id, [
        ("status", None,          "No iniciado",  "Watanabe Emi",  _ts("2024-03-15")),
        ("title",  None,          "TPM自主保全プログラムの標準化",
                                                  "Watanabe Emi",  _ts("2024-03-15")),
        ("status", "No iniciado", "En progreso",  "Ito Masashi",   _ts("2024-04-01")),
        ("status_comment", None,
         "ステップ1（初期清掃・点検）開始。全3ライン対象。"
         "初期清掃で不具合117件を発見（給油漏れ43件、ボルト緩み31件、その他43件）。"
         "赤札・青札管理を導入。清掃基準書の初版作成に着手。",
         "Ito Masashi", _ts("2024-04-01")),
        ("description", None,
         "中間進捗（2024年8月）：ステップ4（総点検訓練）完了。"
         "全オペレーター（18名）が機械の構造・機能・点検手順の教育を修了。"
         "ステップ5（自主点検）の標準チェックリスト（ライン別12種）を作成中。",
         "Ito Masashi", _ts("2024-08-20", "14:00:00")),
        ("status", "En progreso", "Terminado",    "Watanabe Emi",  _ts("2024-11-28")),
        ("status_comment", None,
         "全7ステップ完了。OEE 90%達成（目標）。"
         "不定期停止24分/シフト（ベースライン比−31%）。"
         "AMスコア全員3.5以上。横展開パッケージ（英語版・スペイン語版・フランス語版・イタリア語版）完成。"
         "2025年1月のグローバルOpsExレビューでネットワークベンチマーク認定。",
         "Watanabe Emi", _ts("2024-11-28")),
    ])

    # A3ドキュメント — イニシアティブ1
    a3_html = """<article class="a3-document">
<h2>A3：TPM自主保全プログラムの標準化 — 製茎（Seishin）</h2>
<p><strong>作成者：</strong>伊藤 雅司 &nbsp;|&nbsp; <strong>サイト：</strong>製茎 &nbsp;|&nbsp;
   <strong>開始：</strong>2024年4月1日 &nbsp;|&nbsp; <strong>完了：</strong>2024年11月28日</p>
<hr>

<section><h3>1. 背景（Background）</h3>
<p>製茎サイトでは不定期停止が平均<strong>35分/シフト</strong>発生しており、OEEが<strong>87%</strong>に
とどまっていた。停止原因の62%はオペレーターが対応可能な初期不良（給油漏れ・ボルト緩み・清掃不足）
であったが、発見が遅れ保全部門の対応待ちとなっていた。TPM自主保全（AM）プログラムにより、
オペレーターが自律的に設備を管理できる体制を構築し、OEE 90%とネットワークベンチマーク認定を目指した。</p>
</section>

<section><h3>2. 現状把握（Current Condition）</h3>
<ul>
  <li>不定期停止：<strong>35分/シフト</strong>（全3ライン平均）</li>
  <li>停止原因の62%はAMで予防可能な初期不良</li>
  <li>オペレーターAMスコア：平均<strong>1.2/5.0</strong>（自律点検能力ほぼゼロ）</li>
  <li>OEE：<strong>87%</strong>（目標90%まで+3pp不足）</li>
  <li>保全部門の緊急対応比率：68%（計画保全比率：32%）</li>
</ul>
</section>

<section><h3>3. 目標（Goal）</h3>
<p>2024年12月31日までに：</p>
<ul>
  <li>不定期停止を<strong>≤25分/シフト（−29%）</strong>に削減</li>
  <li>全オペレーターAMスコアを<strong>≥3.5/5.0</strong>に向上</li>
  <li>OEEを<strong>90%</strong>に到達させ、グローバルTPMベンチマーク認定を取得</li>
</ul>
</section>

<section><h3>4. 原因分析（Root Cause Analysis）</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
不定期停止が多発する理由は？
  → オペレーターが設備の異常を早期に発見・処置できていない
    なぜ早期発見できないか？
      → 日常点検の標準がなく、清掃・給油・点検の手順が属人的
        なぜ標準がないか？
          → AM導入前のため、自主保全チェックリストが存在しない
            → 根本原因1：自主保全体制（標準・教育・管理）の欠如

  → 保全部門が緊急対応に追われ、予防保全に時間を割けていない
      なぜ緊急対応が多いか？
        → 初期不良（給油漏れ・ボルト緩み）を早期に処置できず悪化させてから発見
          → 根本原因2：オペレーターの設備管理スキル・意識の不足
</pre>
</section>

<section><h3>5. 対策（Countermeasures）</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">対策</th><th>担当</th><th>期限</th><th>状態</th></tr>
<tr><td style="padding:0.4rem">ステップ1：初期清掃・不具合発見（赤札・青札管理）</td>
    <td>伊藤 雅司</td><td>2024-05-31</td><td>✅ 完了</td></tr>
<tr><td style="padding:0.4rem">ステップ2-3：発生源・困難箇所対策、清掃・給油・点検基準書作成</td>
    <td>伊藤 雅司</td><td>2024-07-31</td><td>✅ 完了</td></tr>
<tr><td style="padding:0.4rem">ステップ4：総点検（機構学習・オペレーター全員教育）</td>
    <td>渡辺 恵美</td><td>2024-09-30</td><td>✅ 完了</td></tr>
<tr><td style="padding:0.4rem">ステップ5-6：自主点検・標準化（ライン別チェックリスト12種）</td>
    <td>伊藤 雅司</td><td>2024-10-31</td><td>✅ 完了</td></tr>
<tr><td style="padding:0.4rem">ステップ7：自主管理の定着・横展開パッケージ作成</td>
    <td>渡辺 恵美</td><td>2024-11-28</td><td>✅ 完了</td></tr>
</table>
</section>

<section><h3>6. 実施計画（Implementation Plan）</h3>
<ul>
  <li><strong>2024年4-5月：</strong>ステップ1 初期清掃・不具合117件摘出・赤札管理開始</li>
  <li><strong>2024年6-7月：</strong>ステップ2-3 発生源対策・基準書作成（清掃/給油/点検）</li>
  <li><strong>2024年8-9月：</strong>ステップ4 機構学習、全オペレーター（18名）教育・テスト</li>
  <li><strong>2024年10月：</strong>ステップ5-6 自主点検チェックリスト運用・標準化</li>
  <li><strong>2024年11月：</strong>ステップ7 定着確認・横展開パッケージ（4言語）完成・A3クローズ</li>
</ul>
</section>

<section><h3>7. フォローアップ指標（Follow-up KPIs）</h3>
<ul>
  <li>不定期停止時間/シフト（目標≤25分 → 実績：24分）</li>
  <li>オペレーターAMスコア（目標≥3.5/5.0 → 実績：4.1/5.0）</li>
  <li>OEE（目標90% → 実績：90%）</li>
  <li>計画保全比率（目標≥60% → 実績：72%）</li>
</ul>
</section>

<section><h3>8. 結果（Results）— ネットワークベンチマーク</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">
✅ <strong>2024年11月28日完了。全目標達成。2025年1月グローバルTPMベンチマーク認定。</strong></p>
<ul>
  <li>不定期停止：35分 → <strong>24分/シフト</strong>（−31%、目標−29%超過）</li>
  <li>オペレーターAMスコア：1.2 → <strong>4.1/5.0</strong>（全員3.5以上）</li>
  <li>OEE：87% → <strong>90%</strong></li>
  <li>計画保全比率：32% → <strong>72%</strong>（緊急対応ほぼ解消）</li>
  <li>横展開実績：Sesto（2025年参照）、Indianapolis（2026年参照）、Fegersheim（2026年参照）</li>
</ul>
</section>
</article>"""

    conn.execute(
        """INSERT INTO initiative_documents
           (initiative_id,document_type,title,content_html,author)
           VALUES (?,?,?,?,?)""",
        (ini1_id, "A3", "A3：TPM自主保全プログラムの標準化 — 製茎", a3_html, "Ito Masashi"),
    )

    # ── 2. En progreso — DMAIC — 自動注射器組立精度の向上 ─────────────────────
    # 自動注射器の組立精度不良率0.8%を低減するDMAICプロジェクト。
    # 主要不良：プランジャー組込み位置ずれ（54%）、キャップ嵌合不良（31%）。
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit,actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 2,
            "自動注射器組立精度の向上",
            "ライン2（自動注射器）の組立精度不良率をDMAICで低減するプロジェクト。"
            "現状の不良率は0.8%（12週平均）で、目標は≤0.2%。"
            "主要不良カテゴリ：プランジャー組込み位置ずれ（54%）、キャップ嵌合不良（31%）、"
            "その他（15%）。Measure フェーズの結果、位置ずれの発生は組立チャックの"
            "摩耗と熱膨張（シフト後半に集中）が主要因と仮説。"
            "Analyze フェーズ（MSA・回帰分析）を2026年5月完了予定。",
            "DMAIC", "En progreso", "Quality",
            "Suzuki Aiko",
            "2026-02-01", "2026-09-30",
            "組立精度不良率を0.8%から≤0.2%に削減（−75%）；"
            "月間廃棄ロス≥6,400ユニット削減；顧客クレームリスクの低減",
            None,
        ),
    )
    ini2_id = cur.lastrowid

    _audit(conn, ini2_id, [
        ("status", None,          "No iniciado",  "Suzuki Aiko",   _ts("2026-01-20")),
        ("title",  None,          "自動注射器組立精度の向上",
                                                  "Suzuki Aiko",   _ts("2026-01-20")),
        ("status", "No iniciado", "En progreso",  "Suzuki Aiko",   _ts("2026-02-01")),
        ("status_comment", None,
         "Define フェーズ完了。不良率ベースライン確定：0.8%（L2、12週平均）。"
         "Measure フェーズ開始：全数検査データ収集（4週間）、"
         "チャック摩耗量・環境温度・不良率の相関分析を設定。",
         "Suzuki Aiko", _ts("2026-02-01")),
        ("description", None,
         "Analyze フェーズ中間報告（2026年4月）："
         "組立チャック摩耗量と位置ずれ不良率の相関 r=0.88（有意）。"
         "熱膨張の影響：シフト開始後4時間以降に不良率が1.4倍に上昇（確認済み）。"
         "対策案：チャック交換間隔を6ヶ月→3ヶ月に短縮、自動補正機構の導入評価中。",
         "Suzuki Aiko", _ts("2026-04-22", "10:00:00")),
    ])

    # ── 3. No iniciado — Kaizen — ライン切替時間のさらなる短縮 ────────────────
    # 製茎は現在ネットワーク最速のchangeover（平均19分）。
    # 次の目標は30分→20分未満への短縮（さらなる差別化）。
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "ライン切替時間のさらなる短縮",
            "全3ラインのライン切替時間をさらに短縮するKaizenプロジェクト。"
            "現状：平均19分（範囲14〜24分）— 既にネットワーク最速。"
            "目標：平均≤12分（さらに−37%）。"
            "主要施策：①並行作業の拡大（現状35%→目標60%の切替作業を機械停止前に実施）、"
            "②ワンタッチ締結具の導入（現状ボルト締結を全箇所ワンタッチ化）、"
            "③デジタルピッキングシステムによる部品取り出し時間のゼロ化。"
            "Indianapolis（SMED 45分→ベンチマーク）との逆展開により、"
            "製茎→グローバルネットワーク全体への知見還流を目指す。",
            "Kaizen", "No iniciado", "Delivery",
            "Nakamura Kenji",
            "2026-07-01", "2026-12-18",
            "ライン切替時間：平均19分→≤12分（−37%）；"
            "切替によるOEE損失をさらに−0.8pp改善；"
            "新標準をグローバルネットワークに展開",
        ),
    )
    ini3_id = cur.lastrowid

    _audit(conn, ini3_id, [
        ("status", None, "No iniciado", "Nakamura Kenji", _ts("2026-05-02")),
        ("title",  None, "ライン切替時間のさらなる短縮",
                                        "Nakamura Kenji", _ts("2026-05-02")),
        ("description", None,
         "スコープ確定（2026年5月）：ワンタッチ締結具の見積依頼を3社に送付済み。"
         "デジタルピッキングシステムはIndianapolisのSMED知見を参考に仕様策定中。"
         "現状切替作業の動画撮影（全3ライン×全3シフト）を6月中に実施予定。",
         "Nakamura Kenji", _ts("2026-05-06", "09:30:00")),
    ])

    # ── 4. Cancelado — 検査カメラキャリブレーション改善 ───────────────────────
    # 機器アップグレード（新型カメラシステム導入）により問題が根本解決されたため中止。
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id,line_number,title,description,methodology,status,category,
            owner,start_date,target_date,expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, None,
            "検査カメラキャリブレーション改善",
            "全ライン検査カメラ（Vision システム）の校正精度向上と校正頻度の最適化プロジェクト。"
            "問題：カメラ校正のドリフトが週1回発生し、毎回15分の再校正停止が必要。"
            "年間換算で約39時間の生産停止に相当。"
            "根本原因仮説：振動と温度変動による光学系の微小変位。"
            "イニシアティブは、新型検査カメラシステム（Cognex In-Sight 9000シリーズ）の"
            "導入決定（2025年10月設備投資審査承認）により中止。"
            "新システムは自動校正機能を内蔵しており、キャリブレーションドリフト問題を"
            "機器レベルで根本解決する。",
            "other", "Cancelado", "Quality",
            "Ito Masashi",
            "2025-09-01", "2026-02-28",
            "校正停止を週1回15分→月1回以下に削減；年間生産停止時間≥36時間削減",
        ),
    )
    ini4_id = cur.lastrowid

    _audit(conn, ini4_id, [
        ("status", None,          "No iniciado",  "Ito Masashi",   _ts("2025-08-20")),
        ("title",  None,          "検査カメラキャリブレーション改善",
                                                  "Ito Masashi",   _ts("2025-08-20")),
        ("status", "No iniciado", "En progreso",  "Ito Masashi",   _ts("2025-09-01")),
        ("status_comment", None,
         "現状分析開始。校正ドリフト発生パターン確認："
         "月曜夜間シフト後（週末温度変動）と予防保全後（機械停止→再起動）に集中。"
         "振動センサーと温度ロガーをカメラ架台に設置して相関データ収集中。",
         "Ito Masashi", _ts("2025-09-01")),
        ("status", "En progreso", "Cancelado",    "Watanabe Emi",  _ts("2025-12-10")),
        ("status_comment", None,
         "中止理由：機器のアップグレードにより解決済み。"
         "2025年10月の設備投資審査でCognex In-Sight 9000シリーズ（自動校正機能内蔵）の"
         "導入が承認された（導入予定：2026年Q1）。"
         "新システムは本イニシアティブが解決しようとしていたキャリブレーションドリフト問題を"
         "機器レベルで根本解決するため、ソフト面での改善活動を継続する意義がなくなった。"
         "伊藤の工数はTPM横展開支援（Sesto向け）に再配分。",
         "Watanabe Emi", _ts("2025-12-10")),
    ])

    conn.commit()
    conn.close()

    _safe_print(f"[ok] 改善活動データを {DB_PATH} に登録しました：")
    _safe_print(f"  #{ini1_id:3d} Terminado   — TPM自主保全プログラムの標準化")
    _safe_print(f"  #{ini2_id:3d} En progreso — 自動注射器組立精度の向上")
    _safe_print(f"  #{ini3_id:3d} No iniciado — ライン切替時間のさらなる短縮")
    _safe_print(f"  #{ini4_id:3d} Cancelado   — 検査カメラキャリブレーション改善")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
