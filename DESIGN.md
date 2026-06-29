# DESIGN.md

Documento de diseño del servicio de procesado de recopilatorios de Spotify.
Complementa a `CLAUDE.md`: aquí está el detalle y las decisiones abiertas que
conviene cerrar durante la implementación.

## 1. Objetivo

Automatizar la conversión de exportaciones ZIP de playlists de Spotify en
álbumes recopilatorios bien etiquetados, listos para Navidrome, sin
intervención manual una vez configurado.

## 2. Flujo de alto nivel

```
[/input]  --escaneo periódico-->  agrupar por playlist ID
   |                                     |
   |                          ¿grupo completo y estable?
   |                                     | sí
   |                              descomprimir (tmp)
   |                                     |
   |                       Spotify API: nombre + portada
   |                                     |
   |                    editar metadatos MP3 + embeber portada
   |                                     |
   |                    crear carpeta destino + cover.jpg
   |                                     |
   |                          mover a [/output]
   |                                     |
   +-------- borrar ZIPs <----- OK ------+
```

## 3. Componentes / módulos propuestos

- `scanner` — lista `/input`, extrae IDs, agrupa, evalúa completitud.
- `naming` — regex de extracción de ID y saneado de nombres de carpeta.
- `spotify` — auth (bootstrap OAuth + refresh) y lectura de playlist.
- `tagging` — descompresión, edición de metadatos, embebido de portada.
- `pipeline` — orquesta el procesado de un grupo de principio a fin.
- `service` — bucle principal con intervalo configurable y manejo de señales.
- `config` — carga de variables de entorno con valores por defecto.

## 4. Extracción del ID de playlist

Patrones de entrada a soportar:

- `7EAqBCOVkDZcbccjxZmgjp.zip`
- `00. 7EAqBCOVkDZcbccjxZmgjp.zip`
- `https://open.spotify.com/playlist/7EAqBCOVkDZcbccjxZmgjp`
- `spotify:playlist:7EAqBCOVkDZcbccjxZmgjp`

Regla: localizar una subcadena de exactamente 22 caracteres en `[0-9A-Za-z]`
precedida por `playlist/`, `playlist:`, un prefijo `NN. `, o al inicio del
nombre. El prefijo numérico `NN` (si existe) se guarda como índice de parte.

## 5. Heurística de completitud (detalle)

Datos observados por el usuario:
- Partes intermedias ≈ 1,07 GB.
- Última parte: entre 1 MB y ~999 MB.

Algoritmo propuesto para un grupo con partes ordenadas por `NN`:

1. Debe existir la parte `00` (o un único fichero sin prefijo).
2. Todas las partes salvo la última deben superar `PART_SIZE_THRESHOLD`
   (por defecto un valor algo inferior a 1,07 GB, p.ej. 1000 MB, para tolerar
   variación). Si alguna intermedia está por debajo, el grupo está incompleto.
3. La última parte debe estar por debajo del umbral.
4. Independientemente de lo anterior: **todas** las partes deben llevar
   `STABLE_MINUTES` sin modificarse (mtime). Si no, esperar al siguiente ciclo.

Caso borde a decidir: ¿qué pasa si la playlist real ocupa un múltiplo exacto y
la "última" parte también pesa ≈1 GB? La estabilidad temporal cubre esto: si
lleva >5 min sin cambiar y no llegan más partes, se asume completa.

**DECISIÓN PENDIENTE:** valor exacto de `PART_SIZE_THRESHOLD`. Propuesta inicial
1000 MB. Ajustar tras observar tamaños reales.

## 6. Metadatos a escribir

Confirmados:
- `album` = nombre de la playlist.
- `albumartist` = `ALBUM_ARTIST` (por defecto "Various Artists").
- `compilation` / `TCMP` = 1.
- `tracknumber` = correlativo global 1..N (orden: parte `NN`, luego alfabético
  dentro de la parte).
- Portada embebida (`APIC`) + `cover.jpg` en la carpeta.

**DECISIONES PENDIENTES (a confirmar con el usuario durante la implementación):**
- ¿Sobrescribir `artist` por pista o respetar el que trae el MP3? (recomendado:
  respetar el artista original de cada pista).
- ¿Fijar año/fecha del recopilatorio? ¿Fecha de exportación o dejar vacío?
- ¿Establecer `totaltracks`?
- ¿Numeración de disco (`discnumber`) cuando hay varias partes, o disco único?
  (recomendado: disco único, numeración correlativa).
- Nombre de la carpeta destino: ¿solo el nombre de la playlist, o prefijar algo?
- Nombre del fichero de portada: `cover.jpg` vs `folder.jpg` (Navidrome admite
  ambos; confirmar preferencia).

## 7. Spotify: bootstrap de autenticación

Como las playlists pueden ser privadas, se requiere Authorization Code Flow:

1. Usuario crea una app en el dashboard de Spotify Developers y obtiene
   `client_id` / `client_secret`, y registra un `redirect_uri`
   (p.ej. `http://localhost:8888/callback`).
2. Comando de bootstrap del contenedor abre la URL de autorización, el usuario
   inicia sesión y autoriza, y el servicio captura el `code` y lo intercambia
   por un `refresh_token`.
3. El `refresh_token` se persiste en `/config`. A partir de ahí el servicio
   renueva el access token automáticamente sin intervención.

**DECISIÓN PENDIENTE:** mecanismo concreto del callback en un NAS headless.
Opciones: exponer temporalmente un puerto y hacer el bootstrap desde el navegador
del propio usuario apuntando a la IP del NAS, o hacer el bootstrap en el Mac y
copiar el token resultante a `/config` del NAS. Recomendado: bootstrap en el Mac
(más simple) y copiar el token.

## 8. Docker

- Base `python:3.12-slim`.
- Usuario no-root con `PUID`/`PGID` aplicados en el entrypoint (patrón
  gosu/su-exec) para que la salida pertenezca al usuario correcto en Synology.
- `HEALTHCHECK` opcional.
- Build multi-arch con `docker buildx build --platform linux/amd64,linux/arm64`.
- `docker-compose.yml` de ejemplo con los tres volúmenes y todas las env vars.

## 9. Despliegue en Synology DS920+

- Arquitectura amd64: la imagen `linux/amd64` es la que corre en el NAS.
- Volúmenes: `/volume1/downloads:/input`, `/volume1/music:/output`,
  `/volume1/docker/spotify-recop/config:/config`.
- Fijar `PUID`/`PGID` al usuario que posee la biblioteca de música para que
  Navidrome y DSM puedan leer y para que el borrado de ZIPs funcione.
- Documentar uso desde Container Manager (importar compose) y por CLI SSH.

## 10. Pruebas

- Unitarias: extracción de ID, agrupación, ordenación de partes, heurística de
  completitud (con ficheros simulados de tamaño/mtime), saneado de nombres.
- Tagging: usar MP3 de prueba muy pequeños generados en el propio test.
- No incluir audio real ni ZIPs grandes en el repo.

## 11. Decisiones abiertas (resumen)

1. Valor de `PART_SIZE_THRESHOLD`.
2. Campos de metadatos opcionales (artist, año, totaltracks, discnumber).
3. Nombre de carpeta destino y del fichero de portada.
4. Mecanismo de bootstrap OAuth en el NAS vs en el Mac.
5. ¿Registro persistente de IDs procesados para idempotencia, o basta con que
   los ZIPs se borren tras éxito?
