"""Dual-profile JobPilot: SQLite discovery staging -> canonical PostgreSQL.

Does not submit applications. Scoring only uses evidence explicitly supplied
by the candidate, and only after opting in to external AI evaluation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata

from jobpilot import geographic_eligibility, get_live_ids, get_config, normalize, official_greenhouse_id, suspicious_application_terms

SOURCE_DB = Path(os.getenv("LEGACY_SQLITE_PATH", "/opt/job_search_tool/data/seen_jobs.sqlite3"))
ROOT = Path(os.getenv("JOBPILOT_ROOT", "/opt/job_search_tool"))
SCHEMA = Path(os.getenv("JOBPILOT_SCHEMA", "/opt/jobpilot/db/schema.sql"))
sys.path.insert(0, str(ROOT))  # upstream app package for optional per-profile AI
RECHECK_SECONDS = 15

EXCLUDE = ("sales", "call center", "telemarketing", "commission", "appointment setter",
           "recruiter", "warehouse", "vendedor", "ventas", "comercial")


def pg_connect():
    import psycopg
    pwd = os.getenv("PGPASSWORD", "")
    if not pwd:
        raise RuntimeError("PGPASSWORD is required; no silent fallback database")
    return psycopg.connect(
        host=os.getenv("PGHOST", "postgres"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "jobpilot"),
        user=os.getenv("PGUSER", "jobpilot"),
        password=pwd,
        connect_timeout=10,
    )


def initialize():
    with pg_connect() as db:
        db.execute(SCHEMA.read_text(encoding="utf-8"))
        db.commit()


def tokens(text):
    simple = unicodedata.normalize("NFKD", text.casefold())
    simple = "".join(c for c in simple if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", simple)
    common = {"and", "the", "for", "de", "del", "la", "los", "para", "of", "en", "y"}
    return {stem(w) for w in words if w not in common and len(w) > 2}


def stem(word):
    # Small cross-language normalization for job titles, not an NLP fit claim.
    for ending in ("ional", "ation", "ment", "ing", "ers", "er", "or", "es", "s"):
        if word.endswith(ending) and len(word) - len(ending) >= 5:
            return word[:-len(ending)]
    return word


def topic_relevance(title, roles):
    t = tokens(title or "")
    if any(word in t for word in {"sales", "telemarket", "recruit", "warehouse", "vendedor", "ventas"}):
        return 0
    if any(ex in (title or "").casefold() for ex in EXCLUDE):
        return 0
    score = 0
    for role in roles:
        r = tokens(role)
        if not r or not t:
            continue
        shared = len(r & t)
        if shared == len(r):
            score = max(score, 95)
        elif shared >= 2 and shared / len(r) >= 0.6:
            score = max(score, 70)
        elif len(r) == 1 and shared == 1:
            score = max(score, 60)
    return score


def classify(job, profile, official_state):
    rel = topic_relevance(job["title"], profile["roles"])
    if rel == 0:
        return 0, "TITLE_NOT_RELEVANT", "Título ajeno a las funciones seleccionadas"
    geo = geographic_eligibility(job["location"], job["description"])
    if geo == "RESTRICTED_OTHER_COUNTRY":
        return rel, "RESTRICTED_LOCATION", "Restricción geográfica incompatible con Colombia"
    if geo != "ELIGIBLE_LOCATION_SIGNAL":
        return rel, "LOCATION_UNVERIFIED", "La oferta no confirma contratación desde Colombia"
    loc = normalize(job["location"])
    is_hybrid = "hybrid" in loc or "híbrido" in loc or "hibrido" in loc
    if is_hybrid and profile["mode"] == "remote":
        return rel, "MODE_MISMATCH", "Este perfil solicita solo remoto"
    if not is_hybrid and profile["mode"] == "hybrid":
        return rel, "MODE_MISMATCH", "Este perfil solicita solo híbrido en Bogotá"
    if is_hybrid and not ("bogot" in loc):
        return rel, "LOCATION_UNVERIFIED", "Híbrido fuera de Bogotá o ciudad no confirmada"
    if suspicious_application_terms(job["description"]):
        return rel, "PAYMENT_WARNING", "La oferta menciona un posible pago para aplicar"
    if official_state != "VERIFIED":
        return rel, "EMPLOYER_REVIEW_REQUIRED", "Verificar empresa, portal oficial y vacante activa"
    if not profile["summary"] or not profile["evidence"]:
        return rel, "AWAITING_VERIFIED_EVIDENCE", "Completar experiencia comprobable para evaluar ajuste real"
    return rel, "READY_FOR_FIT_REVIEW", "Coincidencia temática, pendiente de evaluar competencias"


def read_legacy_jobs():
    if not SOURCE_DB.is_file():
        print("[import] SQLite not present yet; no destructive initialization", flush=True)
        return []
    conn = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT jd.url, jd.company, jd.title, jd.location, jd.description,
                   jd.source, jd.posted_at, jd.passed_filters,
                   us.my_status, us.notes
            FROM job_details jd LEFT JOIN user_status us ON us.url=jd.url
            WHERE jd.url IS NOT NULL AND jd.url != ''
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_profiles(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, roles, search_terms, mode, languages, min_fit, summary, evidence,
                   ai_opt_in, updated_at, skills
            FROM search_profiles ORDER BY id
        """)
        keys = [x.name for x in cur.description]
        return [dict(zip(keys, row)) for row in cur.fetchall()]


def official_boards():
    registry = get_config("employers.yaml", {"employers": []})["employers"]
    active = {e["slug"]: get_live_ids(e) for e in registry if e.get("ats") == "greenhouse"}
    return registry, active


def official_state_for(job, registry, active):
    if job.get("source") != "greenhouse":
        return "UNVERIFIED"
    for company in registry:
        if normalize(company["name"]) == normalize(job["company"]):
            jid = official_greenhouse_id(job["url"], company)
            if jid is None:
                return "UNVERIFIED"
            known = active.get(company["slug"])
            return "ATS_UNAVAILABLE" if known is None else "VERIFIED" if jid in known else "NOT_LIVE"
    return "UNVERIFIED"


LEGACY_STATUSES = {
    "applied": "applied_reported",
    "interview": "interview",
    "rejected": "rejected",
    "skipped": "skipped",
    "silence": "no_response",
}


def sync_once():
    jobs = read_legacy_jobs()
    if not jobs:
        print("[import] Nothing to import yet", flush=True)
        return 0
    registry, active = official_boards()
    with pg_connect() as db:
        profiles = get_profiles(db)
        with db.cursor() as cur:
            for job in jobs:
                official = official_state_for(job, registry, active)
                cur.execute("""
                    INSERT INTO jobs
                        (url,company,title,location,description,source,posted_at,
                         upstream_passed,official_state)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO UPDATE SET
                        company=excluded.company, title=excluded.title,
                        location=excluded.location, description=excluded.description,
                        source=excluded.source, posted_at=excluded.posted_at,
                        upstream_passed=excluded.upstream_passed,
                        official_state=excluded.official_state,
                        last_imported_at=now()
                """, (
                    job["url"], job["company"] or "", job["title"] or "",
                    job["location"] or "", job["description"] or "",
                    job["source"] or "", str(job["posted_at"] or ""),
                    bool(job["passed_filters"]), official,
                ))
                prior = LEGACY_STATUSES.get(job.get("my_status"))
                if prior:
                    cur.execute("""
                        INSERT INTO application_history
                            (job_url,profile_id,status,notes,origin)
                        VALUES (%s,NULL,%s,%s,'legacy_sqlite_unverified')
                        ON CONFLICT (job_url) DO NOTHING
                    """, (job["url"], prior, str(job.get("notes") or "")[:4000]))
                for profile in profiles:
                    relevance, decision, reason = classify(job, profile, official)
                    cur.execute("""
                        INSERT INTO profile_matches
                            (job_url,profile_id,title_relevance,decision,reason,profile_revision)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (job_url,profile_id) DO UPDATE SET
                            title_relevance=excluded.title_relevance,
                            decision=CASE
                                WHEN profile_matches.profile_revision=excluded.profile_revision
                                AND profile_matches.fit_score IS NOT NULL
                                AND excluded.decision='READY_FOR_FIT_REVIEW'
                                THEN profile_matches.decision
                                ELSE excluded.decision END,
                            reason=excluded.reason,
                            fit_score=CASE
                                WHEN profile_matches.profile_revision=excluded.profile_revision
                                AND excluded.decision='READY_FOR_FIT_REVIEW'
                                THEN profile_matches.fit_score ELSE NULL END,
                            ai_summary=CASE
                                WHEN profile_matches.profile_revision=excluded.profile_revision
                                AND excluded.decision='READY_FOR_FIT_REVIEW'
                                THEN profile_matches.ai_summary ELSE NULL END,
                            ai_evaluated_at=CASE
                                WHEN profile_matches.profile_revision=excluded.profile_revision
                                AND excluded.decision='READY_FOR_FIT_REVIEW'
                                THEN profile_matches.ai_evaluated_at ELSE NULL END,
                            profile_revision=excluded.profile_revision,
                            updated_at=now()
                    """, (job["url"], profile["id"], relevance,
                          decision, reason, profile["updated_at"]))
        db.commit()
    print(f"[import] {len(jobs)} legacy postings indexed against both search profiles", flush=True)
    return len(jobs)


def run_search():
    """Two targeted Remotive queries, plus all configured company boards.

    User-edited profile search terms determine queries, while all results are
    stored in legacy SQLite (even when original broad filters reject them).
    Enforces at most 4 Remotive API requests per rolling 24 hours.
    """
    print("[search] Fetching curated ATS boards; no forms submitted", flush=True)
    subprocess.run([sys.executable, "-m", "app.main", "--skip-aggregators",
                    "--skip-discovery"], cwd=ROOT, check=True, timeout=420)
    from app.aggregator_clients import fetch_remotive
    from app import dedup, filters
    with pg_connect() as db:
        profiles = get_profiles(db)
    for profile in profiles:
        terms = [t.strip() for t in profile["search_terms"] if t.strip()]
        if not terms:
            continue
        with pg_connect() as db:
            with db.cursor() as cur:
                cur.execute("""
                    SELECT count(*) FROM source_fetches
                    WHERE source='remotive' AND requested_at>now()-interval '24 hours'
                """)
                if cur.fetchone()[0] >= 4:
                    print("[remotive] 4 requests/24h reached; skipping to respect rate policy", flush=True)
                    continue
                cur.execute("SELECT count(*) FROM source_fetches WHERE profile_id=%s",
                            (profile["id"],))
                index = cur.fetchone()[0] % len(terms)
                term = terms[index]
                cur.execute("""
                    INSERT INTO source_fetches(profile_id,source,search_term)
                    VALUES (%s,'remotive',%s)
                """, (profile["id"], term))
            db.commit()
        try:
            jobs = fetch_remotive({"search": term})
            new = 0
            with dedup.connect() as sqlite:
                for job in jobs:
                    job["source"] = "remotive"
                    if not dedup.is_new(sqlite, job):
                        continue
                    dedup.mark_seen(sqlite, job)
                    dedup.save_details(sqlite, job, filters.passes_filters(job))
                    new += 1
            print(f"[remotive] {profile['id']}: query={term!r}, fetched={len(jobs)}, new={new}",
                  flush=True)
        except Exception as exc:
            print(f"[remotive] {profile['id']}: {type(exc).__name__} (kept ATS results)",
                  flush=True)


def run_ai(max_count):
    if not os.getenv("ANTHROPIC_API_KEY"):
        return
    with pg_connect() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT pm.job_url,pm.profile_id,p.summary,p.evidence,p.skills,
                       p.roles,p.min_fit,p.updated_at,
                       j.company,j.title,j.location,j.description
                FROM profile_matches pm
                JOIN search_profiles p ON p.id=pm.profile_id
                JOIN jobs j ON j.url=pm.job_url
                WHERE p.ai_opt_in=TRUE AND pm.decision='READY_FOR_FIT_REVIEW'
                  AND pm.fit_score IS NULL
                ORDER BY pm.title_relevance DESC, j.last_imported_at DESC
                LIMIT %s
            """, (max_count,))
            rows = cur.fetchall()
        if not rows:
            return
        from app.ai_evaluate import evaluate_one, MODEL
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        for (url, pid, summary, evidence, skills, roles, minimum, revision,
             company, title, location, description) in rows:
            profile = {"summary": summary, "verified_experience_evidence": evidence,
                       "skills": skills, "target_roles": roles, "id": pid}
            job = {"url": url, "company": company, "title": title,
                   "location": location, "description": description}
            try:
                result = evaluate_one(client, profile, job)
                score = int(result["match_score"])
                if not 0 <= score <= 100:
                    raise ValueError("Invalid score")
                decision = "FIT_BELOW_THRESHOLD" if score < minimum else "FIT_REVIEW_REQUIRED"
                details = " | ".join(str(result.get(k, ""))[:1000]
                    for k in ("transferable_strengths", "genuine_gaps", "risk_factors"))
                with db.cursor() as cur:
                    cur.execute("""
                        UPDATE profile_matches SET fit_score=%s,
                            ai_summary=%s, decision=%s, ai_evaluated_at=now()
                        WHERE job_url=%s AND profile_id=%s
                          AND profile_revision=%s
                          AND decision='READY_FOR_FIT_REVIEW'
                    """, (score, details, decision, url, pid, revision))
                db.commit()
                print(f"[AI] {pid}: {score}/100, {title}; advisory only, no submission", flush=True)
            except Exception as exc:
                db.rollback()
                print(f"[AI] {pid}: evaluation failed {type(exc).__name__}", flush=True)


def claim_search():
    with pg_connect() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT id,kind FROM search_requests WHERE state='queued'
                ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE search_requests SET state='running',started_at=now() WHERE id=%s",
                        (row[0],))
        db.commit()
        return row


def finish_search(search_id, error=None):
    with pg_connect() as db:
        db.execute("""
            UPDATE search_requests SET state=%s,finished_at=now(),error_message=%s
            WHERE id=%s
        """, ("failed" if error else "completed", str(error)[:300] if error else None,
              search_id))
        db.commit()


def enqueue_periodic_if_due():
    hours = max(6, int(os.getenv("SCAN_EVERY_HOURS", "24")))
    with pg_connect() as db:
        db.execute("""
            INSERT INTO search_requests(kind,state)
            SELECT 'fetch','queued'
            WHERE NOT EXISTS (SELECT 1 FROM search_requests
                              WHERE state IN ('queued','running'))
              AND NOT EXISTS (
                  SELECT 1 FROM search_requests
                  WHERE kind='fetch' AND created_at>now()-(%s * interval '1 hour')
              )
            ON CONFLICT DO NOTHING
        """, (hours,))
        db.commit()


def run_worker(one_cycle=False):
    initialize()
    sync_once()
    if one_cycle:
        return
    last_profile_revision = None
    last_reindex = time.monotonic()
    while True:
        try:
            enqueue_periodic_if_due()
            task = claim_search()
            if task:
                search_id, kind = task
                try:
                    if kind == "fetch":
                        run_search()
                    sync_once()
                    if kind == "fetch":
                        run_ai(max(1, min(20, int(os.getenv("MAX_AI_EVALUATIONS", "20")))))
                    finish_search(search_id)
                except Exception as exc:
                    finish_search(search_id, exc)
                    print(f"[search] failed ({search_id}): {type(exc).__name__}: {exc}", flush=True)
            else:
                with pg_connect() as db:
                    profiles = get_profiles(db)
                revision = tuple((p["id"], p["updated_at"]) for p in profiles)
                if revision != last_profile_revision:
                    if last_profile_revision is not None:
                        sync_once()
                        run_ai(max(1, min(20, int(os.getenv("MAX_AI_EVALUATIONS", "20")))))
                    last_profile_revision = revision
                    last_reindex = time.monotonic()
                elif time.monotonic() - last_reindex > 3600:
                    sync_once()  # recover any prior SQLite writes without deleting data
                    last_reindex = time.monotonic()
        except Exception as exc:
            print(f"[worker] {type(exc).__name__}: {exc}", flush=True)
        time.sleep(RECHECK_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Import SQLite only; no search")
    args = parser.parse_args()
    run_worker(one_cycle=args.once)
