# Preparar el territorio

**ONE-TIME HUMAN INPUT REQUIRED.** FoodScan no inventa los límites del mercado que deseas estudiar. Debes proporcionar o seleccionar una geometría apropiada y aprobarla después de revisar la vista previa.

## Fuente y licencia

Usa preferentemente límites de una fuente gubernamental u otra fuente pública verificable. Antes de incluir una geometría en una distribución, confirma que su licencia permite redistribuirla y registra fuente, URL, fecha, licencia y hash. Si no puede redistribuirse, descárgala localmente desde su fuente oficial y no la añadas al repositorio.

## Procedimiento

1. Obtén o dibuja uno o varios polígonos que representen el alcance comercial.
2. Exporta la capa como GeoJSON, KML o KMZ y guárdala localmente en `territory/input/`.
3. Pide al agente: **“Importa este territorio y muéstrame la vista previa.”**
4. Revisa visualmente superficie, huecos, islas y municipios incluidos.
5. Aprueba expresamente el alcance cuando corresponda a tu intención.

Ejemplo:

```text
python foodscan.py territory --file territory/input/area.geojson --scope AMG_FULL
python foodscan.py territory --file territory/input/area.geojson --scope AMG_FULL --approve
python foodscan.py plan --scope AMG_FULL
```

El agente sólo añade `--approve` después de recibir aprobación humana real. Importar un archivo no constituye aprobación.

El archivo canónico procesado se conserva bajo `territory/processed/`; cada polígono incluye la clasificación territorial que admite la configuración. GeoJSON utiliza coordenadas longitud, latitud. Sólo se aceptan superficies: los marcadores y rutas no reemplazan polígonos.

Los archivos de entrada del cliente, previews y grids son locales. Los polígonos sintéticos se usan únicamente en tests y nunca se promueven a producción. Consulta [la documentación territorial](../docs/TERRITORY.md) para las reglas de publicación y licencia.
