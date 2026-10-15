# JobPilot ID - Reparacion de Coolify

La causa es un despliegue **Docker Compose Empty**: se guardo el `compose.yaml` en Coolify, pero no se enviaron los archivos del proyecto que el `build.context: .` necesita.

## Recuperacion puntual del servicio existente

En PowerShell, desde la carpeta donde se descargo el ZIP:

```powershell
scp .\jobpilot-id-coolify-repair.zip root@TU_SERVIDOR:/tmp/
ssh root@TU_SERVIDOR
```

En el servidor (Linux), ejecutar:

```bash
mkdir -p /tmp/jobpilot-coolify-repair
unzip -q /tmp/jobpilot-id-coolify-repair.zip -d /tmp/jobpilot-coolify-repair
bash /tmp/jobpilot-coolify-repair/install-jobpilot-coolify.sh \
  /data/coolify/services/hxpvg7jrqq8zln0rdwnayowy \
  /tmp/jobpilot-coolify-repair/jobpilot-id-docker-starter.zip

ls -l /data/coolify/services/hxpvg7jrqq8zln0rdwnayowy/Dockerfile.*
ls -l /data/coolify/services/hxpvg7jrqq8zln0rdwnayowy/app/jobpilot.py
```

El instalador no reemplaza los archivos `.env`, configuraciones existentes ni datos `data/`/`applications/`. Tambien prepara permisos para UID 1000.

Desde Coolify, volver a pulsar **Deploy/Redeploy** del servicio existente. No ejecutar otro `docker compose up` manual al mismo tiempo que Coolify.

## Que debe suceder despues

- Ya no deben aparecer errores `open Dockerfile.worker` o `Dockerfile.dashboard`.
- Se construiran imagenes Node/Python del `pipeline` y Next.js del `dashboard`.
- El sistema buscara anuncios; **no envia automaticamente formularios web**.
- Para generar documentos personalizados se deben rellenar `private/facts.yaml` y `private/profile.yaml` con datos verdaderos y configurar la API de evaluacion si se desea.
- Nunca publicar el dashboard sin autenticacion; el Compose original solo abre el puerto al loopback del servidor (`127.0.0.1:3000`).

## Solucion de despliegue duradera

Esta reparacion carga archivos manualmente en la carpeta del servicio; en futuras recreaciones o migraciones Coolify podria no conservarlos. Para un sistema mantenible, guardar todo el codigo y Dockerfiles en un **repositorio Git privado**, y crear una **Application desde Git -> Build strategy Docker Compose** usando `compose.yaml` en la raiz. Mantener `.env`, datos y documentos privados fuera del repositorio. Consultar https://coolify.io/docs/applications/builds/docker-compose.
