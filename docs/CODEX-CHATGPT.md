# Usar la cuenta de ChatGPT y la cuota de Codex en JobPilot ID

JobPilot ID ejecuta **Codex CLI**, autenticado con tu cuenta ChatGPT, sin OPENAI_API_KEY ni facturación de la API de OpenAI. El uso consume tu cuota normal de Codex, que varía según tu plan. La aplicación **no conoce el saldo exacto de tu cuota**: muestra el estado de conexión e impone un límite de invocaciones propio.

## Antes de desplegar el PR

Mantén la misma Application Coolify y el mismo nombre de proyecto para conservar los volúmenes. PostgreSQL requiere JOBPILOT_DB_PASSWORD. Cloudflare Zero Trust Access se administra exclusivamente desde Cloudflare: no requiere variables en Coolify ni se implanta otro inicio de sesión en el dashboard.

Por defecto, Compose crea un **volumen Docker persistente `jobpilot_codex_home`** con propiedad UID 1000. No necesitas preparar nada por SSH. Si ya tenías una carpeta host existente con una sesión válida de Codex, puedes usarla mediante la variable opcional `JOBPILOT_CODEX_HOST_DIR` y conservar sus permisos. No montes ese volumen en el dashboard.

El archivo `auth.json` contiene tokens equivalentes a credenciales de acceso: nunca publicarlo ni copiarlo a GitHub, al chat o al contenedor web.

## Vincular la cuenta por terminal, una sola vez

Después del despliegue de la rama aprobada, ejecuta por SSH:

```bash
PIPELINE=$(docker ps -q \
  --filter 'label=com.docker.compose.project=wr4ierhoyxew5iczcfhk9tgm' \
  --filter 'label=com.docker.compose.service=pipeline' | head -n 1)

docker exec -it "$PIPELINE" codex login --device-auth
docker exec "$PIPELINE" codex login status
```

Codex mostrará un enlace de autenticación y un código de uso único. Abre el enlace en **tu navegador** e inicia sesión en ChatGPT. No envíes ese código ni credenciales a nadie. Si la autenticación por dispositivo está deshabilitada en tu espacio de trabajo, habilítala con los controles oficiales o usa un método oficial de login de Codex; no copies cookies de ChatGPT.

El estado debe decir **Logged in using ChatGPT**. El adaptador rechaza sesiones de Codex configuradas con una API key, porque el objetivo aquí es utilizar la suscripción.

## Cómo usarlo en el dashboard

1. Elige **Professional** o **Assistant**, y abre **Configurar perfil y CV**.
2. En Proveedor de IA selecciona **Codex · cuenta ChatGPT (cuota del plan)**.
3. Escribe el resumen y la evidencia factual de tu experiencia para ese perfil.
4. Activa la casilla de consentimiento y guarda el perfil.
5. Solicita la búsqueda. Solo las vacantes reconciliadas con su fuente oficial pueden entrar a la evaluación de ajuste IA.

Codex recibe exclusivamente el resumen, las evidencias y habilidades que introdujiste, además de la descripción de la vacante. **No recibe el PDF del CV ni las contraseñas del servidor.**

### Competencias demostradas e inferidas

- **Directa:** competencia documentada de forma explícita en tu experiencia.
- **Inferida:** una experiencia existente permite deducir otra competencia relacionada, con cita literal del texto del perfil; por ejemplo, uso de Moodle respalda el uso práctico de un LMS, pero no administración avanzada de LMS ni certificaciones.
- **Sin evidencia:** no hay fundamento suficiente para afirmar una competencia; JobPilot no debe inventarla.

El resultado del modelo se valida de nuevo en código: cada inferencia positiva tiene que citar texto del perfil de origen. La IA no certifica que una oferta es auténtica; eso requiere verificación de vacante viva en fuente oficial.

## Límites y protección

- El worker llama a Codex CLI usando `codex exec --sandbox read-only --ephemeral --output-schema` y no autoriza escrituras del agente.
- El entorno del proceso Codex solo recibe variables necesarias para la CLI; no recibe PGPASSWORD ni secretos SMTP.
- El límite local por defecto es **cuatro evaluaciones por 24 horas**, configurable con MAX_CODEX_EVALUATIONS_PER_DAY, máximo 30. No representa el límite oficial de la cuenta.
- Si no existe login, se agota la cuota o el sandbox falla, la evaluación queda pendiente: no se inventa una puntuación ni se envía ninguna candidatura.
- Si falla el sandbox de Codex en el entorno Docker, revisa la compatibilidad antes de ejecutar evaluaciones reales; no cambies a `danger-full-access` para solucionarlo.

Fuentes oficiales:
- https://learn.chatgpt.com/docs/auth
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
