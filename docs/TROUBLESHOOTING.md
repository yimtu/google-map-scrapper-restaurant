# Resolver problemas

Empieza con `python foodscan.py doctor` y `python foodscan.py status`. Pide a la IA explicar qué falló, su efecto y el siguiente paso. Los detalles técnicos se conservan en `logs/`; no compartas secretos.

| Mensaje o síntoma | Qué hacer |
|---|---|
| Python no se reconoce | Instalar/verificar Python 3.11+ y abrir una terminal nueva; usar la ruta del intérprete existente si la IA la detecta. |
| Falta Gosom o navegador | Repetir setup; revisar red, descarga y permisos. No reinstalar todo ni borrar datos. |
| ONE-TIME HUMAN INPUT REQUIRED | Proporcionar y aprobar el polígono siguiendo la guía territorial. |
| Archivo territorial inválido | Exportar superficies KML/KMZ o GeoJSON válido, revisar coordenadas y polígonos. |
| Snapshot ya existe | Revisar status; usar resume si fue interrumpido. No sobrescribir ni borrar el snapshot. |
| CAPTCHA o posible bloqueo | Pausar; esperar, reducir carga o probar el proxy disponible. Nunca automatizar CAPTCHA. |
| `unexpected page type` en el smoke | `browser_runtime_bug`: Scrapemate recibió una página interna nula o de tipo incorrecto. No es evidencia de CAPTCHA. Verificar que FoodScan usa el build parcheado. |
| `target closed` | `target_closed`: Chromium, su contexto o la página se cerraron. En Windows, comprobar que el build activo omite `--single-process`. |
| CAPTCHA o tráfico inusual explícito | `captcha_or_google_block`: pausar y sólo entonces evaluar un proxy disponible. |
| Muy pocos resultados | Revisar errores y comparación histórica. No declarar el territorio vacío. |
| Un campo está vacío | Puede no estar disponible en Maps; comprobar la salud general antes de atribuirlo a un error. |
| No aparece un negocio este mes | Tratarlo como ausencia observada, no como cierre definitivo. |
| La descarga pública falla | Comprobar internet y límites de GitHub; reintentar más tarde. No hace falta crear una cuenta ni proporcionar token. |
| Faltan bibliotecas del sistema | Diagnosticar las dependencias concretas y resolver nativamente; solicitar intervención sólo si requieren privilegios. |

No actualices Gosom para cada corrida. `update-gosom` es una decisión deliberada y debe ir seguida de doctor y prueba pequeña. Guarda el reporte de versión anterior para interpretar cambios de extracción.

Docker es último recurso tras demostrar que la instalación nativa no es viable. En una arquitectura sin binario, revisar primero la posibilidad razonable de compilación nativa.

Los tests locales comprueban reglas con datos sintéticos; el smoke comprueba conexión y extracción real pequeña. Ninguno acredita por sí mismo un censo completo del AMG.
