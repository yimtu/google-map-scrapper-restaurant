# Inicio rápido

Abre el repositorio como carpeta de trabajo de tu agente. Pídele leer `AGENTS.md` y di: **“Prepara FoodScan; revisa doctor y la prueba de instalación.”**

El equivalente manual es:

```text
python foodscan.py setup
python foodscan.py doctor
```

Python 3.11 o posterior debe estar disponible. Setup descarga el release nativo público de Gosom si falta, prepara el navegador y ejecuta una búsqueda pequeña. Puedes repetir setup sin borrar tu información. No necesitas cuenta de GitHub, token, Docker ni proxy como requisito normal.

Después sigue [territorio](../territory/README_TERRITORY.md). Falta de polígono es una decisión pendiente, no motivo para inventar fronteras. Con límites aprobados:

```text
python foodscan.py plan --scope AMG_FULL --categories "tacos,postres,nieves"
python foodscan.py pilot --plan generated/plans/<plan>/run_manifest.json
```

El piloto tiene un límite de 15 minutos. Revisa errores, `query_yield.csv`, ETA base y ETA con el presupuesto máximo de expansión. Si alcance, categorías, fuente y tiempo son aceptables, una persona debe aprobar explícitamente el plan:

```text
python foodscan.py approve --plan generated/plans/<plan>/run_manifest.json --ack-source-policy
python foodscan.py monthly --plan generated/plans/<plan>/run_manifest.json
python foodscan.py expand-brands --month YYYY-MM
```

Si se interrumpe, escribe **“Reanuda la corrida.”** No inicies otro mes para arreglar el anterior. Para comprobar el avance usa `python foodscan.py status`.

Al terminar la adquisición, el agente resolverá la cola de plataformas de los prospectos TARGET usando sus capacidades web y repetirá `verify-platforms` hasta completar el quality gate. Pide el resumen de `run_report.json` y la carpeta del mes en `snapshots/`. Una corrida con advertencias, batches o checks pendientes necesita revisión antes de usar las cifras comercialmente.

El siguiente mes basta: **“Actualiza el censo de alimentos del AMG.”** Para alcance central: **“Actualiza sólo Core Guadalajara.”** No necesitas aprender los parámetros internos.

## Regla para agentes

No edites categorías a mano después de crear el plan. No elimines recomendaciones adicionales de Google. El entregable humano final es un solo PDF; Uber Eats, Rappi y DiDi Food se resuelven por separado para cada negocio confirmado con 3+ locales.
