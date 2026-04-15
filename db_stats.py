#!/usr/bin/env python3
"""
db_stats.py — WebScraper database report
=========================================
Outputs data for two thesis tables AND performs automatic extraction-quality
scoring using the most-scraped URLs in the database.

  Tabuľka 2  Výsledky testovania na reálnych webových stránkach
  Tabuľka 3  Kvalita extrakcie na referenčnej vzorke (automatická heuristika)

HOW TO RUN
----------
    docker compose exec api python3 /WebScraper/db_stats.py

Or from the host:
    python3 db_stats.py --host localhost --port 5432 \
        --user webscraper --password YOUR_PW --dbname webscraper

Optional flags:
    --sample-per-domain  N   how many top URLs to score per domain (default 10)
    --min-words          N   minimum words expected in good extraction (default 50)

HOW TABLE 3 WORKS
-----------------
Since there is no manual ground truth, we use content-based heuristics to
score each scraped result automatically:

  Precision proxy
    = (content_blocks with enough text) / (total content_blocks extracted)
    Low precision → scraper included too many short/noisy blocks (nav, ads…)

  Recall proxy
    = min(1.0, total_words_extracted / expected_words_per_page)
    Low recall → scraper missed most of the page text

  F1 = harmonic mean of the two proxies

The TOP N URLs per domain (by content_length) are used as the sample —
longer pages have more signal and represent the typical successful scrape.

LIMITATIONS
-----------
These are proxies, not true information-retrieval metrics. They tell you
whether the extractor produced "enough" structured text, not whether that
text exactly matches a human annotation. For a true evaluation, replace
these values with manually computed ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed.  Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from tabulate import tabulate
except ImportError:
    print("ERROR: tabulate not installed.  Run: pip install tabulate")
    sys.exit(1)


# =============================================================================
# CONNECTION
# =============================================================================

def get_connection(args):
    host     = args.host     or os.environ.get("POSTGRES_HOST",     "postgres")
    port     = args.port     or int(os.environ.get("POSTGRES_PORT", "5432"))
    user     = args.user     or os.environ.get("POSTGRES_USER",     "webscraper")
    password = args.password or os.environ.get("POSTGRES_PASSWORD", "")
    dbname   = args.dbname   or os.environ.get("POSTGRES_DB",       "webscraper")
    return psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname
    )


# =============================================================================
# HELPERS
# =============================================================================

def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or url
        if domain.startswith("www."):
            domain = domain[4:]
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain.lower()
    except Exception:
        return url


def fmt_pct(v: float) -> str:
    return f"{v:.0f} %"


def fmt_time(s: float | None) -> str:
    if s is None:
        return "—"
    if s >= 60:
        return f"{s / 60:.1f} min"
    return f"{s:.1f} s"


# =============================================================================
# TABLE 1 — SCRAPING PERFORMANCE PER DOMAIN
# =============================================================================

def build_table1(conn) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, start_url, pages_scraped, pages_failed, pages_per_second
        FROM   jobs
        WHERE  status IN ('completed', 'stopped', 'failed')
        ORDER  BY created_at DESC
    """)
    jobs = cur.fetchall()
    if not jobs:
        return []

    domain_jobs: dict = defaultdict(list)
    for j in jobs:
        domain_jobs[extract_domain(j["start_url"])].append(j)

    cur.execute("""
        SELECT job_id, COUNT(*) AS cnt
        FROM   log_entries
        WHERE  message LIKE '%js_rendering_triggered%'
        GROUP  BY job_id
    """)
    pw_counts = {str(r["job_id"]): r["cnt"] for r in cur.fetchall()}

    cur.execute("""
        SELECT job_id, COUNT(*) AS cnt
        FROM   log_entries
        WHERE  message LIKE 'Scraping:%'
        GROUP  BY job_id
    """)
    attempted = {str(r["job_id"]): r["cnt"] for r in cur.fetchall()}

    WALL_TYPES = [
        "cloudflare","recaptcha","hcaptcha","datadome","perimeterx",
        "login_wall","cookie_consent","paywall","rate_limit",
        "session_expired","ip_ban",
    ]
    cur.execute("""
        SELECT job_id, message
        FROM   log_entries
        WHERE  message LIKE '%wall_detected%'
           OR  message LIKE '%Wall blocked%'
           OR  message LIKE '%Wall persists%'
    """)
    job_walls: dict = defaultdict(set)
    for r in cur.fetchall():
        msg = r["message"].lower()
        jid = str(r["job_id"])
        for wt in WALL_TYPES:
            if wt in msg:
                job_walls[jid].add(wt)

    rows = []
    for domain, djobs in sorted(domain_jobs.items()):
        scraped = sum(j["pages_scraped"] or 0 for j in djobs)
        failed  = sum(j["pages_failed"]  or 0 for j in djobs)
        total   = scraped + failed
        success = scraped / total * 100 if total else 0.0

        speeds = [
            j["pages_per_second"]
            for j in djobs
            if j["pages_per_second"] and j["pages_per_second"] > 0
        ]
        avg_time = (1.0 / (sum(speeds) / len(speeds))) if speeds else None

        total_pw  = sum(pw_counts.get(str(j["id"]), 0) for j in djobs)
        total_att = sum(attempted.get(str(j["id"]), 0)  for j in djobs)
        pw_pct = total_pw / total_att * 100 if total_att else 0.0

        all_walls = set()
        for j in djobs:
            all_walls.update(job_walls.get(str(j["id"]), set()))
        walls_str = ", ".join(sorted(all_walls)) if all_walls else "žiadne"

        rows.append({
            "Doména":                domain,
            "Spracované stránky":    total,
            "Úspešnosť":             fmt_pct(success),
            "Priemerný čas/stránka": fmt_time(avg_time),
            "Playwright fallback":   fmt_pct(pw_pct),
            "Aktivované bariéry":    walls_str,
        })

    cur.close()
    return rows


# =============================================================================
# TABLE 3 — EXTRACTION QUALITY (automatic heuristic on top URLs)
# =============================================================================

def _count_words(text: str) -> int:
    return len(text.split())


def _score_result(content_json, min_words: int, expected_words: int) -> tuple[float, float]:
    """
    Return (precision_proxy, recall_proxy) for one scrape_result.content blob.

    content is a JSON list of blocks: [{"type": ..., "content": ...}, ...]

    Precision proxy
    ───────────────
    = blocks_with_enough_text / total_blocks
    A block "has enough text" if it has >= min_words words.
    Short blocks are assumed to be noise (nav items, captions, metadata).

    Recall proxy
    ────────────
    = min(1.0,  total_words / expected_words)
    expected_words is the median word count of the top-N sample for the domain,
    so a result is penalised only if it falls significantly short of its peers.
    """
    if not content_json:
        return 0.0, 0.0

    # Parse content
    try:
        if isinstance(content_json, str):
            blocks = json.loads(content_json)
        else:
            blocks = content_json
    except Exception:
        return 0.0, 0.0

    if not isinstance(blocks, list) or len(blocks) == 0:
        return 0.0, 0.0

    total_blocks    = len(blocks)
    rich_blocks     = 0
    total_words     = 0

    for block in blocks:
        if isinstance(block, dict):
            text = block.get("content", "")
        else:
            text = str(block)
        wc = _count_words(text)
        total_words += wc
        if wc >= min_words:
            rich_blocks += 1

    precision = rich_blocks / total_blocks if total_blocks else 0.0
    recall    = min(1.0, total_words / expected_words) if expected_words > 0 else 0.0

    return precision, recall


def build_table3(conn, sample_per_domain: int = 10, min_words: int = 50) -> list:
    """
    For each domain:
      1. Find the TOP sample_per_domain URLs by content_length
         (longest = richest pages = most representative sample)
      2. Score each with precision/recall heuristics
      3. Average → F1

    Returns list of dicts ready for tabulate.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── Fetch all completed jobs ──────────────────────────────────────────────
    cur.execute("""
        SELECT id, start_url
        FROM   jobs
        WHERE  status IN ('completed', 'stopped')
    """)
    jobs = cur.fetchall()
    if not jobs:
        return []

    # Group job IDs by domain
    domain_job_ids: dict = defaultdict(list)
    for j in jobs:
        domain_job_ids[extract_domain(j["start_url"])].append(j["id"])

    rows = []

    for domain, job_ids in sorted(domain_job_ids.items()):

        # ── Pull top N results (most content) for this domain ─────────────────
        cur.execute("""
            SELECT sr.url, sr.content, sr.content_length
            FROM   scrape_results sr
            WHERE  sr.job_id = ANY(%s::uuid[])
              AND  sr.error  IS NULL
              AND  sr.content IS NOT NULL
              AND  sr.content_length > 0
            ORDER  BY sr.content_length DESC
            LIMIT  %s
        """, ([str(jid) for jid in job_ids], sample_per_domain))

        results = cur.fetchall()

        if not results:
            rows.append({
                "Doména":              domain,
                "Vzorka (stránok)":    0,
                "Precision":           "—",
                "Recall":              "—",
                "F1 skóre":            "—",
            })
            continue

        # Median word count across sample → used as expected_words for recall
        word_counts = []
        for r in results:
            try:
                if isinstance(r["content"], str):
                    blocks = json.loads(r["content"])
                else:
                    blocks = r["content"]
                wc = sum(_count_words(b.get("content","") if isinstance(b,dict) else str(b))
                         for b in (blocks if isinstance(blocks,list) else []))
                word_counts.append(wc)
            except Exception:
                word_counts.append(0)

        word_counts.sort()
        n = len(word_counts)
        if n == 0:
            expected_words = 200
        elif n % 2 == 1:
            expected_words = word_counts[n // 2]
        else:
            expected_words = (word_counts[n // 2 - 1] + word_counts[n // 2]) // 2
        # Guard against degenerate median
        expected_words = max(expected_words, min_words * 2)

        # ── Score each result ─────────────────────────────────────────────────
        precisions = []
        recalls    = []

        for r in results:
            p, rc = _score_result(r["content"], min_words, expected_words)
            precisions.append(p)
            recalls.append(rc)

        avg_p  = sum(precisions) / len(precisions)
        avg_r  = sum(recalls)    / len(recalls)
        avg_f1 = (2 * avg_p * avg_r / (avg_p + avg_r)) if (avg_p + avg_r) > 0 else 0.0

        rows.append({
            "Doména":           domain,
            "Vzorka (stránok)": len(results),
            "Precision":        fmt_pct(avg_p  * 100),
            "Recall":           fmt_pct(avg_r  * 100),
            "F1 skóre":         fmt_pct(avg_f1 * 100),
        })

    # ── Averages row ─────────────────────────────────────────────────────────
    def safe_avg(field):
        vals = [
            float(r[field].replace(" %", ""))
            for r in rows
            if r[field] != "—"
        ]
        return fmt_pct(sum(vals) / len(vals)) if vals else "—"

    if len(rows) > 1:
        rows.append({
            "Doména":           "Priemer",
            "Vzorka (stránok)": sum(r["Vzorka (stránok)"] for r in rows),
            "Precision":        safe_avg("Precision"),
            "Recall":           safe_avg("Recall"),
            "F1 skóre":         safe_avg("F1 skóre"),
        })

    cur.close()
    return rows


# =============================================================================
# CATEGORY DISTRIBUTION (bonus)
# =============================================================================

def build_category_distribution(conn) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT j.start_url, c.name AS category, COUNT(DISTINCT sr.id) AS page_count
        FROM   scrape_results sr
        JOIN   jobs j                     ON j.id  = sr.job_id
        JOIN   scrape_result_categories s ON s.scrape_result_id = sr.id
        JOIN   categories c               ON c.id  = s.category_id
        WHERE  j.status IN ('completed', 'stopped')
        GROUP  BY j.start_url, c.name
        ORDER  BY j.start_url, page_count DESC
    """)
    rows = cur.fetchall()
    cur.close()
    return [
        {"Doména": extract_domain(r["start_url"]),
         "Kategória": r["category"],
         "Počet stránok": r["page_count"]}
        for r in rows
    ]


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WebScraper DB report — thesis tables"
    )
    parser.add_argument("--host",     default=None)
    parser.add_argument("--port",     default=None, type=int)
    parser.add_argument("--user",     default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--dbname",   default=None)
    parser.add_argument("--sample-per-domain", default=10,  type=int,
                        help="Top N URLs per domain used for Table 3 (default 10)")
    parser.add_argument("--min-words", default=50, type=int,
                        help="Min words for a block to count as 'rich' (default 50)")
    args = parser.parse_args()

    print("Connecting to database...")
    try:
        conn = get_connection(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    print("Connected.\n")

    # ── Table 1 ──────────────────────────────────────────────────────────────
    sep = "=" * 72
    print(sep)
    print("TABUĽKA 2  Výsledky testovania na reálnych webových stránkach")
    print(sep)
    t1 = build_table1(conn)
    if t1:
        print(tabulate(t1, headers="keys", tablefmt="github",
                       colalign=("left","right","right","right","right","left")))
    else:
        print("  (žiadne dokončené joby)")
    print()

    # ── Table 3 ──────────────────────────────────────────────────────────────
    print(sep)
    print("TABUĽKA 3  Kvalita extrakcie (automatická heuristika)")
    print(f"           Sample: top {args.sample_per_domain} URL/doménu | min_words={args.min_words}")
    print(sep)
    t3 = build_table3(conn,
                      sample_per_domain=args.sample_per_domain,
                      min_words=args.min_words)
    if t3:
        print(tabulate(t3, headers="keys", tablefmt="github",
                       colalign=("left","right","right","right","right")))
    else:
        print("  (žiadne výsledky na hodnotenie)")
    print()
    print("  METODIKA:")
    print("  Precision = bloky s >= min_words slov / všetky extrahované bloky")
    print("  Recall    = min(1.0,  extrahované slová / medián slov vzorky)")
    print("  F1        = 2 × P × R / (P + R)")
    print()

    # ── Category distribution ─────────────────────────────────────────────────
    print(sep)
    print("DISTRIBÚCIA KATEGÓRIÍ")
    print(sep)
    cats = build_category_distribution(conn)
    if cats:
        print(tabulate(cats, headers="keys", tablefmt="github"))
    else:
        print("  (žiadne kategórie — provider = none)")
    print()

    # ── Summary stats ─────────────────────────────────────────────────────────
    print(sep)
    print("SÚHRNNÉ ŠTATISTIKY DATABÁZY")
    print(sep)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            (SELECT COUNT(*)                           FROM jobs)                    AS total_jobs,
            (SELECT COUNT(*) FROM jobs WHERE status='completed')                    AS completed,
            (SELECT COUNT(*) FROM jobs WHERE status='failed')                       AS failed,
            (SELECT COUNT(*) FROM jobs WHERE status='stopped')                      AS stopped,
            (SELECT COALESCE(SUM(pages_scraped),0)     FROM jobs)                   AS total_scraped,
            (SELECT COALESCE(SUM(pages_failed),0)      FROM jobs)                   AS total_failed,
            (SELECT COUNT(*) FROM scrape_results WHERE error IS NULL)               AS results_ok,
            (SELECT COUNT(*) FROM scrape_results WHERE error IS NOT NULL)           AS results_err,
            (SELECT COUNT(*)                           FROM categories)             AS categories,
            (SELECT COUNT(*)                           FROM log_entries)            AS log_entries
    """)
    s = cur.fetchone()
    cur.close()
    conn.close()
    if s:
        print(tabulate([
            ["Celkový počet jobov",          s["total_jobs"]],
            ["  — dokončené",                s["completed"]],
            ["  — zlyhané",                  s["failed"]],
            ["  — zastavené",                s["stopped"]],
            ["Celkovo spracovaných stránok", s["total_scraped"]],
            ["Celkovo neúspešných stránok",  s["total_failed"]],
            ["Výsledky bez chyby",           s["results_ok"]],
            ["Výsledky s chybou",            s["results_err"]],
            ["Počet kategórií",              s["categories"]],
            ["Počet log záznamov",           s["log_entries"]],
        ], tablefmt="github"))
    print("\nHotovo.")


if __name__ == "__main__":
    main()
