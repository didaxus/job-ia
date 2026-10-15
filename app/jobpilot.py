"""JobPilot ID starter: real employer checks and factual PDF preparation.

This is NOT a generic browser auto-apply agent. Only manually approved,
officially advertised email application routes can be auto-dispatched.
All other application links remain queued for a future audited ATS adapter.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
from pathlib import Path
import re
import shutil
import smtplib
import sqlite3
import subprocess
import sys
import time
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
import yaml

ROOT = Path(os.environ.get("JOBPILOT_ROOT", "/opt/job_search_tool"))
PRIVATE = Path(os.environ.get("JOBPILOT_PRIVATE_DIR", "/opt/jobpilot/private"))
CONFIG = Path(os.environ.get("JOBPILOT_CONFIG_DIR", "/opt/jobpilot/config"))
OUTPUT = Path(os.environ.get("JOBPILOT_OUTPUT_DIR", "/output"))
EXPORTER = Path(os.environ.get("JOBPILOT_EXPORTER", "/opt/job_hunt_skills/plugins/job-hunt-skills/scripts/export-documents.mjs"))
GREENHOUSE_HOSTS = {"job-boards.greenhouse.io", "boards.greenhouse.io"}
STOPWORDS = set("the and or with that from this have has are their your for its role will our about experience una las los que con del para por en de la el y".split())


def get_config(name: str, default=None):
    p = CONFIG / name
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().casefold())


def strip_markup(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html.unescape(s or ""))).strip()


def wordset(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z\u00c0-\u024f0-9]+", normalize(text)) if len(w) > 2 and w not in STOPWORDS}


def official_greenhouse_id(url: str, company: dict) -> str | None:
    """Exact domain, exact known board slug, numeric job ID: no redirects or fuzzy matches."""
    p = urlparse(url or "")
    if p.scheme != "https" or p.hostname not in GREENHOUSE_HOSTS or p.username or p.password:
        return None
    parts = p.path.strip("/").split("/")
    if len(parts) != 3 or parts[0].casefold() != company.get("slug", "").casefold() or parts[1] != "jobs":
        return None
    return parts[2] if parts[2].isdigit() else None


def geographic_eligibility(location: str, description: str) -> str:
    loc = normalize(location)
    text = normalize(strip_markup(description))
    # Disqualifying signals are prioritized over vague positive signals.
    blocks = [
        r"\bus[- ]remote\b", r"\bremote\s*[-(/,: ]+\s*(us|usa|united states|canada|uk|united kingdom)\b",
        r"\b(?:must|required to)\s+(?:be\s+)?(?:based|located|reside)\s+in\s+(?:the\s+)?(?:united states|usa|canada|uk|united kingdom)\b",
        r"\b(?:united states|us|canada|mexico|brazil|brasil|argentina|chile|peru|spain|india)\s+(?:residents|applicants)\s+only\b",
        r"\b(?:mexico|brazil|brasil|argentina|chile|peru|spain|india)\s+only\b",
        r"\b(?:not hiring in|not available in|exclude)\s+colombia\b",
    ]
    if any(re.search(rx, loc) or re.search(rx, text) for rx in blocks):
        return "RESTRICTED_OTHER_COUNTRY"
    positives = [r"\bcolombia\b", r"\bbogot[a\u00e1]\b", r"\blatam\b", r"\blatin america\b", r"\bworldwide\b", r"\banywhere\b", r"\bglobal remote\b"]
    if any(re.search(rx, loc) for rx in positives):
        # Bare city or country is insufficient: this person wants remote work,
        # or a role explicitly marked hybrid IN Bogota.
        if "onsite" in loc or "on-site" in loc:
            return "LOCATION_UNCLEAR"
        if "hybrid" in loc and re.search(r"\bbogot[a\u00e1]\b", loc):
            return "ELIGIBLE_LOCATION_SIGNAL"
        if "remote" in loc or "teletrabajo" in loc:
            return "ELIGIBLE_LOCATION_SIGNAL"
        if "worldwide" in loc or "anywhere" in loc or "global" in loc:
            return "ELIGIBLE_LOCATION_SIGNAL"
        return "LOCATION_UNCLEAR"
    # A 'remote' label without a listed hiring country proves nothing.
    return "LOCATION_UNCLEAR"


def suspicious_application_terms(description: str) -> bool:
    text = normalize(strip_markup(description))
    return bool(re.search(r"\b(?:application|registration|processing) fee\b|\bpay to apply\b|\bpay (?:us|for) (?:an? )?(?:application|registration)\b", text))


def get_live_ids(company: dict) -> set[str] | None:
    if company.get("ats") != "greenhouse":
        return None
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs"
        resp = httpx.get(url, params={"content": "false"}, timeout=22, follow_redirects=False)
        resp.raise_for_status()
        payload = resp.json()
        return {str(j["id"]) for j in payload.get("jobs", []) if j.get("id") is not None}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        print(f"[verify] ATS unavailable for {company.get('name')}: {type(exc).__name__}", flush=True)
        return None


def evaluate_job(job: dict, employers: dict[str, dict], active: dict[str, set[str] | None], minimum: int) -> tuple[str, dict | None]:
    company = employers.get(normalize(job.get("company", "")))
    if not company:
        return "COMPANY_NOT_VERIFIED", None
    if job.get("source") != "greenhouse" or company.get("ats") != "greenhouse":
        return "NEEDS_OFFICIAL_ATS_RECONCILIATION", company
    job_id = official_greenhouse_id(job.get("url", ""), company)
    if not job_id:
        return "UNTRUSTED_POSTING_URL", company
    known = active.get(company["slug"])
    if known is None:
        return "OFFICIAL_BOARD_UNAVAILABLE", company
    if job_id not in known:
        return "POSTING_NOT_LIVE", company
    if suspicious_application_terms(job.get("description", "")):
        return "SUSPICIOUS_PAYMENT_REQUIREMENT", company
    geo = geographic_eligibility(job.get("location", ""), job.get("description", ""))
    if geo != "ELIGIBLE_LOCATION_SIGNAL":
        return geo, company
    score = job.get("match_score")
    if score is None:
        return "AWAITING_FIT_SCORE", company
    if score < minimum:
        return "FIT_BELOW_THRESHOLD", company
    return "READY_TO_PREPARE", company


def validated_facts(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        facts = yaml.safe_load(f)
    if not isinstance(facts, dict):
        return None
    raw = str(facts)
    if "TODO" in raw or "[VERIFY" in raw or "[ASK" in raw:
        return None
    ident = facts.get("identity") or {}
    if not ident.get("name") or not ident.get("email") or "@" not in str(ident.get("email")) or not facts.get("experience") or not facts.get("summary"):
        return None
    for exp in facts["experience"]:
        if not all(exp.get(k) for k in ("title", "company", "dates", "highlights")):
            return None
    return facts


def relevant(bullets: list[str], description: str, limit: int = 4) -> list[str]:
    tokens = wordset(description)
    ranking = [(len(wordset(item) & tokens), ix, item) for ix, item in enumerate(bullets)]
    ranking.sort(key=lambda x: (-x[0], x[1]))
    return [x[2] for x in ranking[:limit]]


def markdown_docs(facts: dict, job: dict) -> tuple[str, str]:
    ident = facts["identity"]
    name = str(ident["name"]).strip()
    contact = " | ".join(str(ident.get(key, "")).strip() for key in ("email", "phone", "location", "linkedin", "portfolio") if ident.get(key))
    jd = strip_markup(job.get("description", ""))
    skills = relevant([str(x) for x in facts.get("skills", [])], jd, 14)
    lines = [f"# {name}", contact, "", "---", "", "## Professional Profile", str(facts["summary"]), "", "## Skills"]
    lines += [f"- {skill}" for skill in skills]
    lines += ["", "## Professional Experience"]
    chosen = []
    for entry in facts["experience"]:
        lines += ["", f"### {entry['title']}", f"{entry['company']} | {entry['dates']}"]
        bullets = relevant([str(x) for x in entry["highlights"]], jd, 4)
        chosen.extend(bullets[:2])
        lines += [f"- {item}" for item in bullets]
    lines += ["", "## Education"]
    lines += [f"- {item}" for item in facts.get("education", [])]
    resume = "\n".join(lines).strip() + "\n"
    company = job["company"]
    title = job["title"]
    cover = [f"# {name}", contact, "", "---", "", f"Dear {company} hiring team,", "",
             f"I am applying for the {title} position. My background includes: ", ""]
    cover += [f"- {item}" for item in chosen[:3]]
    cover += ["", "I would welcome the opportunity to discuss how this documented experience could support your team.", "", "Sincerely,", name]
    return resume, "\n".join(cover).strip() + "\n"


def safe_slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")[:48] or "job")


def build_documents(facts: dict, job: dict) -> tuple[Path, Path]:
    job_key = hashlib.sha256((job["url"] + facts["identity"]["email"]).encode()).hexdigest()[:12]
    folder = OUTPUT / f"{safe_slug(job['company'])}-{safe_slug(job['title'])}-{job_key}"
    folder.mkdir(parents=True, exist_ok=True)
    resume, cover = markdown_docs(facts, job)
    paths = (folder / "resume.md", folder / "coverletter.md")
    paths[0].write_text(resume, encoding="utf-8")
    paths[1].write_text(cover, encoding="utf-8")
    subprocess.run(["node", str(EXPORTER), str(paths[0]), str(paths[1])], check=True, timeout=90, stdout=subprocess.DEVNULL)
    pdfs = (folder / "resume.pdf", folder / "coverletter.pdf")
    if not all(p.is_file() and p.stat().st_size > 100 for p in pdfs):
        raise RuntimeError("Exporter did not create expected PDF files")
    return pdfs


def state_db():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OUTPUT / "submission_state.sqlite3")
    conn.execute("CREATE TABLE IF NOT EXISTS sends (job_url TEXT PRIMARY KEY, recipient TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    return conn


def send_approved_email(job: dict, company: dict, pdfs: tuple[Path, Path], facts: dict, routes: list[dict]) -> str:
    route = next((r for r in routes if r.get("job_url") == job["url"] and r.get("approved_by_user") is True), None)
    if not route:
        return "QUEUED_FOR_VERIFIED_BROWSER_ADAPTER"
    if os.environ.get("AUTO_EMAIL", "false").lower() != "true":
        return "EMAIL_ROUTE_APPROVED_SEND_DISABLED"
    recipient = str(route.get("recipient", ""))
    domain = recipient.rsplit("@", 1)[-1].lower()
    proof = urlparse(str(route.get("proof_url", "")))
    official_domain = company.get("company_domain", "").lower()
    if domain != official_domain or proof.scheme != "https" or not (proof.hostname == official_domain or (proof.hostname or "").endswith("." + official_domain)):
        return "EMAIL_ROUTE_NOT_TRUSTED"
    sender = os.environ.get("SMTP_FROM", "")
    host = os.environ.get("SMTP_HOST", "")
    if not sender or not host or not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASSWORD"):
        return "EMAIL_CONFIGURATION_REQUIRED"
    # No automatic retry after an unknown SMTP result: avoids duplicate sends.
    with state_db() as conn:
        old = conn.execute("SELECT state FROM sends WHERE job_url=?", (job["url"],)).fetchone()
        if old:
            return f"PREVIOUS_EMAIL_{old[0]}"
        conn.execute("INSERT INTO sends (job_url, recipient, state) VALUES (?, ?, 'SENDING')", (job["url"], recipient))
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"Application: {job['title']} - {facts['identity']['name']}"
    message.set_content(f"Hello {company['name']} hiring team,\n\nPlease find attached my resume and cover letter for the position {job['title']}.\n\nBest regards,\n{facts['identity']['name']}")
    for path in pdfs:
        message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    state = "OUTCOME_UNKNOWN"
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=25) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            refusals = smtp.send_message(message)
            if refusals:
                state = "OUTCOME_UNKNOWN"
            else:
                state = "SMTP_ACCEPTED_UNCONFIRMED"
    except Exception as exc:
        print(f"[smtp] outcome unknown for {job['url']}: {type(exc).__name__}", flush=True)
    with state_db() as conn:
        conn.execute("UPDATE sends SET state=?, updated_at=CURRENT_TIMESTAMP WHERE job_url=?", (state, job["url"]))
    return state


def collect_candidates() -> list[dict]:
    db = ROOT / "data/seen_jobs.sqlite3"
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT jd.url, jd.company, jd.title, jd.location, jd.description, jd.source, ae.match_score FROM job_details jd LEFT JOIN ai_evaluations ae ON jd.url=ae.url WHERE jd.passed_filters=1 ORDER BY jd.fetched_at DESC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def run_search():
    subprocess.run([sys.executable, "-m", "app.main", "--skip-discovery"], cwd=ROOT, check=True, timeout=360)
    profile = PRIVATE / "profile.yaml"
    if profile.is_file() and "TODO" not in profile.read_text(encoding="utf-8") and os.environ.get("ANTHROPIC_API_KEY"):
        shutil.copyfile(profile, ROOT / "profile.yaml")
        size = max(1, min(int(os.environ.get("MAX_AI_EVALUATIONS", "20")), 100))
        subprocess.run([sys.executable, "-m", "app.ai_evaluate", "--limit", str(size)], cwd=ROOT, check=True, timeout=360)
    else:
        print("[scoring] skipped: verified profile.yaml and ANTHROPIC_API_KEY required", flush=True)


def scan_and_prepare():
    registry = get_config("employers.yaml", {"employers": []})["employers"]
    employers = {normalize(e["name"]): e for e in registry}
    active = {e["slug"]: get_live_ids(e) for e in registry if e.get("ats") == "greenhouse"}
    routes = get_config("approved_email_routes.yaml", {"routes": []})["routes"]
    facts = validated_facts(PRIVATE / "facts.yaml")
    min_score = int(os.environ.get("FIT_MIN", "80"))
    if not 0 <= min_score <= 100:
        raise ValueError("FIT_MIN must be in 0..100")
    rows = []
    for job in collect_candidates():
        state, company = evaluate_job(job, employers, active, min_score)
        pdf_resume = ""
        if state in ("READY_TO_PREPARE", "AWAITING_FIT_SCORE"):
            if not facts:
                state = "MISSING_VERIFIED_FACTS" if state == "READY_TO_PREPARE" else "AWAITING_FIT_SCORE_AND_FACTS"
            else:
                try:
                    pdfs = build_documents(facts, job)
                    pdf_resume = str(pdfs[0])
                    state = (send_approved_email(job, company, pdfs, facts, routes) if state == "READY_TO_PREPARE"
                             else "PREPARED_AWAITING_FIT_SCORE")
                except Exception as exc:
                    print(f"[prepare] error at {job['url']}: {type(exc).__name__}: {exc}", flush=True)
                    state = "DOCUMENT_EXPORT_ERROR"
        rows.append({"company": job.get("company", ""), "title": job.get("title", ""), "location": job.get("location", ""), "score": job.get("match_score", ""), "url": job["url"], "status": state, "resume_pdf": pdf_resume})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "queue.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "title", "location", "score", "url", "status", "resume_pdf"])
        writer.writeheader()
        writer.writerows(rows)
    tally = {}
    for row in rows:
        tally[row["status"]] = tally.get(row["status"], 0) + 1
    print(f"[report] {len(rows)} postings screened, {tally}; results at {path}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--loop", action="store_true")
    args = p.parse_args()
    if args.loop and args.once:
        p.error("choose one of --once and --loop")
    while True:
        try:
            if not args.prepare_only:
                run_search()
            scan_and_prepare()
        except Exception as exc:
            print(f"[pipeline] cycle failed: {type(exc).__name__}: {exc}", flush=True)
            if args.once or args.prepare_only:
                raise
        if not args.loop:
            break
        hours = max(6, int(os.environ.get("SCAN_EVERY_HOURS", "24")))
        print(f"[scheduler] next scan in {hours} hours", flush=True)
        time.sleep(hours * 3600)


if __name__ == "__main__":
    main()
