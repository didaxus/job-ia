# Coolify desde Git, sin FTP

El error `Dockerfile.worker: no such file or directory` ocurría porque los archivos del ZIP quedaron planos, mientras el Dockerfile esperaba `app/` y `config/`. El recurso "Docker Compose Empty" tampoco descarga esos archivos.

Crea una nueva **Application** de GitHub `didaxus/job-ia` (rama `main` una vez integrado el PR), con build **Docker Compose**, base directory `/`, Compose Location `/compose.yaml`.

En variables Coolify: `FIT_MIN=80`, `SCAN_EVERY_HOURS=24`, `AUTO_EMAIL=false` y `MAX_CODEX_EVALUATIONS_PER_DAY=4`. El Compose ya no necesita archivo `.env` en disco.

En el servidor, para habilitar CVs, crea directorio privado:
```sh
sudo install -d -o 1000 -g 1000 -m 700 /srv/jobpilot-id/private
sudo nano /srv/jobpilot-id/private/facts.yaml
sudo nano /srv/jobpilot-id/private/profile.yaml
sudo chown 1000:1000 /srv/jobpilot-id/private/{facts,profile}.yaml
sudo chmod 600 /srv/jobpilot-id/private/{facts,profile}.yaml
```
Utiliza las plantillas del repositorio, sustituyendo TODO por hechos verificados. No subas datos personales a GitHub. Sin esos archivos el servicio puede buscar pero no preparar candidaturas reales.

Conecta el panel privado usando `ssh -L 3000:127.0.0.1:13030 root@IP_SERVIDOR` y abre `http://localhost:3000`. No asignes dominio público al panel sin autenticación y TLS.

Los volúmenes `jobpilot_db` y `jobpilot_applications` mantienen estado y PDFs, pero no constituyen una copia de seguridad. No borres el servicio anterior si tiene datos sin migrar.

**Estado:** este prototipo no puede rellenar ni enviar formularios ATS. Solo admite envío SMTP a rutas expresamente autorizadas, con `AUTO_EMAIL=false` por defecto. Ninguna prueba o construcción confirma una candidatura enviada.


## Enrutamiento existente: Cloudflare Tunnel -> Traefik -> JobPilot

**Incidente:** la compilacion y el proceso Next.js pasan (curl al puerto local devuelve HTTP 200), pero `https://jobs-ia.didaxus.com/` no tiene un router utilizable. No es necesario modificar ni reiniciar el tunel o el proxy global.

En `compose.yaml`, **solamente `dashboard`** tiene etiquetas `traefik.enable=true`, router `job-ia-dashboard` con `Host(\`jobs-ia.didaxus.com\`)`, `entrypoints=https`, `tls=true` y servicio hacia el puerto **interno 3000**. El puerto host `127.0.0.1:13030` permanece exclusivamente para el diagnostico local. `pipeline` no tiene router publico.

El dashboard usa las redes `default` y `coolify`; Traefik elige `coolify` mediante `traefik.docker.network=coolify`. La red `coolify` debe existir previamente (Coolify la crea en instalaciones estandar). Nunca cambies etiquetas ni redes del servicio Civitas para reparar JobPilot.

### Evitar enrutamiento duplicado de Coolify

Estas son **etiquetas explicitas**, compatibles con una aplicacion Git/Compose cuyo despliegue sea **Raw (deploy file as-is)**. En un modo Compose gestionado, Coolify tambien puede generar routers automaticamente a partir de Domains. **No mantengas simultaneamente dos routers que compitan por el mismo Host.**

Tras fusionar y antes de cambiar el modo, inspecciona `Advanced > Docker Compose > Compose deployment` y la seccion de dominios. Si eliges Raw, esta definicion se hace responsable de red y labels; conserva el mismo recurso/proyecto y revisa los nombres de volumenes para no desconectar SQLite ni las aplicaciones existentes. Si mantienes el modo gestionado, verifica que los labels propios aparecen en el contenedor y desactiva cualquier router automatico duplicado para ese host. No hagas `docker compose up` paralelo a Coolify.

### Comprobacion en el servidor (solo lectura)

```sh
DASH=$(docker ps -q --filter 'label=com.docker.compose.project=wr4ierhoyxew5iczcfhk9tgm' --filter 'label=com.docker.compose.service=dashboard' | head -n 1)
docker inspect -f '{{ index .Config.Labels "traefik.http.routers.job-ia-dashboard.rule" }}' "$DASH"
docker inspect -f '{{range $network, $config := .NetworkSettings.Networks}}{{$network}} {{end}}' "$DASH"
curl -I http://127.0.0.1:13030/
curl -kI --resolve jobs-ia.didaxus.com:443:127.0.0.1 https://jobs-ia.didaxus.com/
docker logs coolify-proxy --tail 60
```

Se espera la regla `Host(\`jobs-ia.didaxus.com\`)`, la red `coolify`, HTTP 200 en el dashboard local y una respuesta del servicio via Traefik. Si el proxy recibe peticiones por otro entrypoint (por ejemplo, tunnel hacia puerto 80), comprueba la ruta efectiva antes de cambiar `https`: aqui se replica el contrato HTTPS de los servicios existentes.

### Acceso seguro obligatorio para datos personales

**Cloudflare Tunnel no equivale a Cloudflare Access.** Este dashboard de terceros no tiene autenticacion propia. Antes de permitir candidatos, CV, notas o documentos privados, crea una aplicacion de **Cloudflare Zero Trust Access** para `jobs-ia.didaxus.com` que limite el acceso a cuentas autorizadas con MFA. Los headers y el rate limit no autentican usuarios. No uses el panel de Coolify para publicar esta interfaz abierta a Internet mientras carezca de Access.

## PostgreSQL, doble perfil y Codex con la cuenta ChatGPT

Configura JOBPILOT_DB_PASSWORD en Coolify y conserva un respaldo del volumen SQLite actual.
Para Codex no se necesita OPENAI_API_KEY ni claves de Anthropic. El worker instala Codex CLI; realiza una única autenticación de ChatGPT mediante `codex login --device-auth` en el contenedor, con CODEX_HOME persistente y separado del dashboard.

La protección de jobs-ia.didaxus.com se configura exclusivamente en tu aplicación de Cloudflare Zero Trust, fuera de Coolify. No se requieren variables ni validadores de Cloudflare dentro de JobPilot.

Consulta [guía Codex](CODEX-CHATGPT.md) y [migración](DUAL-PROFILES-POSTGRES.md).
