-- Canonical JobPilot state. Idempotent on both fresh and existing PG volumes.
-- SQLite remains a read-only upstream import source until search is migrated.
CREATE TABLE IF NOT EXISTS search_profiles (
    id text PRIMARY KEY CHECK (id IN ('professional', 'assistant')),
    label text NOT NULL,
    headline text NOT NULL DEFAULT '',
    roles text[] NOT NULL DEFAULT '{}',
    search_terms text[] NOT NULL DEFAULT '{}',
    skills text[] NOT NULL DEFAULT '{}',
    summary text NOT NULL DEFAULT '',
    evidence text NOT NULL DEFAULT '',
    mode text NOT NULL DEFAULT 'both' CHECK (mode IN ('remote', 'hybrid', 'both')),
    languages text[] NOT NULL DEFAULT ARRAY['es','en']::text[],
    min_fit integer NOT NULL DEFAULT 80 CHECK (min_fit BETWEEN 0 AND 100),
    cv_original_name text,
    cv_sha256 text,
    cv_uploaded_at timestamptz,
    ai_provider text NOT NULL DEFAULT 'codex_chatgpt'
        CHECK (ai_provider IN ('codex_chatgpt','disabled')),
    ai_opt_in boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO search_profiles
    (id, label, headline, roles, search_terms, skills, mode, languages, min_fit)
VALUES
    ('professional', 'Professional', 'Diseño instruccional y aprendizaje',
     ARRAY['Instructional Designer','Learning Experience Designer',
           'Curriculum Developer','eLearning Developer',
           'Learning & Development Specialist','Training Specialist',
           'Diseñador instruccional','Analista de capacitación']::text[],
     ARRAY['instructional design','learning experience design','curriculum developer']::text[],
     ARRAY[]::text[], 'both', ARRAY['es','en']::text[], 80),
    ('assistant', 'Assistant', 'Asistencia virtual y contenidos educativos',
     ARRAY['Virtual Assistant','Administrative Assistant','Research Assistant',
           'Educational Content Writer','Asistente virtual',
           'Asistente administrativo','Redactor de contenidos educativos']::text[],
     ARRAY['virtual assistant','administrative assistant','educational content writer']::text[],
     ARRAY[]::text[], 'both', ARRAY['es','en']::text[], 70)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS jobs (
    url text PRIMARY KEY,
    company text NOT NULL,
    title text NOT NULL,
    location text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    source text NOT NULL DEFAULT '',
    posted_at text,
    upstream_passed boolean NOT NULL DEFAULT false,
    official_state text NOT NULL DEFAULT 'UNVERIFIED',
    last_imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profile_matches (
    job_url text NOT NULL REFERENCES jobs(url) ON DELETE CASCADE,
    profile_id text NOT NULL REFERENCES search_profiles(id),
    title_relevance integer NOT NULL DEFAULT 0
        CHECK (title_relevance BETWEEN 0 AND 100),
    decision text NOT NULL DEFAULT 'NOT_REVIEWED',
    reason text NOT NULL DEFAULT '',
    fit_score integer CHECK (fit_score IS NULL OR fit_score BETWEEN 0 AND 100),
    ai_summary text,
    ai_inferences jsonb NOT NULL DEFAULT '[]'::jsonb,
    ai_evaluated_at timestamptz,
    profile_revision timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_url, profile_id)
);

CREATE INDEX IF NOT EXISTS idx_profile_matches_by_profile
    ON profile_matches(profile_id, decision, title_relevance DESC);

-- Exactly one overall application record per official job URL, regardless
-- of which search profile discovered it.
CREATE TABLE IF NOT EXISTS application_history (
    job_url text PRIMARY KEY REFERENCES jobs(url) ON DELETE CASCADE,
    profile_id text REFERENCES search_profiles(id),
    status text NOT NULL DEFAULT 'saved'
        CHECK (status IN ('saved','applied_reported','interview',
                          'rejected','skipped','no_response')),
    notes text NOT NULL DEFAULT '',
    origin text NOT NULL DEFAULT 'manual',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id text REFERENCES search_profiles(id),
    kind text NOT NULL DEFAULT 'fetch' CHECK (kind IN ('fetch','reindex')),
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued','running','completed','failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    error_message text
);

-- Prevent two simultaneous/repeated searches racing or hitting ATS APIs.
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_search
    ON search_requests ((1)) WHERE state IN ('queued','running');

CREATE INDEX IF NOT EXISTS idx_jobs_last_imported
    ON jobs(last_imported_at DESC);

-- Four Remotive calls maximum in any rolling 24-hour window.
CREATE TABLE IF NOT EXISTS source_fetches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id text REFERENCES search_profiles(id),
    source text NOT NULL,
    search_term text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_fetches_window ON source_fetches(source,requested_at);

-- Only operational status, not auth tokens, is stored in PostgreSQL.
CREATE TABLE IF NOT EXISTS ai_runtime_status (
    provider text PRIMARY KEY CHECK (provider = 'codex_chatgpt'),
    state text NOT NULL DEFAULT 'login_required'
        CHECK (state IN ('connected','login_required','cli_unavailable',
                         'wrong_auth_method','quota_exhausted','error')),
    checked_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO ai_runtime_status(provider,state)
VALUES ('codex_chatgpt','login_required') ON CONFLICT (provider) DO NOTHING;

-- At most a configured number of invocations in any rolling 24h window.
-- Log attempts before calling Codex so crashes cannot silently double spend.
CREATE TABLE IF NOT EXISTS ai_evaluation_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_url text NOT NULL REFERENCES jobs(url),
    profile_id text NOT NULL REFERENCES search_profiles(id),
    invoked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_attempts_window ON ai_evaluation_attempts(invoked_at);

-- A short-lived Codex device authorization attempt, NOT an OAuth credential.
-- The one-time USER CODE is displayed only in the externally-protected
-- dashboard, never in logs, and deleted on completion/expiry.
CREATE TABLE IF NOT EXISTS codex_device_logins (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    state text NOT NULL DEFAULT 'queued' CHECK
        (state IN ('queued','starting','awaiting_user','connected','failed','expired')),
    verification_url text,
    user_code text,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '15 minutes',
    finished_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_codex_one_active_login
    ON codex_device_logins ((1))
    WHERE state IN ('queued','starting','awaiting_user');
CREATE INDEX IF NOT EXISTS idx_codex_device_login_recent
    ON codex_device_logins(created_at DESC);

-- The worker refreshes this timestamp so the UI can distinguish 'no jobs'
-- from 'the worker never started'.
CREATE TABLE IF NOT EXISTS worker_heartbeat (
    worker_id text PRIMARY KEY,
    checked_at timestamptz NOT NULL DEFAULT now(),
    state text NOT NULL DEFAULT 'starting'
);
