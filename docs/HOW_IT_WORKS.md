# Cómo funciona

La persona define el territorio y pide la actualización. FoodScan genera puntos de búsqueda dentro de polígonos, distribuidos según densidad. Combina esos puntos con perfiles de alimentos; el piloto ayuda a evitar consultas que apenas añaden establecimientos nuevos.

Gosom recibe URLs de Google Maps con identificadores de punto y consulta. Trabaja en modo navegador, un batch pequeño cada vez, con parámetros compatibles. Los originales y el estado de ejecución permiten conservar lo obtenido y continuar una interrupción. La deduplicación propia une observaciones del mismo establecimiento sin confundir locales que comparten ubicación.

Python recorta territorialmente, normaliza campos, clasifica alimentos y agrupa marcas mediante señales conservadoras. Cada lugar recibe simultáneamente municipio y pertenencia a CORE_PERIFERICO, URBAN_AMG y AMG_FULL; una capa sin geometría aprobada queda desconocida. SQLite guarda establecimientos, observaciones, marcas y corridas con una migración aditiva que mantiene el JSON histórico.

Después se **completa la red de sucursales** únicamente para marcas ya descubiertas con dos o más ubicaciones y señales razonables. La segmentación comercial es SINGLE=1, WATCHLIST=2, TARGET=3–20 y LARGE=21+. Uber Eats, Rappi y DiDi Food se revisan después de segmentar; por defecto sólo TARGET. La cola `platform_check_queue.csv` es un contrato interoperable: FoodScan la prepara y valida, mientras un agente con acceso web investiga cada sucursal y registra evidencia. El ciclo continúa con `verify-platforms` hasta completar el quality gate o documentar un bloqueo real.

Los estados internos son PENDING, ERROR, CONFIRMED, NOT_FOUND y UNCERTAIN. PENDING nunca cuenta como resultado; UNCERTAIN exige investigación ejecutada y evidencia ambigua. Las salidas comerciales traducen estos estados a Sí, No confirmada y Requiere revisión.

El número de sucursales es el observado en el alcance censado. Un nombre parecido no prueba pertenencia a una marca y una marca con seis locales detectados podría tener muchos más fuera del AMG. Los casos dudosos se conservan para revisión; el alcance sin evidencia es `uncertain`.

Los snapshots son independientes por mes. `resume` continúa el mismo snapshot; no convierte el mes anterior en una búsqueda nueva. Una ausencia se reporta como `missing_this_run`. `closed` requiere un estado de cierre observado en la fuente. Los resultados parciales o alcances distintos pueden producir diferencias engañosas: revisa la salud antes de comparar.

Las pasadas adicionales aportan una ganancia marginal: Place IDs nuevos divididos entre los únicos previos. El umbral configurable inicial de parada es 0.5%. Un bajo rendimiento significa saturación empírica de las búsquedas ejecutadas; no demuestra cobertura del 100% de Google Maps.

`run_report.json`, `metadata.json` y `report_traceability.json` explican la ejecución y permiten reconstruir cada KPI del PDF. El nombre `FoodScan_Report.pdf` se reserva para un reporte FINAL; una fase requerida con pendientes o errores produce sólo `FoodScan_Report_DRAFT.pdf`. El dataset permanece en los CSV.
