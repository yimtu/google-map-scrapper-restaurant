# FoodScan: contrato canónico para agentes

Este archivo es la fuente canónica de operación para cualquier agente que trabaje en este repositorio. FoodScan es el producto; el agente sólo lo instala, ejecuta, supervisa y complementa con investigación web cuando corresponde.

Lee `README.md` y la ayuda real de `python foodscan.py <comando> --help`. Opera desde la raíz del repositorio. Habla en lenguaje sencillo y reporta únicamente resultados comprobados.

## Peticiones del usuario

- **“Prepara FoodScan”**: detecta el sistema operativo, verifica Python, ejecuta `setup`, prepara Gosom y el navegador, crea la configuración local, inicializa SQLite y ejecuta `doctor`. El objetivo es `FoodScan Doctor: READY`.
- **“Actualiza FoodScan”**: completa sin preguntas técnicas innecesarias doctor → territorio → plan → adquisición o reanudación → procesamiento → deduplicación → marcas → completar red de sucursales → segmentos → verificación web de plataformas TARGET → quality gate → CSV → PDF → resumen.
- **“Reanuda la corrida”**: consulta `status` y continúa el mismo snapshot con sus parámetros originales. No sustituyas una reanudación con una corrida nueva.
- **“Compara este mes contra el anterior”**: ejecuta `compare`, comprueba que alcance y salud sean comparables y explica cambios y ausencias.

No preguntes al operador por zoom, depth, bbox, workers ni otros parámetros internos. Solicita sólo decisiones humanas reales, como aprobación territorial, una credencial introducida de forma local y oculta o permisos del sistema.

## Integridad operativa

No inventes territorios ni aprobación humana. Los polígonos sintéticos de pruebas nunca son territorio productivo. Si falta una capa requerida, informa `ONE-TIME HUMAN INPUT REQUIRED` y sigue `territory/README_TERRITORY.md`.

Antes de una corrida mensual presenta alcance, puntos, consultas activas, trabajos estimados, batches, uso de proxy y versiones. Ejecuta primero la calibración prevista por el producto. No conviertas `setup`, un smoke test o un piloto en un censo productivo.

No declares éxito porque terminó un subproceso. Revisa contenido, batches y `run_report.json`. Un volumen anormalmente bajo, CAPTCHA o fallos requiere diagnóstico. No automatices CAPTCHA ni presentes una corrida parcial como completa.

Conserva los valores iniciales seguros definidos por FoodScan: navegador normal, concurrencia/pool/páginas conservadores y sin fast mode. Gosom es una dependencia externa; `update-gosom` es una acción deliberada. No uses Docker en la ruta normal.

## Datos, secretos y trazabilidad

No cargues datasets completos en el contexto del modelo. Usa Python y SQLite para agrupar, filtrar y contar; inspecciona sólo resúmenes y casos ambiguos pequeños. No inventes conteos, marcas, cobertura ni estados.

No fusiones sucursales sólo por coordenadas compartidas, teléfono o dominio corporativo. Conserva los datos originales y la trazabilidad. Una ausencia significa `missing_this_run`, no cierre. El número observado dentro del territorio no demuestra alcance nacional.

Nunca solicites ni imprimas secretos en conversación. Las credenciales y proxies se introducen localmente y no deben aparecer en logs, CSV, reportes ni commits. Conserva snapshots y estado de reanudación; no los borres para ocultar errores.

Después de modificar el producto, ejecuta las pruebas relevantes y revisa el diff. Distingue tests sintéticos, smoke real, piloto y corrida productiva.

## Segmentos y reportes

FoodScan clasifica SINGLE=1, WATCHLIST=2, TARGET=3–20 y LARGE=21+. La verificación automática de plataformas corresponde a TARGET, salvo instrucción expresa distinta.

Los estados internos son `PENDING`, `ERROR`, `CONFIRMED`, `NOT_FOUND` y `UNCERTAIN`:

- `PENDING`: todavía no investigado.
- `ERROR`: se intentó la comprobación y hubo un bloqueo técnico real.
- `CONFIRMED`: existe evidencia específica y verificable de esa sucursal.
- `NOT_FOUND`: el protocolo de búsqueda se ejecutó sin hallar evidencia suficiente; no significa ausencia absoluta.
- `UNCERTAIN`: la investigación se ejecutó y produjo evidencia realmente ambigua.

Las salidas para usuario muestran sólo **Sí**, **No confirmada** y **Requiere revisión**. Si la verificación forma parte de la corrida, sólo se genera `FoodScan_Report.pdf` cuando el quality gate pasa. Con `PENDING` o `ERROR` se genera como máximo `FoodScan_Report_DRAFT.pdf`. Si la verificación no fue solicitada, la sección se omite.

## Verificación web obligatoria para TARGET

**Si `platform_check_queue.csv` contiene registros `PENDING`, el agente DEBE resolverlos activamente utilizando las capacidades web disponibles en su entorno. Investiga cada combinación `branch × platform`, guarda o actualiza `platform_evidence.csv`, vuelve a ejecutar `foodscan verify-platforms` y repite hasta que `completed_checks == expected_checks` o exista un bloqueo real y documentado.**

Al ejecutar **“Actualiza FoodScan”**, después de generar TARGET ejecuta:

```text
python foodscan.py verify-platforms --month YYYY-MM
```

No preguntes si se deben verificar Uber Eats, Rappi o DiDi Food: forman parte del output TARGET. Python genera, importa y valida la cola; el agente realiza la investigación con el navegador o herramienta web disponible. No implementes un scraper HTTP alternativo para sustituir este procedimiento.

Para cada `branch × platform`:

1. Busca combinaciones de marca, dirección o colonia y plataforma. Ejecuta también una consulta restringida al dominio oficial cuando ayude.
2. Abre el resultado y prioriza páginas directas de la plataforma. Un snippet o la memoria del modelo no son evidencia.
3. Antes de `CONFIRMED`, comprueba identidad: nombre compatible, dirección o sucursal compatible y municipio o colonia compatible; usa teléfono u otra señal adicional cuando exista. Que el nombre aparezca en un buscador no basta.
4. Guarda una fila con `brand_id`, `branch_id`, `platform`, `status`, `evidence_url`, `page_title`, `matched_name`, `matched_address`, `checked_at`, `method`, `confidence`, `notes` y `search_queries`.
5. Antes de `NOT_FOUND`, ejecuta y registra como mínimo una búsqueda general, una restringida al dominio o plataforma y una por marca más ubicación.
6. Una sucursal confirmada no confirma las demás. Un bloqueo técnico queda como `PENDING` o `ERROR`, nunca como `UNCERTAIN`.

Guarda evidencia incrementalmente y repite `verify-platforms` hasta completar el gate. Si el entorno no ofrece acceso web, no inventes resultados: conserva `PENDING`, genera DRAFT y explica qué capacidad falta y qué checks quedaron bloqueados.

## Criterio de terminación

Una actualización termina cuando los batches requeridos están completos, los outputs son consistentes, la fase web TARGET alcanzó su estado permitido y el quality gate emitió `FINAL`. Si existe un bloqueo real, entrega DRAFT y enumera exactamente los checks pendientes o con error.
