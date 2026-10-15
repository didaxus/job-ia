# JobPilot ID

## Dual-profile PostgreSQL deployment (proposed)

This revision introduces two **editable** search profiles: **Professional (educación/L&D)** and **Assistant (asistencia virtual)**. Profiles have their own search terms, roles, eligibility preferences, factual experience fields, fit thresholds and privately stored PDF CVs.

**PostgreSQL 16 is canonical** for profiles, job-to-profile matches, manually recorded applications and search requests. The current SQLite database remains intact as an upstream staging source and is imported idempotently, including previously rejected postings. One global application record per job URL prevents duplicate application history across profiles. No submissions are dispatched by this revision.

**Do not merge or deploy without first configuring PostgreSQL credentials and Cloudflare Access.** The new dashboard validates Cloudflare Access JWT cryptographically and fails closed when issuer/AUD are absent. See [dual-profile migration and activation guide](docs/DUAL-PROFILES-POSTGRES.md) and [Coolify routing guide](docs/COOLIFY.md).

The UI now provides **Todos / Professional / Assistant**, editable searches, on-demand search requests, profile-specific match reasons, one manual application history and private PDF uploads. Remotive sources are searched with per-profile terms (max 4 requests per rolling 24h per API guidance); curated ATS boards still require live vacancy validation.


Prototipo de busqueda de vacantes de empresas reales, analisis de ajuste, generacion factual de CV y cola de candidaturas. **No postula por formularios ATS**. El envio de email esta desactivado por defecto y requiere aprobacion explicita para cada oferta.

## Despliegue en Coolify

1. Crea una **Application** desde GitHub con este repositorio y la rama `main` (tras integrar el PR).
2. Selecciona **Docker Compose**, base directory `/`, compose file `/compose.yaml`.
3. Configura las variables en Coolify: `FIT_MIN=80`, `SCAN_EVERY_HOURS=24`, `AUTO_EMAIL=false` y, opcionalmente, `ANTHROPIC_API_KEY`. No subas claves al repositorio.
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

Consulta [guía Coolify](docs/COOLIFY.md) y [arquitectura](docs/ARCHITECTURE.md).
