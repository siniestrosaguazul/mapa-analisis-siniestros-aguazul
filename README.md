# Mapa de Análisis Espacial — Siniestros Viales Aguazul

Mapa web interactivo del **Observatorio Territorial de Seguridad Vial de Aguazul (Casanare)**, en el marco de la Red de Observatorios Territoriales (ROT) de la ANSV.

Publicado con GitHub Pages y conectado en vivo a una hoja de Google Sheets: al actualizar la hoja, el mapa refleja los cambios sin necesidad de tocar el código.

## Qué muestra

- Puntos de siniestros coloreados por gravedad (con muertos, con heridos, solo daños).
- Zonas críticas identificadas automáticamente mediante agrupamiento espacial (DBSCAN).
- Buffers (radios de influencia) alrededor de cada zona crítica.
- Mapa de calor de concentración de siniestros.
- Filtros dinámicos por año, mes y gravedad.
- Estadísticas de siniestros y víctimas que se recalculan según los filtros.

Todo el análisis (colores, año/mes, zonas críticas, estadísticas) se calcula en el navegador a partir de los datos crudos de la hoja.

## Estructura

```
├── docs/
│   └── index.html          Mapa (única página del sitio)
├── .github/
│   └── workflows/
│       └── deploy.yml       Despliegue automático a GitHub Pages
└── README.md
```

## Fuente de datos

Los datos se leen de una hoja de Google Sheets **publicada como CSV**
(Archivo → Compartir → Publicar en la web → CSV). La URL se configura en el
bloque `CONFIG` dentro de `docs/index.html`.

Columnas que el mapa reconoce (por coincidencia parcial, tolerante a mayúsculas
y tildes): IPAT, FechaHecho, HoraHecho, Direccion, Gravedad, ClaseAccidente,
Latitud, Longitud, Cant_Muertos, Cantidad_Heridos. Como mínimo se requieren las
columnas de latitud y longitud.

## Parámetros ajustables

En `docs/index.html`, dentro de `CONFIG`:

- `EPS_METROS`: radio de agrupación de zonas críticas (por defecto 100 m).
- `MIN_PUNTOS`: mínimo de siniestros para formar una zona (por defecto 2).
- `BUFFER_METROS`: radio del círculo visual de cada zona (por defecto 150 m).
- `MAP_CENTER` / `MAP_ZOOM`: vista inicial del mapa.

## Cómo se actualiza

- **Los datos** se actualizan solos: se editan en la hoja de Google Sheets.
- **El sitio** se redespliega en cada `push` a `main`, o manualmente desde la
  pestaña *Actions* → *Desplegar mapa a Pages* → *Run workflow*.
