# JobPilot ID v2: dos perfiles + PostgreSQL

**Estado:** implementacion propuesta en Pull Request. No cambiar el servidor en produccion hasta configurar secretos, Cloudflare Access y backups. El despliegue anterior SQLite sigue funcionando en main hasta el merge.

## Diseño

- PostgreSQL 16 es la autoridad de perfiles (search_profiles), ofertas importadas (jobs), coincidencias por perfil (profile_matches), solicitudes de busqueda (search_requests) y un unico registro por anuncio en application_history.
- professional y assistant se inicializan una sola vez con puestos editables, terminos de busqueda, idiomas, modo remoto/hibrido, ajuste minimo y datos de evidencia vacios. **No se inventa experiencia.**
- Un CV PDF independiente por perfil en un directorio privado del host. La base solo contiene nombre original, SHA-256 y fecha; los PDFs no entran en PostgreSQL ni GitHub.
- El buscador externo continua usando seen_jobs.sqlite3 como area de captura/deduplicacion. profile_worker.py importa **todas** las ofertas, incluidas las 250 rechazadas por los filtros previos, las reevalua por cada perfil y no borra SQLite.
- Los titulos generan solo una puntuacion de coincidencia tematica; no son una puntuacion real de empleabilidad. El ajuste IA es opcional y exige resumen, evidencias expresas, aceptacion del usuario y API key.
- Las postulaciones siguen siendo **manuales**. Un estado applied_reported no demuestra envio efectuado por JobPilot. No hay formularios web automatizados en esta version.

## PREPARACION OBLIGATORIA en Coolify (antes de merge)

En la Application Git didaxus/job-ia, seccion de variables de entorno de ejecucion:

- JOBPILOT_DB_PASSWORD: generar una contraseña aleatoria y larga; tratarla como secreto. Es nueva y no se comparte con otras bases de datos.
- CF_ACCESS_TEAM_DOMAIN: dominio de equipo de Cloudflare Access, formato https://EQUIPO.cloudflareaccess.com.
- CF_ACCESS_AUD: Application Audience (AUD) Tag exacto de la aplicacion **self-hosted** de Cloudflare Access que proteja jobs-ia.didaxus.com.
- AUTO_EMAIL=false: no enviar correos; el worker v2 nunca envia formularios.
- Opcionales: SCAN_EVERY_HOURS=24, MAX_AI_EVALUATIONS=20, ANTHROPIC_API_KEY (solo si deseas IA despues de autorizarla en cada perfil).
- JOBPILOT_PRIVATE_HOST_DIR=/srv/jobpilot-id/private si se usa la ruta predeterminada.

En Cloudflare Zero Trust crea una aplicacion **Access > Applications > Add an application > Self-hosted** para jobs-ia.didaxus.com con politica Allow restrictiva para tus cuentas y MFA. **Cloudflare Tunnel por si solo NO autentica**. El backend valida la firma RS256, issuer, AUD, expiracion y sesion humana del JWT Access en cada ruta (salvo recursos estaticos y healthz). Si faltan esas dos variables o el JWT, responde 503/401 y **no sirve el dashboard**. No poner valores ficticios en produccion.

En el servidor comprueba permisos de los archivos de CV:

    sudo install -d -o 1000 -g 1000 -m 700 /srv/jobpilot-id/private
    sudo install -d -o 1000 -g 1000 -m 700 /srv/jobpilot-id/private/cvs

El dashboard corre como usuario node UID 1000; los archivos PDF se crean con permisos 0600. No dar a esos archivos una URL publica ajena a los endpoints autenticados.

## Migracion no destructiva

**Antes del primer despliegue v2**, haz backup de los volumenes existentes de Coolify (jobpilot_db para SQLite y jobpilot_applications para documentos). Guarda las copias fuera del repositorio. No ejecutes docker compose down -v, no borres volumenes y no recrees el recurso con otro project-name sin revisar la migracion.

PostgreSQL crea un volumen nuevo jobpilot_postgres, interno sin puertos host publicados. El worker ejecuta el esquema idempotente al arrancar, crea los dos perfiles unicamente si no existen y lee el SQLite actual en modo de solo lectura. Las ofertas con URL repetida hacen upsert; la historia SQLite se importa solo si no existe un registro para esa URL. Los estados heredados son **reportados, no certificados**.

Si todo esta configurado, integra el PR y pulsa Redeploy. Revisa:

    docker ps --filter label=com.docker.compose.project=wr4ierhoyxew5iczcfhk9tgm

    # Sustituye con el nombre real del contenedor:
    docker logs pipeline-... --tail 70
    docker logs dashboard-... --tail 70

El worker comunica [import] N legacy postings indexed against both search profiles, sin perder vacantes. En el dashboard, usa las pestanas Todos / Professional / Assistant, configura cada perfil, sube su CV PDF y usa Buscar ahora. Las busquedas de Remotive emplean los terminos que edites (uno por perfil y ejecucion; rotacion por historial), con limite estricto de **cuatro consultas por ventana movil de 24 horas**. Las empresas curadas se siguen consultando en sus ATS. Las ofertas de agregadores no se califican como oficialmente verificadas sin reconciliacion.

## Rollback

Si falla la migracion, revierte **el codigo/Compose a la version anterior del despliegue** sin ejecutar down -v: el volumen SQLite continua presente e intacto, y los datos nuevos PostgreSQL quedan en su propio volumen. No asumas que cambios realizados unicamente en PostgreSQL volveran automaticamente al dashboard SQLite anterior; exporta/importa esos estados deliberadamente.

## Validacion adicional recomendada en staging

- docker compose config (establece previamente la contraseña real o un valor de CI).
- python -m unittest discover -s tests -v para contratos offline.
- Ejecucion de prueba del worker y esquema contra PostgreSQL temporal; asegurar seed 2/2, importacion repetible y unicidad de application_history.
- Usar una sesion Access valida y verificar que faltas de cookie/token, AUD incorrecto y tokens de servicio son DENY.
- Subir y descargar los dos PDFs, comprobar que no hay contenido accesible por rutas publicas.
- Guardar perfiles distintos, buscar ambos, cambiar professional sin alterar assistant, confirmar que el historial manual no se duplica.

Fuentes: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/ y https://github.com/remotive-com/remote-jobs-api
