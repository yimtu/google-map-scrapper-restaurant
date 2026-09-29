# FoodScan

FoodScan descubre establecimientos de alimentos, normaliza y deduplica resultados, identifica marcas, completa redes de sucursales y produce datasets comerciales trazables. Python y SQLite conservan el estado; [Gosom](https://github.com/gosom/google-maps-scraper) realiza la adquisición de Google Maps; un agente compatible opera el flujo y verifica plataformas públicas en la web.

## Entregables

- `FoodScan_Report.pdf`: **único entregable humano canónico**, de longitud dinámica y sin truncar listas.
- `requested_places.csv`: establecimientos de las categorías solicitadas.
- `additional_findings.csv`: recomendaciones válidas que Google devolvió fuera de las categorías solicitadas.
- `unclassified_findings.csv`: resultados cuya categoría no permite decidir con seguridad.
- `multi_location_3_plus.csv`: todo negocio confirmado con 3+ locales, sin importar giro ni tamaño máximo.
- `multi_location_branches.csv`: locales observados de esos negocios.
- `platform_presence.csv` y `platform_evidence.csv`: decisiones independientes y evidencia de Uber Eats, Rappi y DiDi Food.

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

El agente preparará un plan inmutable con categorías humanas explícitas, ejecutará un piloto de calibración limitado a 15 minutos, mostrará categorías/queries/alcance/ETA y pedirá aprobación. Gosom captura raw productivo en JSON Lines para preservar categorías secundarias. FoodScan conserva tanto los resultados solicitados como las recomendaciones adicionales de Google, resuelve marcas con criterio conservador y verifica Uber Eats, Rappi y DiDi Food **por separado para todo negocio confirmado con 3+ locales**, sin importar giro ni límite máximo de locales. El resultado humano es un solo PDF completo.

## Comandos

```text
python foodscan.py --help
python foodscan.py setup
python foodscan.py doctor
python foodscan.py territory --help
python foodscan.py plan --scope AMG_FULL --categories "tacos,postres,nieves"
python foodscan.py pilot --plan generated/plans/<plan>/run_manifest.json
python foodscan.py approve --plan generated/plans/<plan>/run_manifest.json --ack-source-policy
python foodscan.py monthly --plan generated/plans/<plan>/run_manifest.json
python foodscan.py expand-brands --month YYYY-MM
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

## Política de fuente

Las corridas productivas requieren confirmación explícita de la política de fuente/licenciamiento. Consulta [docs/SOURCE_POLICY.md](docs/SOURCE_POLICY.md). La aprobación de FoodScan no sustituye una revisión legal ni los términos del proveedor de datos.

## Categorías y recomendaciones de Google

Una búsqueda de Gosom es una query de Google Maps, no un filtro duro. FoodScan nunca elimina silenciosamente recomendaciones válidas fuera del universo pedido: las clasifica como `REQUESTED`, `ADDITIONAL` o `UNCLASSIFIED` y las presenta por separado.

## Plataformas

No existe un estado combinado de “delivery”. Para cada negocio confirmado con tres o más locales se resuelven independientemente **Uber Eats**, **Rappi** y **DiDi Food**. Un link explícito capturado por Gosom puede confirmar un Sí; la falta de link jamás se interpreta como No.
