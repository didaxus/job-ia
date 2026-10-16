# JobPilot ID

## Dashboard: conexión Codex y diagnóstico de PostgreSQL

El dashboard ahora muestra un asistente para **Conectar ChatGPT mediante código de dispositivo de Codex**, directamente desde `jobs-ia.didaxus.com` (sin API key). El worker es el único componente que almacena las credenciales de la CLI en `CODEX_HOME`. Para iniciar no es obligatorio usar SSH, pero el directorio privado debe existir antes del despliegue.

El servicio `schema` inicializa o actualiza PostgreSQL de forma idempotente **antes** de iniciar worker y dashboard, y `/api/system/status` diferencia entre PostgreSQL sin conexión, esquema incompleto, worker detenido, vacantes almacenadas y cero coincidencias. Consulta la [guía de reparación y vinculación](docs/CODEX-DASHBOARD-ONBOARDING.md).


## Dual-profile PostgreSQL deployment (proposed)

This revision introduces two **editable** search profiles: **Professional (educación/L&D)** and **Assistant (asistencia virtual)**. Profiles have their own search terms, roles, eligibility preferences, factual experience fields, fit thresholds and privately stored PDF CVs.

**PostgreSQL 16 is canonical** for profiles, job-to-profile matches, manually recorded applications and search requests. The current SQLite database remains intact as an upstream staging source and is imported idempotently, including previously rejected postings. One global application record per job URL prevents duplicate application history across profiles. No submissions are dispatched by this revision. **Codex CLI inicia sesión con ChatGPT y usa su cuota del plan, no claves API.**

**Antes de desplegar** configura la contraseña de PostgreSQL, haz respaldo de SQLite y protege el dominio mediante tu aplicación Cloudflare Zero Trust Access. No se requieren variables de Cloudflare en Coolify. See [dual-profile migration and activation guide](docs/DUAL-PROFILES-POSTGRES.md) and [Coolify routing guide](docs/COOLIFY.md).

The UI now provides **Todos / Professional / Assistant**, editable searches, on-demand search requests, profile-specific match reasons, one manual application history and private PDF uploads. Remotive sources are searched with per-profile terms (max 4 requests per rolling 24h per API guidance); curated ATS boards still require live vacancy validation.


Prototipo de busqueda de vacantes de empresas reales, analisis de ajuste, generacion factual de CV y cola de candidaturas. **No postula por formularios ATS**. El envio de email esta desactivado por defecto y requiere aprobacion explicita para cada oferta.

## Despliegue en Coolify

1. Crea una **Application** desde GitHub con este repositorio y la rama `main` (tras integrar el PR).
2. Selecciona **Docker Compose**, base directory `/`, compose file `/compose.yaml`.
3. Configura `JOBPILOT_DB_PASSWORD`, `MAX_CODEX_EVALUATIONS_PER_DAY=4`, `SCAN_EVERY_HOURS=24` y `AUTO_EMAIL=false` en Coolify. No se necesitan claves API ni variables de Cloudflare.
4. Prepara en el servidor `/srv/jobpilot-id/private` y crea ahi `facts.yaml` y `profile.yaml` usando las plantillas de `private/`. Nunca publiques tu CV ni secretos en GitHub.
5. Despliega: el Compose ahora contiene un router Traefik HTTPS para `jobs-ia.didaxus.com` hacia el puerto interno 3000 del `dashboard`, unido a la red externa `coolify`. **Protege el hostname con Cloudflare Access antes de servir datos personales**; Cloudflare Tunnel por sí solo no autentica. Conserva el diagnóstico por `127.0.0.1:13030` (SSH: `ssh -L 3000:127.0.0.1:13030 root@IP_SERVIDOR`). En Coolify evita los routers duplicados entre labels manuales y dominios generados.

### Estructura

- `app/jobpilot.py`: verificacion de vacantes Greenhouse, elegibilidad y preparacion de documentos.
- `config/`: fuentes, filtros, empresas comprobadas y rutas de email aprobadas.
- `private/*.example.yaml`: plantillas sin datos privados.
- `tests/`: pruebas offline.
- `Dockerfile.worker`, `Dockerfile.dashboard`, `compose.yaml`: despliegue.

La busqueda parte de `fedorchenko-juli/job_search_tool` y la exportacion documental de `Remotivated/job-hunt-skills` fijados a revisiones de Git. Las licencias de terceros deben respetarse. No se integra `master-instructional-design` por restricciones de uso.

### Probar

```sh
python -m pip install 'httpx>=0.27' 'pyyaml>=6.0'
python -m unittest discover -s tests -v
docker compose -f compose.yaml config
```

La CI comprueba tests y construye imagenes, pero no valida una postulación real. Los datos de SQLite y documentos se persisten en volúmenes de Docker; realiza copias de seguridad. No elimines el servicio antiguo hasta comprobar el nuevo y migrar sus datos, si los tiene.

Consulta [Codex y tu cuenta ChatGPT](docs/CODEX-CHATGPT.md), [guía Coolify](docs/COOLIFY.md) y [arquitectura](docs/ARCHITECTURE.md).
