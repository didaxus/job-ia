# Contrato del futuro submitter de navegacion

Flujo de estados sugerido:

```
DISCOVERED
 -> OFFICIAL_COMPANY_VERIFIED
 -> OFFICIAL_JOB_LIVE
 -> LOCATION_ELIGIBLE
 -> MATCH_SCORED
 -> DOCUMENTS_PREPARED
 -> ADAPTER_SUPPORTED
 -> FORM_VALIDATED
 -> SUBMIT_ATTEMPTED
 -> SUBMITTED_CONFIRMED | OUTCOME_UNKNOWN | DENIED | USER_ACTION_REQUIRED
```

El reporte de busqueda y puntuacion NO autoriza por si solo el POST.
Un adaptador de ATS valida su propio formulario, version y estado en el
momento de enviarlo. Idempotencia por identificador del puesto + identidad
del postulante + canal de envio. Si se pierde la confirmacion, NUNCA
reintentar automaticamente la transaccion incierta.

No simular MFA, CAPTCHA ni cuentas. Nunca seleccionar respuestas sobre
nacionalidad, ubicacion, autorizacion de trabajo o permisos migratorios que
no procedan de datos previamente confirmados por el postulante. No deducir
que "Remote" significa Colombia elegible. Guardar las preguntas, las
respuestas y pruebas de resultado de forma cifrada con retencion limitada.

La fase inicial muestra adrede `QUEUED_FOR_VERIFIED_BROWSER_ADAPTER` donde
seria incorrecto fingir que se envio una aplicacion por Greenhouse.
