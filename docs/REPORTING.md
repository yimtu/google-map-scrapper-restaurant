# Reporte único y quality gate

El entregable humano canónico de FoodScan es un solo PDF. Los CSV, JSONL y SQLite son soportes técnicos y nunca sustituyen al PDF.

## Qué conserva FoodScan

Una query de Gosom no es un filtro duro. Cada establecimiento dentro del territorio se conserva y se clasifica como:

- `REQUESTED`: pertenece al universo solicitado.
- `ADDITIONAL`: Google lo devolvió aunque su categoría explícita queda fuera del universo pedido.
- `UNCLASSIFIED`: la categoría disponible no permite decidir con seguridad.

Los hallazgos adicionales y no clasificados **no se eliminan**. Se reportan por separado y no inflan los KPIs de categorías solicitadas.

## Contenido obligatorio del PDF

El PDF tiene longitud dinámica y debe incluir:

1. alcance aprobado, categorías solicitadas y queries derivadas;
2. cascada de adquisición: raw → únicos → REQUESTED → ADDITIONAL → UNCLASSIFIED → marcas;
3. todos los negocios confirmados con 3+ locales;
4. tres columnas independientes: Uber Eats, Rappi y DiDi Food;
5. todos los locales observados de cada negocio 3+;
6. directorio completo REQUESTED;
7. Hallazgos adicionales;
8. No clasificados;
9. metodología, warnings y trazabilidad.

No existe límite de 3 páginas. No existe top-18 ni top-12.

## Plataformas

La selección de plataformas es por negocio, no por un campo combinado de delivery. Toda marca confirmada con 3+ locales observados entra al gate, sin importar giro ni tamaño máximo.

- Una evidencia positiva de una sucursal resuelve `Sí` para ese negocio/plataforma.
- `No confirmada` requiere haber agotado las búsquedas necesarias sin evidencia positiva.
- `Requiere revisión` cubre ambigüedad o una comprobación que no pudo resolverse limpiamente.
- Falta de dato nunca equivale a No.

## Quality gate

Cuando la verificación de plataformas pertenece a la corrida, FoodScan cuenta **una decisión por negocio × plataforma**. Para N negocios confirmados 3+, existen exactamente `N × 3` decisiones esperadas.

`FoodScan_Report.pdf` sólo se genera como FINAL cuando no queda ninguna decisión requerida PENDING o ERROR. En otro caso el máximo entregable es `FoodScan_Report_DRAFT.pdf`.

`run_report.json`, `metadata.json` y `report_traceability.json` permiten reconstruir las cifras y las tablas del PDF.
