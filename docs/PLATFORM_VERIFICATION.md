# Verificación de plataformas

FoodScan verifica Uber Eats, Rappi y DiDi Food para cada sucursal de marcas TARGET (3–20 sucursales observadas). La cola CSV es el contrato entre el producto y cualquier agente con acceso web.

## Flujo

```text
TARGET
→ platform_check_queue.csv
→ agente investiga la web
→ platform_evidence.csv
→ foodscan verify-platforms
→ quality gate
→ FINAL o DRAFT
```

Ejecuta:

```text
python foodscan.py verify-platforms --month YYYY-MM
```

El comando crea o actualiza la cola, importa evidencia, valida campos, calcula el progreso y ejecuta el gate. No navega la web por Python. Si informa registros `PENDING`, el agente debe investigarlos siguiendo `AGENTS.md`, guardar evidencia y repetir el comando.

## Evidencia por sucursal

Cada fila de `platform_evidence.csv` corresponde a una combinación `brand_id × branch_id × platform` y contiene:

```text
brand_id,branch_id,platform,status,evidence_url,page_title,
matched_name,matched_address,checked_at,method,confidence,notes,search_queries
```

`CONFIRMED` exige una URL abierta y señales suficientes para identificar esa sucursal. Una coincidencia de nombre en el buscador no basta. Una sucursal confirmada no confirma automáticamente las demás.

Antes de `NOT_FOUND` se registran como mínimo tres búsquedas: general, restringida a la plataforma o su dominio y marca más ubicación. Significa “No confirmada en la revisión realizada”, no ausencia absoluta.

`UNCERTAIN` se usa sólo tras una búsqueda ejecutada con evidencia ambigua. Un fallo técnico se conserva como `PENDING` o `ERROR`.

## Progreso y bloqueo

El progreso tiene la forma:

```text
Platform verification: 81/270 checks completed
```

El agente repite investigación e importación hasta que `completed_checks == expected_checks`. Si el navegador, el sitio o los permisos bloquean una comprobación, registra el bloqueo con precisión y genera sólo un DRAFT. Nunca inventa evidencia ni transforma el bloqueo en `UNCERTAIN`.
