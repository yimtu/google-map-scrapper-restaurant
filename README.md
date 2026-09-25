# FoodScan

FoodScan descubre establecimientos de alimentos, normaliza y deduplica resultados, identifica marcas, completa redes de sucursales y produce datasets comerciales trazables. Python y SQLite conservan el estado; [Gosom](https://github.com/gosom/google-maps-scraper) realiza la adquisición de Google Maps; un agente compatible opera el flujo y verifica plataformas públicas en la web.

## Entregables

- `prospects_3_20.csv`: marcas TARGET con 3–20 sucursales observadas.
- `watchlist_2.csv`: marcas con dos sucursales observadas.
- `prospect_branches.csv`: detalle de sucursales TARGET.
- `platform_presence.csv` y `platform_evidence.csv`: resultados y evidencia de Uber Eats, Rappi y DiDi Food.
- `FoodScan_Report.pdf`: reporte final, generado sólo cuando pasa el quality gate.

Los resultados locales se crean en `snapshots/`, `data/`, `logs/`, `generated/` y `output/`. Esas carpetas no forman parte del producto publicado.

## Requisitos

- Python 3.11 o posterior.
- Internet y espacio en disco para el runtime y los resultados.
- Un agente con acceso a terminal y archivos.
- Para verificar plataformas: un agente con navegador o capacidad web.

Docker no forma parte de la instalación normal. Un proxy tampoco es requisito inicial.

## Instalación con un agente

Clona el repositorio, ábrelo como carpeta de trabajo y pide al agente que prepare FoodScan siguiendo [`AGENTS.md`](AGENTS.md).

- ChatGPT Desktop/Codex: **“Prepara FoodScan.”**
- Claude Code: **“Lee `CLAUDE.md` y prepara FoodScan.”**
- Otro agente: **“Lee `AGENTS.md` y prepara FoodScan.”**

El equivalente manual es:

```text
python foodscan.py setup
python foodscan.py doctor
```

El objetivo es `FoodScan Doctor: READY`.

Después define y aprueba el territorio siguiendo [la guía territorial](territory/README_TERRITORY.md). Para operar el flujo completo, pide:

> **Actualiza FoodScan.**

El agente ejecutará la adquisición o reanudación, procesará establecimientos y marcas, resolverá la cola web de los prospectos TARGET y aplicará el quality gate antes del reporte final.

## Comandos

```text
python foodscan.py --help
python foodscan.py setup
python foodscan.py doctor
python foodscan.py territory --help
python foodscan.py plan --scope AMG_FULL
python foodscan.py pilot --scope AMG_FULL
python foodscan.py monthly --scope AMG_FULL
python foodscan.py status
python foodscan.py resume
python foodscan.py verify-platforms --month YYYY-MM
python foodscan.py export
python foodscan.py compare
```

En Windows también puedes usar `foodscan.cmd`; en Linux o macOS, `sh foodscan.sh`.

## Documentación

- [Inicio rápido](docs/QUICKSTART.md)
- [Cómo funciona](docs/HOW_IT_WORKS.md)
- [Verificación de plataformas](docs/PLATFORM_VERIFICATION.md)
- [Reportes y quality gate](docs/REPORTING.md)
- [Territorio](docs/TERRITORY.md)
- [Referencia Gosom](docs/GOSOM_REFERENCE.md)
- [Solución de problemas](docs/TROUBLESHOOTING.md)

FoodScan no promete cobertura absoluta de Google Maps. Una ausencia observada no demuestra un cierre y `NOT_FOUND` en una plataforma significa únicamente “No confirmada en la revisión realizada”.
