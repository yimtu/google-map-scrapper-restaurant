# Territorio

FoodScan genera puntos de búsqueda dentro de polígonos aprobados. No sustituye una geometría faltante con una caja rectangular ni asume límites comerciales o metropolitanos.

## Fuentes admisibles

Publica una geometría sólo si es necesaria, su fuente es pública y su licencia permite redistribuirla. Conserva junto a ella:

- institución y URL de origen;
- fecha de consulta;
- licencia o términos de uso;
- alcance y versión;
- SHA-256 del archivo original.

Si la licencia no permite redistribución, documenta cómo obtener el archivo desde la fuente oficial y mantenlo local e ignorado por Git.

## Importación

FoodScan acepta GeoJSON, KML y KMZ con polígonos. Los marcadores y rutas no definen un territorio. Importa primero sin aprobación, revisa la vista previa y usa `--approve` únicamente después de recibir aprobación humana explícita.

```text
python foodscan.py territory --file territory/input/area.geojson --scope AMG_FULL
python foodscan.py territory --file territory/input/area.geojson --scope AMG_FULL --approve
python foodscan.py plan --scope AMG_FULL
```

El archivo procesado se conserva bajo `territory/processed/`. Los previews y grids generados son artefactos locales. Los polígonos sintéticos pertenecen sólo a fixtures y tests.

Consulta también [la guía operativa](../territory/README_TERRITORY.md).
