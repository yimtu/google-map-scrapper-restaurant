# FoodScan: contrato canónico para agentes

Este archivo es la fuente canónica de operación. FoodScan toma las decisiones determinísticas; el agente instala, ejecuta, supervisa y realiza investigación web únicamente cuando FoodScan genera checks pendientes.

## Regla principal

**No improvises el producto.** No sustituyas comandos, no edites snapshots para “arreglar” resultados, no cambies categorías después de aprobar un plan y no reinterpretes una salida porque te parezca más razonable.

## Peticiones del usuario

- **“Prepara FoodScan”**: ejecuta setup y doctor. Termina sólo con FoodScan Doctor: READY o con el bloqueo exacto.
- **“Actualiza FoodScan”**: doctor → territorio → plan inmutable con categorías humanas explícitas → piloto máximo 15 min → presentar alcance/categorías/queries/jobs/proxy/ETA → aprobación humana → adquisición exacta → procesamiento → marcas → expansión dirigida dentro del presupuesto → verificación independiente de Uber Eats/Rappi/DiDi Food para todo negocio confirmado con 3+ locales → quality gate → único PDF final.
- **“Reanuda”**: usa el snapshot y plan existentes. Nunca lo sustituyas por una corrida nueva.
- **“Compara”**: compara sólo snapshots con la misma firma metodológica.

No preguntes al operador por zoom, depth, bbox, workers, pool, páginas por navegador ni parámetros internos.

## Categorías: contrato no negociable

La query de Google Maps NO es un filtro duro de categoría. Gosom puede devolver recomendaciones ajenas a la búsqueda.

1. El usuario expresa categorías humanas con --categories.
2. FoodScan congela categorías, aliases y queries dentro del plan.
3. El agente DEBE mostrar categorías solicitadas y queries derivadas antes de pedir aprobación.
4. Después de aprobar, el agente NO PUEDE agregar, retirar, renombrar ni reinterpretar categorías.
5. FoodScan clasifica cada establecimiento como REQUESTED, ADDITIONAL o UNCLASSIFIED.
6. PROHIBIDO eliminar ADDITIONAL o UNCLASSIFIED para “limpiar” el resultado.
7. ADDITIONAL y UNCLASSIFIED permanecen en raw, datos procesados y PDF, separados de los KPIs solicitados.
8. Sólo REQUESTED alimenta KPIs de categorías solicitadas. Nunca afirmes que una query produjo exclusivamente esa categoría.

Gosom usa JSON Lines como raw productivo para conservar category y categories[] cuando estén disponibles. No conviertas la adquisición productiva de vuelta a CSV si eso pierde categorías secundarias.

## Integridad operativa

Antes de producción presenta territorio/hash, categorías solicitadas, queries derivadas, grid points, jobs, batches, proxy, versión/hash de Gosom, ETA, presupuesto de expansión y política de fuente.

El piloto tiene hard wall de 15 minutos. El smoke usa 1×1×1; el piloto acotado prueba 2×2×1. Producción sólo usa 2×2×1 si el piloto realmente lo completó limpio.

La corrida completa requiere aprobación humana explícita. El plan aprobado congela código, Gosom, territorio, proxy, settings, categorías, queries, jobs y runtime. Si cualquiera cambia, genera un nuevo plan y pide aprobación.

No automatices CAPTCHA. Un bloqueo de Google detiene la adquisición. No presentes una corrida parcial como completa.

## Identidad y marcas

No fusiones negocios sólo por nombre, teléfono compartido, coordenadas o un único website.

- Los IDs de Google son aliases de un record_id interno persistente.
- Conflictos entre aliases fallan cerrado.
- Una cadena se confirma sólo con evidencia fuerte por establecimiento.
- Un homónimo sin evidencia propia permanece independiente.
- SINGLE=1, WATCHLIST=2, TARGET=3–20 y LARGE=21+ son segmentos descriptivos. No confundas TARGET con elegibilidad de plataformas.

## Uber Eats / Rappi / DiDi Food

**La decisión es por negocio y por plataforma, no por “delivery”.**

Para TODA marca confirmada con 3 o más locales observados, sin importar giro y sin límite máximo de locales, deben existir tres decisiones independientes: Uber Eats, Rappi y DiDi Food.

No existe un campo combinado delivery_status.

1. Una evidencia positiva de una sucursal basta para Sí a nivel negocio para esa plataforma.
2. Para No confirmada, deben agotarse las búsquedas necesarias de los locales observados sin evidencia positiva.
3. No confirmada no significa ausencia absoluta.
4. Requiere revisión representa evidencia ambigua o check no resoluble limpiamente.
5. Un link explícito de Uber/Rappi/DiDi dentro de order_online capturado por Gosom es evidencia positiva válida.
6. La ausencia de order_online NUNCA significa No.
7. Una plataforma confirmada no confirma las otras dos.
8. Una marca con 30, 100 o más locales sigue dentro de esta regla si FoodScan la confirmó como cadena.

FoodScan puede conservar detalle por sucursal, pero el quality gate cuenta una decisión independiente por negocio × plataforma. Cuando ya existe un positivo, no sigas investigando sucursales sólo para volver a probar el mismo Sí.

## Investigación web de checks pendientes

Si existen checks pendientes, el agente **DEBE resolverlos activamente utilizando las capacidades web disponibles en su entorno**; el agente realiza la investigación con el navegador o herramienta web disponible.

**Un snippet o la memoria del modelo no son evidencia. Que el nombre aparezca en un buscador no basta. Abre el resultado** y comprueba identidad antes de confirmar.

Si el entorno no permite completar un check, **conserva `PENDING`** o registra ERROR; nunca inventes una conclusión.

Después de guardar evidencia ejecuta `foodscan verify-platforms` y repite mientras queden decisiones requeridas sin cerrar.

Si platform_check_queue.csv contiene filas pendientes, el agente DEBE investigarlas con las capacidades web disponibles.

- prioriza URL directa de la plataforma;
- verifica identidad mediante nombre + ubicación/dirección;
- guarda evidencia inmediatamente;
- nunca uses snippet o memoria del modelo como evidencia;
- antes de NOT_FOUND registra mínimo búsqueda general, búsqueda restringida a plataforma/dominio y marca + ubicación;
- bloqueo técnico = PENDING o ERROR.

Después importa evidencia y vuelve a ejecutar foodscan verify-platforms. Repite hasta que las tres decisiones de cada negocio 3+ estén completas o exista un bloqueo documentado.

## Reporte: un solo entregable humano

El entregable humano canónico es **un solo PDF**. Los CSV/JSON/SQLite son soportes técnicos y no sustituyen al PDF.

El PDF:

- tiene longitud dinámica; no existe límite de 3 páginas;
- NO trunca TARGET a 18 ni WATCHLIST a 12;
- incluye alcance aprobado y categorías solicitadas;
- muestra raw → únicos → REQUESTED → ADDITIONAL → UNCLASSIFIED → marcas;
- incluye todos los negocios confirmados con 3+ locales;
- muestra columnas separadas Uber Eats / Rappi / DiDi Food;
- incluye todos los locales observados de cada negocio 3+;
- incluye el directorio completo REQUESTED;
- incluye ADDITIONAL bajo Hallazgos adicionales;
- incluye UNCLASSIFIED bajo No clasificados;
- incluye metodología, advertencias y trazabilidad.

PROHIBIDO sustituir una tabla completa por “ver CSV adjunto” para ahorrar páginas.
PROHIBIDO omitir Hallazgos adicionales.
PROHIBIDO inventar No cuando el dato simplemente no fue capturado.

## Datos de Gosom

Conserva los campos crudos disponibles. Teléfono, website, rating, review_count, open_hours, price_range, about, menu, order_online y categorías pueden alimentar el PDF o soportes.

El campo status de Gosom NO debe presentarse como abierto/cerrado sin validación específica. Falta de dato significa “sin información capturada”, no “No”.

## Quality gate y terminación

FoodScan_Report.pdf sólo existe como FINAL cuando:

1. adquisición requerida completa;
2. plan ejecutado = plan aprobado;
3. procesamiento y dedupe completos;
4. expansión completada o declarada no requerida;
5. cada marca confirmada con 3+ locales tiene resueltas independientemente Uber Eats, Rappi y DiDi Food;
6. no hay checks requeridos PENDING o ERROR;
7. el reporte se generó desde el snapshot trazable.

Si falta cualquiera, máximo FoodScan_Report_DRAFT.pdf.

Antes de declarar terminado: ejecuta pruebas si modificaste producto, revisa diff, run_report.json, report_traceability.json y comprueba que el PDF existe. No declares éxito porque un subproceso terminó; declara éxito porque el contrato completo pasó.