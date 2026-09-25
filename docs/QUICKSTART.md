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
python foodscan.py plan --scope AMG_FULL
python foodscan.py pilot --scope AMG_FULL
```

Pide a la IA revisar el piloto, sus errores y `generated/query_yield.csv`, y mostrar una estimación del censo. Después:

```text
python foodscan.py monthly --scope AMG_FULL
```

Si se interrumpe, escribe **“Reanuda la corrida.”** No inicies otro mes para arreglar el anterior. Para comprobar el avance usa `python foodscan.py status`.

Al terminar la adquisición, el agente resolverá la cola de plataformas de los prospectos TARGET usando sus capacidades web y repetirá `verify-platforms` hasta completar el quality gate. Pide el resumen de `run_report.json` y la carpeta del mes en `snapshots/`. Una corrida con advertencias, batches o checks pendientes necesita revisión antes de usar las cifras comercialmente.

El siguiente mes basta: **“Actualiza el censo de alimentos del AMG.”** Para alcance central: **“Actualiza sólo Core Guadalajara.”** No necesitas aprender los parámetros internos.
