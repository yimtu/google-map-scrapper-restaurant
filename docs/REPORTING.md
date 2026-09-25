# Reportes y quality gate

FoodScan separa los datos técnicos de las salidas comerciales. Los CSV conservan la trazabilidad; el PDF resume los prospectos sin ocultar verificaciones incompletas.

## Archivos principales

- `prospects_3_20.csv`: una fila comercial por marca TARGET.
- `watchlist_2.csv`: marcas con dos sucursales observadas.
- `prospect_branches.csv`: ubicaciones TARGET.
- `platform_presence.csv`: estado agregado por marca y plataforma.
- `platform_evidence.csv`: evidencia por sucursal y plataforma.
- `run_report.json`: resultado de la ejecución.
- `report_traceability.json`: procedencia de KPIs y tablas.

Los estados técnicos no se muestran al usuario. Las salidas comerciales utilizan únicamente **Sí**, **No confirmada** y **Requiere revisión**.

## Quality gate

Cuando la verificación de plataformas forma parte de la corrida, FoodScan registra:

```text
expected_checks
completed_checks
pending_checks
errors
report_status
```

`FoodScan_Report.pdf` sólo se genera con `report_status = FINAL`, después de completar todos los checks esperados sin pendientes ni errores. Si falta cualquier comprobación requerida, el máximo entregable es `FoodScan_Report_DRAFT.pdf`, acompañado por el detalle interno del bloqueo.

Si la verificación de plataformas no fue solicitada ni pertenece a la corrida, el PDF omite esa sección completamente. No llena huecos con estados ambiguos.

## Interpretación

El conteo de sucursales refleja lo observado dentro del territorio y las búsquedas ejecutadas. No demuestra el tamaño nacional de una marca. Una ausencia mensual se reporta como `missing_this_run`; un cierre requiere evidencia explícita.

`run_report.json`, `metadata.json` y `report_traceability.json` permiten reconstruir las cifras del PDF. Antes de usar los resultados comercialmente, revisa el alcance, la salud de la adquisición, el estado del gate y las advertencias.
