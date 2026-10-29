# Chaves de configuração

42 chaves customizáveis por chat/user. Defaults e descrições completas vivem em `customization.example.json` (com `_doc_KEY` ao lado de cada chave).

## Prompts e timeouts

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `ASK_DL_TIMEOUT` | `5.0` | Segundos pra clicar no botão de download | 1 | 60 |
| `ASK_LANG_TIMEOUT` | `10.0` | Segundos pra escolher idioma de dublagem | 1 | 60 |
| `ASK_CAPTION_TIMEOUT` | `5.0` | Segundos pra escolher incluir caption de mídia social | 1 | 60 |
| `ASK_ARTICLE_TIMEOUT` | `5.0` | Segundos pra escolher incluir corpo de artigo | 1 | 60 |
| `ASK_SCREENSHOT_TIMEOUT` | `5.0` | Segundos pra escolher tirar screenshot | 1 | 60 |
| `ASK_DL_DEFAULT` | `"yes"` | Comportamento no timeout: `"yes"` baixa, `"no"` ignora | — | — |
| `ASK_CAPTION_DEFAULT` | `"no"` | Comportamento no timeout: `"yes"` inclui, `"no"` descarta | — | — |
| `ASK_ARTICLE_DEFAULT` | `"yes"` | Comportamento no timeout: `"yes"` envia artigo, `"no"` descarta | — | — |
| `ASK_SCREENSHOT_DEFAULT` | `"yes"` | Comportamento no timeout: `"yes"` tira foto, `"no"` cai pra falha+retry | — | — |
| `PROMPT_DOWNLOAD_ENABLED` | `true` | `false` baixa direto sem perguntar | — | — |
| `PROMPT_CAPTION_ENABLED` | `true` | `false` respeita ASK_CAPTION_DEFAULT silenciosamente | — | — |
| `PROMPT_LANG_ENABLED` | `true` | `false` baixa idioma original direto | — | — |

## YT-DLP

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `YTDLP_MAX_HEIGHT` | `1920` | Altura máxima do vídeo (480/720/1080/1920/2160/4320) | 144 | — |
| `YTDLP_SOCKET_TIMEOUT` | `90` | Timeout socket do yt-dlp (segundos) | 30 | 600 |
| `YTDLP_YT_CLIENTS` | `"default"` | CSV de clients do extractor (`default,mweb` + PO Token pra idade restrita) | — | — |

## Scraper genérico

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `SCRAPE_MAX_PARALLEL_DOWNLOADS` | `6` | Arquivos baixados em paralelo | 1 | 20 |
| `SCRAPE_MAX_MEDIA_URLS` | `60` | Limite de candidatos | 1 | 500 |
| `SCRAPE_SCROLL_MAX_ROUNDS` | `4` | Scrolls pra lazy-load | 0 | 20 |
| `SCRAPE_SCROLL_PAUSE_MS` | `3000` | Pausa (ms) entre scrolls | 500 | 10000 |
| `SCRAPE_MIN_IMAGE_SIZE` | `50` | Min (px) da imagem | 1 | 500 |
| `SCRAPE_HLS_TIMEOUT_S` | `180` | Timeout ffmpeg ao mux'ar HLS/DASH | 30 | 600 |
| `SCRAPE_FAST_PATH_TIMEOUT_S` | `12` | Timeout fast path HTTP | 5 | 60 |
| `SCRAPE_SCREENSHOT_FALLBACK` | `"yes"` | Oferece screenshot quando nada acha | — | — |
| `SCRAPE_GALLERY_DL_ENABLE` | `"yes"` | Liga gallery-dl | — | — |
| `SCRAPE_GALLERY_DL_TIMEOUT_S` | `90` | Timeout por chamada gallery-dl | 30 | 300 |
| `SCRAPE_GALLERY_DL_PARALLEL_FILES` | `3` | Arquivos de álbum baixados em paralelo | 1 | 8 |
| `SCRAPE_PAYWALL_BYPASS` | `"yes"` | Liga Googlebot UA + archive.ph | — | — |
| `SCRAPE_ARCHIVE_TIMEOUT_S` | `15` | Timeout archive.ph | 5 | 60 |
| `SCRAPE_ARTICLE_EXTRACT` | `"yes"` | Extrai corpo de artigo via trafilatura | — | — |
| `SCRAPE_ARTICLE_MIN_CHARS` | `300` | Min chars pra considerar artigo | 100 | 2000 |

## Telegram / envio

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `MAX_URLS_PER_MESSAGE` | `20` | Máximo de URLs por mensagem | 1 | 50 |
| `MEDIA_GROUP_CHUNK_SIZE` | `10` | Tamanho do chunk em sendMediaGroup (Telegram limita 10) | 1 | 10 |
| `MEDIA_GROUP_DELAY` | `4.0` | Delay (s) entre chunks de 10 — controla flood-risk | 0 | 30 |
| `STATUS_CYCLE_INTERVAL` | `5.0` | Intervalo (s) entre rotações da mensagem de status | 1 | 30 |
| `TELEGRAM_UPLOAD_TIMEOUT` | `600` | Timeout (s) de upload pra Telegram | 30 | 3600 |
| `TELEGRAM_MAX_UPLOAD_MB` | `2000` | Tamanho máx (MB) — hard limit do Bot API pra bots (Premium não afeta) | 50 | 2000 |
| `VIDEO_CONVERT_TIMEOUT` | `900` | Timeout (s) da conversão ffmpeg pra MP4 (webm/mkv/avi/flv) | 60 | 3600 |

## Plataformas específicas

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `IG_CAPTION_MAX` | `1000` | Max caption do IG antes de truncar | 100 | 2200 |
| `IG_USER_AGENT` | `Instagram 219...` | UA pra baixar áudio do IG | — | — |
| `IG_QUEUE_WARN_THRESHOLD` | `5` | Tamanho da fila do Instagram pra warning | 1 | 100 |
| `THREADS_MIN_IMAGE_SIZE` | `500` | Min (px) de imagem do Threads | 1 | 1000 |
| `REDDIT_JSON_UA` | UA do Firefox 123 | UA usado na API JSON do Reddit | — | — |

## Outros

| Chave | Default | Descrição | Min | Max |
|---|---|---|---|---|
| `DOWNLOAD_TIMEOUT_SECONDS` | `15` | Timeout por arquivo individual via aiohttp | 5 | 120 |
| `DOWNLOAD_SEGMENTS` | `4` | Conexões (faixas Range) por arquivo ≥ 4 MB | 1 | 16 |
| `PW_GOTO_TIMEOUT_MS` | `25000` | Timeout (ms) do `page.goto()` | 5000 | 120000 |
| `SAFE_URL_MAX_LENGTH` | `200` | Max chars de URL nos logs | 50 | 1000 |

## O que NÃO é customizável (system-level)

Vive em `.env`, vale pra todo o processo:

- **Auth/identity**: `TELEGRAM_BOT_TOKEN`, `ALLOWED_*`, `ALLOW_ALL`, `FIREFOX_PROFILE_PATH`
- **Endpoints**: `LOCAL_API_HOST`
- **Paths**: `BASE_DOWNLOAD_DIR`, `FIREFOX_PROFILE_PATH`
- **Logger**: `LOG_LEVEL`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- **Pools (boot-time)**: `YTDLP_WORKERS`, `IG_WORKERS`, `IO_WORKERS`, `PW_CONCURRENCY`
- **Sessão aiohttp global**: `AIOHTTP_TOTAL_TIMEOUT`, `AIOHTTP_CONNECT_TIMEOUT`, `AIOHTTP_READ_TIMEOUT`, `AIOHTTP_CONN_LIMIT`, `AIOHTTP_UA_DEFAULT`
- **Playwright (boot-time)**: `PW_VIEWPORT_*`, `PLAYWRIGHT_UA`, `PW_REFRESH_*`
- **TTL caches (boot-time)**: `TTL_RETRIES_SECONDS`, `TTL_FUTURES_SECONDS`
- **Background tasks**: `SHUTDOWN_TASKS_TIMEOUT`, `METRICS_LOG_INTERVAL_MIN`
- **Extensões parseadas no boot**: `IMAGE_EXTS_EXTRA`, `VIDEO_EXTS_EXTRA`
