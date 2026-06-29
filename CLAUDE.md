# CLAUDE.md

Guía de trabajo para Claude Code en este repositorio. Léela siempre antes de
generar o modificar código. Si una decisión contradice lo aquí escrito,
pregunta antes de continuar.

## Qué es este proyecto

Servicio en contenedor Docker que vigila periódicamente un directorio de
descargas, detecta ficheros ZIP de música exportados desde playlists de
Spotify, los procesa (descomprime, edita metadatos como recopilatorio,
descarga nombre y portada de la playlist vía API de Spotify) y deposita el
resultado en un directorio de música servido por Navidrome.

Despliegue objetivo: **Synology DS920+** (x86-64, Intel Celeron J4125) con
Docker / Container Manager. Publicación futura en Docker Hub, idealmente
multi-arch (`linux/amd64` + `linux/arm64`).

## Stack y decisiones cerradas

- **Lenguaje:** Python 3.12+.
- **Metadatos de audio:** `mutagen` (los ficheros de entrada son MP3).
- **API de Spotify:** `spotipy` (o `requests` directo si resulta más simple
  para el flujo concreto). Solo se leen datos: nombre de la playlist y URL de
  la portada.
- **Imagen / portada:** `Pillow` solo si hay que redimensionar o convertir;
  si no, descargar y guardar tal cual.
- **Contenedor:** imagen basada en `python:3.12-slim`. Estilo LinuxServer.io
  para permisos: soporte de `PUID`/`PGID`, no correr como root al escribir
  ficheros de salida.
- **Orquestación local:** `docker-compose.yml` de ejemplo + instrucciones para
  Synology Container Manager.

## Autenticación de Spotify (IMPORTANTE)

Las playlists a procesar son una **mezcla de públicas y privadas**. Por tanto
**NO basta Client Credentials**: se usa **OAuth Authorization Code con refresh
token**.

- Scope mínimo necesario: `playlist-read-private` (y `playlist-read-collaborative`
  si aplica). No se necesitan scopes de escritura.
- El refresh token NO caduca; se genera **una sola vez** mediante un comando de
  bootstrap (`--auth` o subcomando dedicado) que abre el flujo OAuth, captura el
  código y guarda el token en el volumen persistente `/config`.
- Nunca hardcodear `client_id` / `client_secret` / tokens. Vienen por variables
  de entorno o por fichero en `/config`. Añadir `.env`, tokens y secretos a
  `.gitignore`.

## Identificación de ZIPs y agrupación

Cada playlist se identifica por su **ID de Spotify** (22 caracteres base62).

Formatos de nombre de fichero observados:

- Playlist en un único ZIP: `PLAYLISTID.zip` (puede venir también como
  `00. PLAYLISTID.zip`).
- Playlist en varios ZIPs: prefijo numérico de parte:
  - `00. 7EAqBCOVkDZcbccjxZmgjp.zip`
  - `01. 7EAqBCOVkDZcbccjxZmgjp.zip`
  - `02. 7EAqBCOVkDZcbccjxZmgjp.zip`

Reglas:

- Extraer el ID con un regex tolerante que acepte: ID pelado, prefijo `NN. `,
  URL completa (`https://open.spotify.com/playlist/ID`) y URI
  (`spotify:playlist:ID`). El ID son 22 chars en `[0-9A-Za-z]`.
- Agrupar todos los ZIPs que compartan el mismo ID de playlist.
- El prefijo `NN` determina el orden de las partes; dentro de cada parte, las
  pistas se ordenan alfabéticamente por nombre de fichero.

## Detección de "playlist completa" antes de procesar

Combinar dos señales (defensa en profundidad):

1. **Heurística por tamaño:** las partes intermedias pesan ~1 GB (corte
   observado ≈ 1,07 GB). La última parte pesa menos de ~1 GB. El grupo se
   considera potencialmente completo cuando existe la parte `00`, las
   intermedias son ≈1 GB y hay una parte final < umbral.
2. **Estabilidad temporal (salvaguarda):** no procesar hasta que **todas** las
   partes del grupo lleven más de `STABLE_MINUTES` (por defecto 5) sin cambiar
   su tamaño/mtime. Cubre descargas en curso aunque el tamaño confunda.

Filtro de tamaño mínimo: aplicar `MIN_TOTAL_SIZE_MB` (por defecto 100) al
**tamaño total agregado del grupo**, no a cada parte individual.

## Procesamiento de cada grupo

1. Validar completitud (sección anterior).
2. Descomprimir todas las partes a un directorio temporal.
3. Consultar la API de Spotify con el ID: obtener nombre de la playlist y URL
   de la portada de mayor resolución.
4. Descargar la portada como `cover.jpg` (o `folder.jpg`) en la carpeta destino.
5. Editar metadatos de cada MP3 con `mutagen`:
   - `album` = nombre de la playlist.
   - Marcar como recopilatorio: `compilation` (`TCMP` = `1`).
   - `albumartist` = "Various Artists" (configurable).
   - `tracknumber` = correlativo 1..N siguiendo el orden de partes (`NN`) y
     luego alfabético por fichero dentro de cada parte.
   - Embeber la portada en cada fichero (`APIC`) además de guardarla en disco.
   - Resto de campos a confirmar en DESIGN.md.
6. Crear carpeta destino nombrada a partir del nombre de la playlist
   (sanear caracteres no válidos para sistemas de ficheros).
7. Mover/copiar el resultado al directorio de salida (`/output`).
8. Si todo fue OK: **borrar los ZIPs originales** del directorio de entrada.
9. Registrar el resultado (log) y, si se implementa, marcar el ID como
   procesado para idempotencia.

## Directorios (rutas internas del contenedor)

- `/input`  → directorio de descargas vigilado (read-write, para poder borrar).
- `/output` → directorio de música de Navidrome (read-write).
- `/config` → estado persistente: token de Spotify, registro de procesados,
  configuración opcional.

En Synology se mapearán típicamente a `/volume1/downloads`, `/volume1/music` y
una carpeta de configuración del propio contenedor.

## Configuración (variables de entorno)

Definir y documentar al menos:

- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
- `SCAN_INTERVAL_SECONDS` (frecuencia del escaneo periódico)
- `STABLE_MINUTES` (por defecto 5)
- `PART_SIZE_THRESHOLD` (umbral parte llena vs última; por defecto ~1 GB)
- `MIN_TOTAL_SIZE_MB` (por defecto 100)
- `ALBUM_ARTIST` (por defecto "Various Artists")
- `PUID`, `PGID`, `TZ`
- `DELETE_ZIPS_AFTER` (por defecto true)

## Estilo de código y convenciones

- Código y comentarios en inglés (proyecto público); mensajes de log claros.
- Tipado con type hints; `ruff` + `black` para formato y linting.
- Logging con el módulo `logging`, nivel configurable por env (`LOG_LEVEL`).
- Manejo de errores robusto: un grupo que falla NO debe tumbar el servicio ni
  borrar los ZIPs; se registra y se reintenta en el siguiente ciclo.
- Idempotencia: reprocesar el mismo input no debe duplicar ni corromper salida.
- Tests con `pytest` para: extracción de ID, agrupación, heurística de
  completitud y edición de metadatos (con MP3 de prueba pequeños).

## Seguridad

- Nunca commitear secretos. `.gitignore` debe cubrir `.env`, `/config` local,
  tokens y ficheros de prueba grandes.
- No registrar tokens ni secretos en los logs.

## Cómo abordar el trabajo

Trabaja en incrementos pequeños y verificables. Orden sugerido:

1. Esqueleto del proyecto + parsing/agrupación de nombres (con tests).
2. Heurística de completitud (con tests).
3. Integración Spotify (auth bootstrap + lectura de playlist).
4. Edición de metadatos y portada.
5. Bucle de servicio + escaneo periódico.
6. Dockerfile, compose y build multi-arch.
7. README e instrucciones de despliegue en Synology.

Consulta `DESIGN.md` para el detalle de diseño y las decisiones pendientes.
