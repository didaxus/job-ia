"use client";

import { useEffect, useMemo, useState } from "react";

type ProfileId = "professional" | "assistant";
type View = "all" | ProfileId;
type Profile = {
  id: ProfileId; label: string; headline: string; roles: string[]; search_terms: string[]; skills: string[];
  summary: string; evidence: string; mode: "remote" | "hybrid" | "both";
  languages: string[]; min_fit: number; ai_provider: "codex_chatgpt" | "disabled"; ai_opt_in: boolean;
  cv_original_name: string | null; cv_uploaded_at: string | null;
};
type Job = {
  url: string; company: string; title: string; location: string; description: string;
  source: string; official_state: string; profile_id: ProfileId; profile_label: string;
  title_relevance: number; decision: string; reason: string;
  fit_score: number | null; ai_summary: string | null;
  ai_inferences: {required_skill:string; relation:"direct"|"inferred"|"unsupported";evidence_text:string;rationale:string}[];
  application_status: string | null; application_notes: string | null;
  application_origin: string | null;
};
type AiRuntime = {provider:string;state:string;checked_at:string|null};
type DeviceLogin = {
  id: string | null; state: string; effective_state: string;
  verification_url: string | null; user_code: string | null;
  expires_at: string | null; error_code: string | null;
};
type SystemStatus = {
  database: string; worker: string; jobs: number | null;
  profiles?: number; matches?: number; message: string;
};
type Search = {
  id: number; profile_id: ProfileId | null; state: string;
  created_at: string; error_message: string | null;
};
const statuses = [
  ["saved", "Guardada (no enviada)"],
  ["applied_reported", "Postulación registrada manualmente"],
  ["interview", "Entrevista"],
  ["rejected", "Rechazada"],
  ["no_response", "Sin respuesta"],
  ["skipped", "Descartada"],
];

async function requestJson(url: string, options?: RequestInit) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.message || ("HTTP " + response.status));
  return data;
}

export default function Page() {
  const [view, setView] = useState<View>("all");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<Search[]>([]);
  const [aiRuntime, setAiRuntime] = useState<AiRuntime | null>(null);
  const [device, setDevice] = useState<DeviceLogin | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [showRejected, setShowRejected] = useState(false);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Profile | null>(null);
  const [selected, setSelected] = useState<Job | null>(null);
  const [applicationStatus, setApplicationStatus] = useState("saved");
  const [applicationNotes, setApplicationNotes] = useState("");
  const [upload, setUpload] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh(selectedView: View = view, rejected: boolean = showRejected) {
    // Do not suppress the entire dashboard if only one endpoint fails.
    // This is essential for diagnosing PostgreSQL/worker start-up failures.
    const sources = [
      ["Perfiles", "/api/profiles"],
      ["Vacantes", "/api/jobs?profile=" + selectedView + "&rejected=" + rejected],
      ["Historial", "/api/search"],
      ["Codex", "/api/ai/status"],
      ["Vinculación", "/api/ai/connect"],
      ["Sistema", "/api/system/status"],
    ];
    const settled = await Promise.allSettled(sources.map(([, url]) => requestJson(url)));
    if (settled[0].status === "fulfilled") setProfiles(settled[0].value);
    if (settled[1].status === "fulfilled") setJobs(settled[1].value);
    if (settled[2].status === "fulfilled") setRuns(settled[2].value);
    if (settled[3].status === "fulfilled") setAiRuntime(settled[3].value);
    if (settled[4].status === "fulfilled") setDevice(settled[4].value);
    if (settled[5].status === "fulfilled") setSystemStatus(settled[5].value);
    if (settled[5].status === "rejected") {
      setSystemStatus({ database: "unavailable", worker: "unknown",
                        jobs: null, message: "No se pudo consultar PostgreSQL" });
    }
    const failures = settled.flatMap((result, i) =>
      result.status === "rejected"
        ? [sources[i][0] + ": " + (result.reason as Error).message]
        : []
    );
    setError(failures.join(" | "));
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh(view, showRejected);
    const poll = window.setInterval(() => refresh(view, showRejected), 15000);
    return () => window.clearInterval(poll);
  }, [view, showRejected]);

  useEffect(() => {
    // Device authorization runs in the worker. Poll only the short-lived
    // code and operational status, not the whole jobs list, every 3 seconds.
    const poll = window.setInterval(async () => {
      if (!device || !["queued", "starting", "awaiting_user"].includes(device.effective_state)) return;
      const [next, ai] = await Promise.allSettled([
        requestJson("/api/ai/connect"),
        requestJson("/api/ai/status"),
      ]);
      if (next.status === "fulfilled") setDevice(next.value);
      if (ai.status === "fulfilled") setAiRuntime(ai.value);
    }, 3000);
    return () => window.clearInterval(poll);
  }, [device]);

  const activeProfile = profiles.find(p => p.id === view);
  const visible = useMemo(() => jobs.filter(j => {
    if (!query.trim()) return true;
    const searchable = (j.company + " " + j.title + " " + j.location).toLocaleLowerCase();
    return searchable.includes(query.toLocaleLowerCase());
  }), [jobs, query]);
  const uniqueJobs = new Set(visible.map(j => j.url)).size;
  const latest = runs[0];

  function startEdit(p: Profile) {
    setDraft({ ...p, roles: [...p.roles], search_terms: [...p.search_terms], skills: [...p.skills], languages: [...p.languages] });
    setEditing(true);
    setUpload(null);
    setNotice("");
    setError("");
  }
  function patch<K extends keyof Profile>(key: K, value: Profile[K]) {
    if (draft) setDraft({ ...draft, [key]: value });
  }
  async function saveProfile() {
    if (!draft) return;
    setBusy(true); setNotice(""); setError("");
    try {
      await requestJson("/api/profiles", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      setNotice("Preferencias guardadas en PostgreSQL. Las coincidencias se recalcularán automáticamente.");
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function uploadCv() {
    if (!draft || !upload) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const form = new FormData();
      form.set("profile_id", draft.id);
      form.set("file", upload);
      const result = await requestJson("/api/cv", { method: "POST", body: form });
      setNotice("CV PDF privado guardado para " + draft.label + ": " + result.filename);
      setUpload(null);
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function connectCodex() {
    setBusy(true); setError(""); setNotice("");
    try {
      await requestJson("/api/ai/connect", { method: "POST" });
      setNotice("Vinculación solicitada. Espera el código y abre el enlace oficial de OpenAI.");
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function searchNow() {
    setBusy(true); setError(""); setNotice("");
    try {
      await requestJson("/api/search", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: view === "all" ? null : view }),
      });
      setNotice("Búsqueda solicitada. El worker consultará las fuentes y actualizará ambos perfiles.");
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function openJob(j: Job) {
    setSelected(j);
    setApplicationStatus(j.application_status || "saved");
    setApplicationNotes(j.application_notes || "");
    setNotice("");
  }
  async function saveApplication() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await requestJson("/api/applications", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: selected.url, profile_id: selected.profile_id,
          status: applicationStatus, notes: applicationNotes,
        }),
      });
      setNotice("Estado registrado manualmente en el historial único. No se ha enviado ninguna postulación.");
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <>
      <header className="jp-header">
        <div>
          <p className="jp-eyebrow">JOBPILOT ID</p>
          <h1>Búsqueda laboral personalizada</h1>
          <p className="jp-muted">Dos perfiles, dos CV y un historial único. No envía candidaturas automáticamente.</p>
        </div>
        <button className="jp-primary" type="button" disabled={busy || systemStatus?.worker !== "active"} onClick={searchNow}>Buscar ahora</button>
      </header>
      <main className="jp-main">
        <nav className="jp-tabs" aria-label="Perfiles laborales">
          {(["all", "professional", "assistant"] as View[]).map(item => (
            <button key={item} type="button" className={view === item ? "jp-tab selected" : "jp-tab"}
              aria-current={view === item ? "page" : undefined}
              onClick={() => { setView(item); setEditing(false); setSelected(null); }}>
              {item === "all" ? "Todos" : item === "professional" ? "Professional · Educación y L&D" : "Assistant · Apoyo remoto"}
            </button>
          ))}
        </nav>
        {systemStatus && (
          <section className="jp-panel jp-system">
            <div>
              <strong>Estado del sistema</strong>
              <p className="jp-muted">
                PostgreSQL: {systemStatus.database === "ready" ? "conectado" :
                  systemStatus.database === "schema_missing" ? "esperando migración" : "sin conexión"} ·
                Worker: {systemStatus.worker === "active" ? "activo" : "sin actividad reciente"} ·
                Ofertas almacenadas: {systemStatus.jobs === null ? "desconocido" : systemStatus.jobs}
              </p>
            </div>
            {systemStatus.database !== "ready" && (
              <p className="jp-muted">
                El panel todavía no puede consultar datos. Verifica en Coolify los servicios
                postgres y schema; no borres SQLite ni los volúmenes.
              </p>
            )}
            {systemStatus.database === "ready" && systemStatus.worker !== "active" && (
              <p className="jp-muted">
                PostgreSQL está listo pero el worker no informa actividad.
                Revisa los logs del servicio pipeline en Coolify.
              </p>
            )}
          </section>
        )}
        <section className="jp-panel jp-onboarding">
          <div className="jp-onboarding-header">
            <div>
              <p className="jp-eyebrow">PROVEEDOR IA · SIN API KEY</p>
              <h2>Conecta Codex con tu cuenta ChatGPT</h2>
              <p className="jp-muted">
                Utiliza la cuota Codex de tu plan. No escribas aquí contraseñas ni tokens.
              </p>
            </div>
            <button type="button" className="jp-primary" disabled={busy ||
                systemStatus?.worker !== "active" ||
                ["queued", "starting", "awaiting_user"].includes(device?.effective_state || "") ||
                (aiRuntime?.state === "connected" || device?.effective_state === "connected")}
              onClick={connectCodex}>Conectar ChatGPT</button>
          </div>
          <p className="jp-muted">
            Estado: <strong>{(aiRuntime?.state === "connected" || device?.effective_state === "connected") ? "Conectado con ChatGPT" :
              device?.effective_state === "queued" ? "Solicitud en espera del worker" :
              device?.effective_state === "starting" ? "Preparando código de dispositivo" :
              device?.effective_state === "awaiting_user" ? "Esperando autorización en OpenAI" :
              device?.effective_state === "failed" ? "No se completó la autorización" :
              device?.effective_state === "expired" ? "El código expiró; puedes solicitar otro" :
              systemStatus?.worker !== "active" ? "Worker sin actividad" : "Pendiente de conexión"}</strong>
          </p>
          {device?.effective_state === "awaiting_user" && device.user_code && (
            <div className="jp-device-flow">
              <p><strong>1.</strong> Abre la página oficial de autorización:</p>
              <a href="https://auth.openai.com/codex/device" target="_blank"
                 rel="noopener noreferrer" className="jp-link">
                Abrir autorización oficial de OpenAI ↗
              </a>
              <p><strong>2.</strong> Introduce este código temporal en esa página:</p>
              <code className="jp-device-code">{device.user_code}</code>
              <p className="jp-muted">
                Expira en aproximadamente 15 minutos. No compartas este código.
                La página se actualizará automáticamente al completar el proceso.
              </p>
            </div>
          )}
          {device?.effective_state === "failed" && (
            <p className="jp-muted">
              No se pudo iniciar o completar Codex CLI ({device.error_code || "sin detalle"}).
              Comprueba que la autenticación por código de dispositivo esté habilitada para tu cuenta.
              Puedes intentarlo de nuevo.
            </p>
          )}
          <p className="jp-muted jp-small">
            La vinculación se ejecuta en el worker; los tokens se guardan solo en CODEX_HOME,
            nunca en el dashboard ni en PostgreSQL.
          </p>
        </section>
        {error && <div className="jp-alert jp-error" role="alert">{error}</div>}
        {notice && <div className="jp-alert jp-success" role="status">{notice}</div>}
        <div className="jp-metrics">
          <div className="jp-metric"><span>Vacantes en pantalla</span><strong>{systemStatus?.database === "ready" ? uniqueJobs : "—"}</strong></div>
          <div className="jp-metric"><span>Coincidencias por perfil</span><strong>{systemStatus?.database === "ready" ? visible.length : "—"}</strong></div>
          <div className="jp-metric"><span>Última búsqueda</span>
            <strong className="jp-state">{latest ? (
              latest.state === "completed" ? "Completada" :
              latest.state === "running" ? "En ejecución" :
              latest.state === "queued" ? "En cola" : "Falló"
            ) : "Sin ejecuciones"}</strong>
          </div>
        </div>
        <div className="jp-actionbar">
          <div>
            <h2>{activeProfile ? activeProfile.label : "Todas las oportunidades"}</h2>
            <p className="jp-muted">La relevancia del título no equivale a una puntuación profesional verificada.</p>
          </div>
          {activeProfile && (
            <button type="button" className="jp-outline" onClick={() => editing ? setEditing(false) : startEdit(activeProfile)}>
              {editing ? "Volver a vacantes" : "Configurar perfil y CV"}
            </button>
          )}
        </div>

        {editing && draft && view !== "all" ? (
          <section className="jp-panel jp-editor">
            <h3>Preferencias de {draft.label}</h3>
            <p className="jp-muted">Este perfil tiene búsqueda y CV independientes. No inventes experiencia ni competencias.</p>
            <div className="jp-grid2">
              <label>Título profesional
                <input value={draft.headline} onChange={e => patch("headline", e.target.value)} maxLength={160} />
              </label>
              <label>Modalidad
                <select value={draft.mode} onChange={e => patch("mode", e.target.value as Profile["mode"])}>
                  <option value="both">Remoto Colombia o híbrido Bogotá</option>
                  <option value="remote">Solo remoto contratando desde Colombia</option>
                  <option value="hybrid">Solo híbrido en Bogotá</option>
                </select>
              </label>
              <label>Puestos objetivo (uno por línea)
                <textarea rows={8} value={draft.roles.join("\n")} onChange={e => patch("roles", e.target.value.split("\n"))} />
              </label>
              <label>Términos de búsqueda en Remotive (uno por línea; máximo seis)
                <textarea rows={8} value={draft.search_terms.join("\n")} onChange={e => patch("search_terms", e.target.value.split("\n").filter(Boolean))} />
              </label>
              <label>Competencias reales (una por línea)
                <textarea rows={8} value={draft.skills.join("\n")} onChange={e => patch("skills", e.target.value.split("\n").filter(Boolean))} />
              </label>
              <label>Resumen profesional
                <textarea rows={5} maxLength={4000} value={draft.summary} onChange={e => patch("summary", e.target.value)} />
              </label>
              <label>Evidencia de experiencia comprobable
                <textarea rows={5} maxLength={10000} value={draft.evidence} onChange={e => patch("evidence", e.target.value)}
                  placeholder="Organizaciones, tareas y resultados demostrables; sin métricas inventadas" />
              </label>
            </div>
            <div className="jp-grid2">
              <fieldset>
                <legend>Idiomas de ofertas</legend>
                {(["es", "en"] as string[]).map(language => (
                  <label className="jp-check" key={language}>
                    <input type="checkbox" checked={draft.languages.includes(language)} onChange={e =>
                      patch("languages", e.target.checked
                        ? [...new Set([...draft.languages, language])]
                        : draft.languages.filter(x => x !== language))
                    } /> {language === "es" ? "Español" : "Inglés"}
                  </label>
                ))}
                <p className="jp-muted jp-small">La fuente no siempre identifica el idioma. Las ofertas dudosas se dejan pendientes de revisión.</p>
              </fieldset>
              <fieldset>
                <legend>Evaluación de ajuste</legend>
                <label>Proveedor de IA
                  <select value={draft.ai_provider} onChange={e =>
                    patch("ai_provider", e.target.value as Profile["ai_provider"])}>
                    <option value="codex_chatgpt">Codex · cuenta ChatGPT (cuota del plan)</option>
                    <option value="disabled">Sin IA</option>
                  </select>
                </label>
                <p className="jp-muted jp-small">
                  Estado Codex: {aiRuntime?.state === "connected" ? "Conectado con ChatGPT" :
                    aiRuntime?.state === "quota_exhausted" ? "Límite de Codex alcanzado" :
                    aiRuntime?.state === "wrong_auth_method" ? "Se requiere login con ChatGPT, no clave API" :
                    aiRuntime?.state === "cli_unavailable" ? "Codex CLI no disponible" : "Pendiente de conectar en servidor"}.
                  La conexión se realiza una vez por SSH; no se introducen contraseñas ni tokens aquí.
                </p>
                <label>Ajuste mínimo deseado: {draft.min_fit}%
                  <input type="range" min={50} max={100} step={5}
                    value={draft.min_fit} onChange={e => patch("min_fit", Number(e.target.value))}/>
                </label>
                <label className="jp-check">
                  <input type="checkbox" checked={draft.ai_opt_in}
                    onChange={e => patch("ai_opt_in", e.target.checked)} />
                  Autorizo enviar mi resumen y evidencias escritas a Codex para evaluar las ofertas
                </label>
                <p className="jp-muted jp-small">Desactivado por defecto. El CV PDF no se envía. Usa la cuota de Codex de tu cuenta ChatGPT, sin API key. Inferencias como Moodle → uso de LMS deben citar evidencia; no se inventan habilidades.</p>
              </fieldset>
            </div>
            <button type="button" className="jp-primary" disabled={busy} onClick={saveProfile}>Guardar preferencias</button>
            <div className="jp-cv">
              <h3>Hoja de vida · {draft.label}</h3>
              <p>{profiles.find(p => p.id === draft.id)?.cv_original_name
                ? "CV guardado: " + profiles.find(p => p.id === draft.id)?.cv_original_name
                : "Aún no has subido un CV para este perfil."}</p>
              <p className="jp-muted">PDF privado de máximo 5 MB, almacenado fuera de GitHub. No se envía automáticamente.</p>
              <input aria-label="Seleccionar CV PDF" type="file" accept=".pdf,application/pdf"
                onChange={e => setUpload(e.target.files?.[0] || null)}/>
              <div className="jp-buttons">
                <button type="button" className="jp-outline" disabled={busy || !upload} onClick={uploadCv}>Guardar CV PDF</button>
                {profiles.find(p => p.id === draft.id)?.cv_uploaded_at &&
                  <a href={"/api/cv?profile_id=" + draft.id} className="jp-link">Descargar CV privado</a>}
              </div>
            </div>
          </section>
        ) : (
          <>
            <div className="jp-filterbar">
              <label>Filtrar vacantes visibles
                <input type="search" placeholder="Puesto, empresa o ciudad"
                  value={query} onChange={e => setQuery(e.target.value)} />
              </label>
              <label className="jp-check">
                <input type="checkbox" checked={showRejected} onChange={e => setShowRejected(e.target.checked)}/>
                Mostrar también ofertas rechazadas por título
              </label>
              <button className="jp-outline" type="button" onClick={() => refresh()}>Actualizar resultados</button>
            </div>
            {loading ? <p className="jp-empty">Cargando vacantes desde PostgreSQL…</p> :
              visible.length === 0 ? (
                <div className="jp-empty">
                  {systemStatus?.database !== "ready" ? "Esperando conexión con PostgreSQL." :
                    (systemStatus.jobs === 0
                      ? "Todavía no hay publicaciones importadas. Verifica el worker e inicia una búsqueda."
                      : "Hay " + systemStatus.jobs + " publicaciones almacenadas, pero ninguna coincide con estos criterios visibles. Activa «Mostrar también ofertas rechazadas por título» para revisar los motivos.")}
                </div>
              ) : (
                <div className="jp-list">
                  {visible.map(j => (
                    <article className="jp-job" key={j.url + "::" + j.profile_id}>
                      <div className="jp-jobcontent">
                        <div className="jp-jobmeta"><span>{j.profile_label}</span><span>{j.company}</span><span>{j.location}</span></div>
                        <h3>{j.title}</h3>
                        <p className="jp-muted">{j.reason}</p>
                        <div className="jp-pills">
                          <span className="jp-pill">Coincidencia título {j.title_relevance}%</span>
                          <span className={j.official_state === "VERIFIED" ? "jp-pill jp-verified" : "jp-pill jp-warning"}>
                            {j.official_state === "VERIFIED" ? "Empleador y oferta verificados" : "Fuente por verificar"}
                          </span>
                          {j.fit_score !== null && <span className="jp-pill">Ajuste IA {j.fit_score}%</span>}
                          {j.application_status && <span className="jp-pill">Historial: {j.application_status}</span>}
                        </div>
                      </div>
                      <button type="button" className="jp-outline" onClick={() => openJob(j)}>Ver oferta</button>
                    </article>
                  ))}
                </div>
              )}
          </>
        )}
        <footer className="jp-footer">
          El historial es único entre ambos perfiles. «Postulación registrada manualmente» no confirma un envío por parte de JobPilot.
        </footer>
      </main>

      {selected && <div className="jp-backdrop" role="presentation" onMouseDown={e => {
        if (e.target === e.currentTarget) setSelected(null);
      }}>
        <section role="dialog" aria-modal="true" aria-label="Detalle de vacante" className="jp-dialog">
          <div className="jp-dialoghead">
            <div><p className="jp-eyebrow">{selected.company} · {selected.profile_label}</p><h2>{selected.title}</h2>
              <p className="jp-muted">{selected.location}</p></div>
            <button type="button" className="jp-outline" onClick={() => setSelected(null)}>Cerrar</button>
          </div>
          <p className="jp-muted">{selected.reason}</p>
          {selected.ai_summary && <div className="jp-panel"><h3>Evaluación IA</h3><p>{selected.ai_summary}</p></div>}
          {(selected.ai_inferences?.length ?? 0) > 0 && (
            <div className="jp-panel">
              <h3>Competencias: evidencia e inferencias</h3>
              <ul>
                {selected.ai_inferences.map((item, i) => (
                  <li key={i}>
                    <strong>{item.required_skill} — {item.relation === "direct" ? "Demostrada" :
                      item.relation === "inferred" ? "Inferencia respaldada" : "Sin evidencia"}</strong>
                    {item.evidence_text && <p>Evidencia literal: «{item.evidence_text}»</p>}
                    <p className="jp-muted">{item.rationale}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {selected.url.startsWith("https://") && <a href={selected.url} target="_blank" rel="noopener noreferrer" className="jp-link">Abrir oferta original ↗</a>}
          <p className="jp-muted">Fuente: {selected.source === "remotive" ? "Remotive" : selected.source || "Sin identificar"}. Confirma siempre la vacante en el sitio oficial.</p>
          <h3>Descripción de la vacante</h3>
          <div className="jp-description">{selected.description.replace(/<[^>]+>/g," ").slice(0,16000) || "La fuente no proporcionó descripción."}</div>
          <div className="jp-panel">
            <h3>Seguimiento manual de la candidatura</h3>
            <p className="jp-muted">No envía ningún formulario ni correo. Se comparte entre Professional y Assistant.</p>
            <label>Estado
              <select value={applicationStatus} onChange={e => setApplicationStatus(e.target.value)}>
                {statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>Notas
              <textarea rows={3} maxLength={4000} value={applicationNotes}
                onChange={e => setApplicationNotes(e.target.value)}/>
            </label>
            <button type="button" className="jp-primary" disabled={busy} onClick={saveApplication}>Guardar seguimiento</button>
          </div>
        </section>
      </div>}
    </>
  );
}
