# JobPilot ID - Docker Compose starter

**Estado: prototipo de descubrimiento, verificacion, generacion factual de CV y
cola de candidaturas.** No se deben reportar postulaciones de portales web como
enviadas: todavia no existen adaptadores de navegacion para los ATS. Incluye un
canal SMTP opcional solo para anuncios oficiales que invitan explicitamente a
aplicar por correo y han sido aprobados uno por uno.

## Componentes

- `pipeline`: descarga vacantes, filtra y deduplica usando el repositorio MIT
  `fedorchenko-juli/job_search_tool`; puntua con Claude de manera opcional;
  comprueba vigencia del ID de cada trabajo en el ATS Greenhouse publico;
  verifica empresa de registro curado y elegibilidad geografica, y genera
  documentos desde un banco de hechos comprobados.
- `dashboard`: panel local existente del buscador en localhost:3000. Ojo: su
  estado manual de solicitud no equivale a constancia del empleador.
- `app/jobpilot.py`: produce `applications/queue.csv` con motivos exactos de
  descarte, CV por vacante y registros SMTP de no duplicacion.
- `Remotivated/job-hunt-skills`: solamente se utiliza su exportador MIT de
  Markdown a PDF y DOCX, sin redistribuir sus archivos en este paquete.
- `master-instructional-design`: NO va integrado ni clonado debido a sus
  terminos de licencia. Las competencias L&D se basan en criterios comunes y
  en la descripcion publica de GitLab, no en reproducir su metodologia.

## Requisitos

- Docker Engine con Docker Compose v2, espacio para dos imagenes Node/Python.
- Acceso a internet para compilar las imagenes y consultar APIs de empleo.
- En Windows, abrir PowerShell en esta carpeta; en Linux, terminal.
- Opcional: API key de Anthropic para puntuacion de compatibilidad. Sin ella,
  los documentos se pueden preparar, pero el estado sera
  `PREPARED_AWAITING_FIT_SCORE`: NUNCA se enviaran automaticamente.

## Preparacion de archivos personales

Copia estos archivos, despues reemplaza TODAS las marcas `TODO` por hechos
comprobables de tus CV reales:

```sh
cp .env.example .env
cp private/facts.example.yaml private/facts.yaml
cp private/profile.example.yaml private/profile.yaml
```

En PowerShell usa `Copy-Item` en vez de `cp`, si lo prefieres. La primera fuente
(`facts.yaml`) controla lo que puede aparecer en los CV generados: sin hechos
verificados, no hay exportacion. `profile.yaml` alimenta la puntuacion
opcional de Claude. No subas `private/` ni `.env` a GitHub.

## Ejecucion

```sh
# Validar declaracion

docker compose config

# Compilar y arrancar busqueda recurrente + panel privado

docker compose up -d --build

# Observar la primera ejecucion

docker compose logs -f pipeline

# Abrir panel en este mismo equipo: http://localhost:3000

# Ejecutar un unico ciclo, sin esperar 24 horas

docker compose run --rm pipeline python /opt/jobpilot/app/jobpilot.py --once

# Recalcular verificacion y generar PDFs sin buscar de nuevo

docker compose run --rm pipeline python /opt/jobpilot/app/jobpilot.py --prepare-only
```

`SCAN_EVERY_HOURS=24` inicia un ciclo al arrancar y luego cada 24 horas.
El minimo interno es 6 horas, para no superar las 4 consultas diarias
recomendadas por Remotive.

Los resultados aparecen en `applications/queue.csv`.
Cada carpeta `applications/<empresa>-<puesto>-<hash>/` contiene, si supera
los controles, `resume.md`, `resume.pdf`, `resume.docx`,
`coverletter.md`, `coverletter.pdf` y `coverletter.docx`.

## Verificacion de empresas reales

La lista inicial contiene GitLab y Coursera: sus tableros Greenhouse fueron
consultados como empresas reales el 15 de octubre de 2026. No implica que
exista hoy un puesto relevante ni que acepten Colombia.

El sistema valida antes de preparar documentos:

1. Nombre EXACTO del empleador en `config/employers.yaml`.
2. Fuente `greenhouse` directa (no basta un anuncio copiado en Remotive).
3. URL HTTPS oficial con slug y job ID numerico exactos.
4. ID presente en el listado PUBLICO vigente del ATS en cada ciclo.
5. No indicios de tarifa de solicitud.
6. Indicacion de zona contratante apta para Colombia, LATAM o worldwide
   y modalidad remote, o hibrida especificamente en Bogota.
7. Puntuacion si esta disponible; minimo `FIT_MIN`.

Las vacantes "Remote US", "Remote Canada" o solo "Remote" no son
suficientes. La prueba de elegibilidad real de contratacion puede necesitar
revisar descripcion completa, acuerdo de contratacion y preguntas del ATS.
Los detectores no reemplazan una revision final del anuncio.

Para anadir empresas, debes comprobar primero dominio corporativo, pagina
de carreras y el slug que la empresa vincula como su propio ATS. Anade tanto
`config/companies.yaml` como `config/employers.yaml`. La lista puede crecer
con empresas de eLearning, LMS, universidades, organismos y equipos L&D,
siempre que se verifique el enlace oficial.

## Envio de candidaturas - limites reales

**No existe un boton de envio universal.** Greenhouse permite descargar
anuncios por API publica, pero su endpoint API `POST` para aplicaciones
requiere un API key del empleador. No se puede inventar esa credencial.

Este starter solamente incluye envio SMTP cuando TODAS las condiciones
siguientes se cumplen:

- `AUTO_EMAIL=true` en `.env`.
- El trabajo se verifico como real y vigente, con puntaje >= FIT_MIN.
- El empleador tiene un dominio corporativo en la lista curada.
- `config/approved_email_routes.yaml` tiene la URL exacta de esa vacante,
  la direccion del destinatario que pertenece a ese dominio, una URL de
  prueba en el sitio corporativo y `approved_by_user: true`.
- La oferta oficial efectivamente indica que esa cuenta acepta solicitudes
  por correo; es obligatorio comprobarlo antes de anadir la ruta.
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` estan configurados.

SMTP `SMTP_ACCEPTED_UNCONFIRMED` significa que el servidor de correo acepto
el mensaje: no demuestra entrega final ni recepcion por parte de RR. HH.
Los resultados inciertos `OUTCOME_UNKNOWN` no se reintentan automaticamente,
para no duplicar envios. La cola se mantiene en SQLite.

## Siguiente fase: adaptadores de formularios web

Incorporar un contenedor `submitter` con Playwright y adaptadores probados
por portal (Greenhouse, Lever, Ashby, Workable). Cada adaptador debe:

- Reconfirmar el ID del puesto, dominio, estado, lugar y restriccion.
- Comprobar que el formulario no exija registrar una cuenta, pagar, usar
  suscripciones ni sortear CAPTCHA o una barrera de seguridad.
- Adjuntar el PDF generado y contestar solamente con hechos verificados.
- Detenerse si hay campos desconocidos, consentimiento ambiguo o dudas de
  elegibilidad; no marcar "aplicado" por abrir la URL.
- Enviar solo si el sitio lo permite, dentro de una politica de frecuencia
  prudente y con un adaptador probado en ese portal exacto.
- Guardar prueba de confirmacion (ID de candidatura, pantalla de exito o
  acuse explicitamente confirmado). Nunca reutilizar credenciales de otra
  empresa ni crear cuentas sin orden del usuario.

El navegador sin GUI de Docker puede toparse con verificaciones que requieren
accion humana. Ni este starter ni la fase proxima deben eludir CAPTCHA.

## Seguridad

- El panel se publica SOLO a 127.0.0.1 en el host; no abrir el puerto 3000
  a internet sin autenticacion TLS/VPN.
- Variables de SMTP y Anthropic son confidenciales; considera secrets de
  Docker antes de pasar a un servidor compartido.
- Usa imagenes base y referencias GitHub pinneadas; actualizar debe incluir
  verificacion de dependencias y pruebas.
- Los directorios `private/`, `data/` y `applications/` contienen datos
  personales y no deben sincronizarse a repositorios publicos.
- En Linux, si hay errores de escritura al montar volumenes, comprueba que
  el usuario UID 1000 del contenedor pueda escribir en `data/` y
  `applications/`; no uses chmod 777.
- Ninguna postulación se ha enviado durante la creacion de este starter.

## Estado de pruebas

El paquete incluye pruebas unitarias offline del verificador de URLs,
localizacion, empresas, indicios de fraude y generacion de CV desde hechos.
Ejecutar `python -m unittest discover -s tests -v` tras instalar `httpx`
y `pyyaml`. Las pruebas no hacen peticiones de red ni envian correos.

No se ejecutaron `docker compose up` ni aplicaciones reales a empleadores.
El build completo y la integracion live deben comprobarse en un equipo con
Docker e internet antes de considerarlo listo para una campana de envio.

## Fuentes

- https://github.com/fedorchenko-juli/job_search_tool (MIT)
- https://github.com/Remotivated/job-hunt-skills (MIT)
- https://github.com/narosemena/master-instructional-design (CC BY-NC-ND 4.0, NO integrado)
- https://handbook.gitlab.com/job-description-library/people-group/instructional-designer/
- https://docs.greenhouse.io/job-board
- https://github.com/remotive-com/remote-jobs-api
