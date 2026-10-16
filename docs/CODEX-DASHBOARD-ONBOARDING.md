# Activar datos y conectar Codex desde JobPilot

Esta revisión corrige dos defectos independientes observados tras desplegar el PR #3: un fallo de consulta del historial PostgreSQL que ocultaba toda la interfaz de datos, y la ausencia de un flujo web para la autenticación por código de dispositivo de Codex.

## 1. Qué se ha cambiado

- Nuevo servicio de arranque `schema` basado en PostgreSQL 16: aplica `db/schema.sql` mediante `psql` y se completa **antes** de que arranquen worker y dashboard. El esquema es idempotente y no borra tablas ni volúmenes. Esta separación impide que un fallo posterior del importador SQLite deje el dashboard sin tablas.
- El worker publica un heartbeat y puede seguir activo cuando la importación heredada falla; conserva SQLite sin alteraciones.
- `/api/system/status` ofrece únicamente estado del esquema, conectividad, heartbeat y conteos de ofertas/perfiles (sin secretos ni datos personales).
- El dashboard consulta perfiles, ofertas, búsqueda y proveedor independientemente mediante `Promise.allSettled`: si un endpoint falla, los otros datos no desaparecen de la pantalla.
- Se añade una tarjeta **Conectar Codex con tu cuenta ChatGPT** visible incluso cuando no hay vacantes. El botón encola un inicio de sesión oficial por dispositivo.
- El worker (único servicio con acceso a `CODEX_HOME`) ejecuta `codex login --device-auth`, obtiene el código temporal que imprime la CLI y lo transmite a la interfaz por medio de una tabla PostgreSQL de vida corta. El usuario abre únicamente la URL fija de OpenAI `https://auth.openai.com/codex/device` y autoriza allí su cuenta. El dashboard consulta el estado automáticamente hasta completarse.
- PostgreSQL almacena solo el código de usuario temporal (máximo 15 minutos), nunca `access_token`, `refresh_token`, `auth.json` ni contraseñas. Al terminar, se elimina el código.
- La autenticación del dominio sigue siendo tu propia aplicación Cloudflare Zero Trust. No hay variables `CF_ACCESS_TEAM_DOMAIN` ni `CF_ACCESS_AUD` en Coolify ni una segunda pantalla de login en JobPilot.

## 2. Requisitos previos en el servidor

La rama actual utiliza el mismo proyecto Compose, el volumen SQLite antiguo y el volumen PostgreSQL de JobPilot. **Haz backup antes de desplegar; no uses `docker compose down -v` ni cambies el nombre del proyecto Coolify.**

En Coolify debe estar configurada la contraseña `JOBPILOT_DB_PASSWORD`. El servicio `schema` utiliza esa misma contraseña. **Por defecto, Codex utiliza el volumen Docker persistente `jobpilot_codex_home`**, creado automáticamente por Compose con permisos de usuario correctos. No necesitas crear carpetas por SSH ni introducir secretos de ChatGPT en Coolify.

Si ya tienes una sesión previa de Codex en `/srv/jobpilot-id/codex-home`, puedes conservarla configurando opcionalmente `JOBPILOT_CODEX_HOST_DIR=/srv/jobpilot-id/codex-home` en Coolify; verifica que sea propiedad de UID 1000 y modo 0700. No borres el directorio anterior antes de comprobar la migración.

## 3. Flujo nuevo dentro del dashboard

1. Tras fusionar el PR y pulsar Redeploy, entra en `https://jobs-ia.didaxus.com/`.
2. La tarjeta *Estado del sistema* indicará si PostgreSQL responde, si el worker está activo y cuántas ofertas hay almacenadas.
3. Pulsa **Conectar ChatGPT** en la tarjeta *Conecta Codex con tu cuenta ChatGPT*.
4. Espera a que aparezca un código temporal. Abre el enlace **Oficial de OpenAI** y escribe ese código en la web de OpenAI (no en JobPilot).
5. Vuelve al dashboard: la tarjeta cambiará a *Conectado con ChatGPT*. El código ya no se mostrará.
6. Abre Professional o Assistant, completa la evidencia real, selecciona Codex y autoriza las evaluaciones. Las inferencias deben citar evidencia literal.

La CLI de Codex está diseñada para esta autorización por dispositivo en servidores sin navegador. Si la función está deshabilitada por la cuenta/organización, actívala en los ajustes de ChatGPT. No inventamos una API de autenticación privada ni capturamos la contraseña.

## 4. Si el dashboard sigue vacío después del redeploy

Ejecuta estas **comprobaciones de solo lectura** por SSH; no revelan contraseñas:

```bash
APP=wr4ierhoyxew5iczcfhk9tgm
docker ps -a --filter "label=com.docker.compose.project=$APP" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

curl -sS -i http://127.0.0.1:13030/api/system/status

for SERVICE in postgres schema pipeline dashboard; do
  ID=$(docker ps -aq \
    --filter "label=com.docker.compose.project=$APP" \
    --filter "label=com.docker.compose.service=$SERVICE" | head -n 1)
  if [ -n "$ID" ]; then
    echo "=== $SERVICE ==="
    docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$ID"
    docker logs --tail 40 "$ID" 2>&1
  fi
done
```

**Interpretación:**

- `database=unavailable`: PostgreSQL, credenciales o DNS interno.
- `database=schema_missing`: revisar el contenedor `schema` y la aplicación de las migraciones.
- `worker=stale`: revisar `pipeline`; no confundir con cero ofertas.
- `database=ready`, `worker=active`, `jobs=0`: revisar el volumen SQLite heredado, la importación y el origen de las ofertas.
- `jobs>0`, pero cero coincidencias: activar *Mostrar también ofertas rechazadas* y revisar filtros/títulos.

No se han cambiado el flujo de candidatura manual ni las restricciones de autenticidad de ofertas. La búsqueda en LinkedIn e Indeed sigue pendiente de una integración de fuentes autorizadas y comprobación de la vacante en el ATS oficial.

Referencia del método de autenticación oficial:
https://learn.chatgpt.com/docs/auth
