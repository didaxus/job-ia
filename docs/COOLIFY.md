# Coolify desde Git, sin FTP

El error `Dockerfile.worker: no such file or directory` ocurría porque los archivos del ZIP quedaron planos, mientras el Dockerfile esperaba `app/` y `config/`. El recurso "Docker Compose Empty" tampoco descarga esos archivos.

Crea una nueva **Application** de GitHub `didaxus/job-ia` (rama `main` una vez integrado el PR), con build **Docker Compose**, base directory `/`, Compose Location `/compose.yaml`.

En variables Coolify: `FIT_MIN=80`, `SCAN_EVERY_HOURS=24`, `AUTO_EMAIL=false` y opcional `ANTHROPIC_API_KEY`. El Compose ya no necesita archivo `.env` en disco.

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
