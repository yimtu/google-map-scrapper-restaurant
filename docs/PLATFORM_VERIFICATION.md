# Verificación independiente de Uber Eats, Rappi y DiDi Food

FoodScan verifica plataformas para **todo negocio confirmado con 3 o más locales observados**, sin importar giro y sin límite máximo de locales.

La pregunta no es “¿tiene delivery?”. Existen tres decisiones separadas:

- Uber Eats
- Rappi
- DiDi Food

## Evidencia automática de Gosom

Antes de pedir trabajo al agente, FoodScan revisa `order_online` capturado por Gosom. Un link explícito de Uber Eats, Rappi o DiDi Food es evidencia positiva y puede cerrar el Sí del negocio para esa plataforma.

La ausencia de link jamás produce NOT_FOUND.

## Cola web

Los checks que sigan sin resolver aparecen en `platform_check_queue.csv`.

FoodScan conserva evidencia por sucursal porque ayuda a demostrar identidad, pero el quality gate decide a nivel negocio × plataforma:

- si cualquier sucursal está CONFIRMED → negocio/plataforma = CONFIRMED;
- si todas las sucursales observadas terminan NOT_FOUND → negocio/plataforma = NOT_FOUND;
- si queda PENDING o ERROR sin un positivo → la decisión no está cerrada;
- evidencia ambigua completada puede quedar UNCERTAIN.

Una vez confirmado un Sí no se siguen revisando sucursales únicamente para volver a demostrar el mismo Sí.

## Protocolo del agente

Para un check pendiente:

1. busca marca + plataforma;
2. usa consulta restringida al dominio de la plataforma;
3. busca marca + ubicación/sucursal cuando sea necesario;
4. abre evidencia directa;
5. valida nombre y ubicación/dirección compatibles;
6. guarda evidencia incrementalmente.

Antes de NOT_FOUND deben quedar documentadas al menos tres búsquedas: general, dominio/plataforma y marca + ubicación.

Un bloqueo técnico es PENDING o ERROR. No es UNCERTAIN y nunca se convierte en No.

## Estados públicos

- CONFIRMED → **Sí**
- NOT_FOUND → **No confirmada**
- UNCERTAIN / PENDING / ERROR → **Requiere revisión**

“No confirmada” describe la revisión realizada; no demuestra ausencia absoluta.
