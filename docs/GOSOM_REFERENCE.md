# Gosom: referencia acotada para FoodScan

Referencia consultada el 24-09-2026: [repositorio oficial](https://github.com/gosom/google-maps-scraper), [releases públicos](https://github.com/gosom/google-maps-scraper/releases/latest) y [esquema de salida](https://github.com/gosom/google-maps-scraper/blob/main/gmaps/entry.go). La versión realmente instalada y su SHA-256 se consultan en `tools/gosom/VERSION.json`; no se asume que main sea idéntico al binario instalado.

El motor activo en Windows es temporalmente `tools/gosom-foodscan/gosom-foodscan.exe`, construido sobre Gosom v1.18.1 y Scrapemate v1.4.0. Corrige el cierre invertido de páginas, la recuperación que podía devolver `(nil,nil)` y elimina `--single-process`. El binario oficial se conserva sin cambios. Versiones, fuentes, pruebas y SHA-256 están documentados en `tools/gosom-foodscan/PATCHES.md` y `VERSION.json`.

## Campos y diferencias de formato

El esquema CSV oficial enumera 36 columnas: `input_id`, `link`, `title`, `category`, `address`, `open_hours`, `popular_times`, `website`, `phone`, `plus_code`, `review_count`, `review_rating`, `reviews_per_rating`, `latitude`, `longitude`, `cid`, `status`, `descriptions`, `reviews_link`, `thumbnail`, `timezone`, `price_range`, `data_id`, `street_view_url`, `place_id`, `images`, `reservations`, `order_online`, `menu`, `owner`, `complete_address`, `credit_cards_accepted`, `about`, `user_reviews`, `user_reviews_extended`, `emails`.

JSON incluye `categories` y utiliza aliases como `web_site`, `description` y el histórico `longtitude`. FoodScan conserva lo recibido y normaliza aliases; no fabrica categorías secundarias ausentes del CSV. Las imágenes contienen `title` e `image` (URL). Los enlaces de menú, reserva y pedido son campos distintos. Fuente: [Entry y CsvHeaders](https://github.com/gosom/google-maps-scraper/blob/main/gmaps/entry.go).

## Controles

| Opciones | Uso en FoodScan |
|---|---|
| `-input`, `-results`, `-json` | Entradas y salida; CSV por defecto, JSON cuando se solicita. |
| `-lang`, `-geo`, `-zoom`, `-depth` | Idioma y búsqueda; FoodScan genera URLs por punto y selecciona profundidad territorial. |
| `-grid-bbox`, `-grid-cell` | Grid uniforme nativo disponible; FoodScan calcula su grid por polígonos y densidad. |
| `-c`, `-browser-pool-size`, `-pages-per-browser` | Carga inicial conservadora: 1, 1, 1. |
| `-resume` | Continuar archivo y sidecar del mismo batch, con parámetros originales. |
| `-proxies-file` | Ruta al archivo privado, cuando está configurado y lo admite el binario. |
| `-exit-on-inactivity` | Salida por inactividad; no equivale por sí sola a éxito. |
| `-email`, `-extra-reviews`, `-fast-mode` | Desactivadas en el censo inicial. |
| `-version` | Identificar dependencia instalada. |

El input admite URLs y un identificador tras `#!#`. Resume requiere salida a archivo y conserva estado junto a resultados; no se reutiliza entre meses. Consulta la [referencia CLI oficial](https://github.com/gosom/google-maps-scraper#command-line) y la ayuda del binario instalado para compatibilidad exacta.

## Entorno y alcance

FoodScan establece `DISABLE_TELEMETRY=1` para desactivar la telemetría de Gosom y usa `PLAYWRIGHT_INSTALL_ONLY=1` durante preparación. Procura guardar el runtime bajo `.runtime/`; cualquier caché externa necesaria debe quedar indicada por la instalación. Consulta [telemetría oficial](https://github.com/gosom/google-maps-scraper#telemetry).

Gosom termina su responsabilidad al entregar establecimientos crudos. Municipio, deduplicación, marcas, completar red de sucursales, segmentos comerciales, plataformas y reportes pertenecen a FoodScan; nunca deben mezclarse con el discovery inicial.

Web UI, REST API, PostgreSQL, AWS Lambda, S3, SaaS Edition, LeadsDB, custom writers y Docker están fuera del camino normal de v0.1: el objetivo local se resuelve con binario, Python y SQLite. La habilidad oficial de Gosom no se instala. No se modifica el código del proveedor.
