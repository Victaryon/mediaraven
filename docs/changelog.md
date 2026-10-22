# Changelog

## v1.3.4 — Post de texto do Reddit volta como texto

**Causa:** lendo a página do post (v1.3.3), o bot pegava imagem e vídeo, mas não o texto. Post só de texto não tinha mídia, caía no yt-dlp e terminava em "🚫 Vídeo indisponível".

- 📝 **Texto do post:** o corpo (`…-post-rtjson-content`) vira o `selftext`, um parágrafo por linha — também na legenda de posts com mídia.
- 💬 **Post só de texto:** volta como mensagem com título, texto e link, como X e Threads (nova chave `downloader_status.reddit_text_only`), sem passar pelo yt-dlp.
- ✅ 429 testes (novo: post de texto lido da página volta só com a legenda).

## v1.3.3 — Reddit volta a baixar sem a API JSON

**Causa:** em 21/10/2026 o Reddit passou a responder `403 Blocked` na API JSON pra qualquer anônimo (IP residencial ou de datacenter, com ou sem cookies), e o yt-dlp — inclusive a versão do mesmo dia — cai em *"Account authentication is required"*. Todo link do Reddit falhava com "🔑 Vídeo exige login".

- 👽 **Página do post no lugar da API:** com 403 no JSON, o `reddit_json` abre a página via `curl_cffi` (digital TLS de Firefox), resolve o desafio JS do Reddit (dobra a semente e reenvia o form) e lê o `<shreddit-post>`: imagens e galerias saem das URLs `i.redd.it` do post; vídeos vão pro yt-dlp pela URL HLS do `<shreddit-player>`, com o título do post na legenda.
- 🔁 **Crosspost:** `content-href` relativo ao original vira URL absoluta e o vídeo da própria página é usado — antes virava "link externo" quebrado.
- 🔤 **Títulos com acento:** o link `/s/` do app chega com o slug codificado duas vezes (`%25C3%25…`) e a página não achava o post; agora é decodificado antes.
- 🖼️ **Post sem `post-type`:** usa o `content-href` quando é imagem.
- 🗑️ **Mídia apagada:** imagem com 404 no `i.redd.it` responde *"A mídia desse post foi removida do Reddit."* (nova chave `downloader_status.reddit_media_removed`) em vez de "Vídeo exige login", sem gastar 4 tentativas do yt-dlp.
- ✅ 428 testes (novos: desafio JS, página com galeria/vídeo/crosspost/sem tipo, slug duplo, mídia removida).

## v1.3.2 — Título das postagens sempre inteiro

**Causa:** na legenda que vai junto da mídia, o título era cortado com `...` — em **80 caracteres** no Reddit (sem autor, o título sobe pro cabeçalho e herdava o limite do nome do autor) e em 120 nos demais. Título do Reddit chega a 300.

- 📝 **O título nunca é cortado:** quem cede espaço na legenda curta é a descrição, que continua saindo completa no texto à parte quando não cabe.
- ✅ 425 testes (novo: título de 300 caracteres do Reddit sai inteiro e a legenda fica ≤ 1024).

## v1.3.1 — Download ignorado vira reação 🙈, sem mensagem

- 🙈 **Ignorar o download não manda mais texto:** com link único, a pergunta some e a reação da mensagem original troca para `reaction_ignored` (default 🙈 — o Telegram só aceita uma lista fixa de emojis como reação de bot, sem ❌). Com vários links na mesma mensagem, ou se o chat recusar a reação, continua o texto `status.download_ignored`.
- ✅ 424 testes (novos: reação + pergunta apagada; vários links mantêm o texto; reação recusada cai no texto).

## v1.3.0 — Sai o instagrapi: Instagram só pela sessão web do Firefox

**Por quê:** desde 02/10/2026 o login novo do instagrapi por senha leva **HTTP 429** para todo mundo ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)), e cada reinício do bot gastava uma tentativa do limite de login da conta. A v1.2.35 já buscava o mesmo JSON pela API web com a sessão do Firefox; o instagrapi virou peso morto.

**Breaking changes:**

- 🗑️ **`IG_USER`, `IG_PASS` e `IG_SESSION_FILE` não existem mais** — pode apagar do `.env`, junto com o `ig_session.json`. A sessão do Instagram agora é a do Firefox (`FIREFOX_PROFILE_PATH`): logue no Instagram por ele.
- 📦 **`instagrapi` sai das dependências** (e com ele `pydantic`, `pycryptodomex` e `PySocks`).

**Major changes:**

- 🌐 **`downloaders/instagram.py` só pela API web** (`download_instagram_instagrapi` → `download_instagram_api`): o shortcode vira id e o JSON vira o objeto de mídia em ~30 linhas, com a mesma escolha do instagrapi (maior resolução de imagem e de vídeo). Foto + música, carrossel e post que exige login seguem iguais.
- 📖 **Stories** (`/stories/<usuario>/<id>/`) reconhecidos pela API web.
- 🛡️ **Chave nova faltando no `messages.json` do usuário cai no texto do `messages.example.json`** em vez de derrubar o download com `KeyError` depois de uma atualização.
- 🚀 Sem login na partida: reiniciar o bot não faz mais nenhuma tentativa de login no Instagram.
- ✅ Validado: 421 testes numa venv nova só com o `requirements.txt` (sem nenhum resto do instagrapi); a chamada da API web respeita o `HTTPS_PROXY` (com o proxy desligado ela falha em vez de sair pelo IP do servidor).

## v1.2.35 — Instagram sem Instagrapi: API web com a sessão do Firefox (foto + música inclusive)

**Causa:** com o login do Instagrapi fora do ar ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)), o caminho do Instagram autenticado desistia logo no início ("cliente não está logado"). Post de **foto com música** — que o embed delega de propósito e o yt-dlp não baixa (*"No video formats found"*) — chegava sem som ou pelo scraper genérico.

**Major changes:**

- 🌐 **`media/{pk}/info` pela API web** quando o Instagrapi não está logado — com os cookies do Firefox (`FIREFOX_PROFILE_PATH`). O JSON é o mesmo da API do app: o `extract_media_v1` do próprio instagrapi monta o `media_info`, e o resto do fluxo não muda (download pelo CDN, `progressive_download_url` + `audio_asset_start_time_in_ms` / `overlap_duration_in_ms` → ffmpeg). Carrossel, reel e post que exige login entram junto.
- 🏷️ Status novo `📸 Instagram Web (...)` — **quem usa `messages.json` próprio precisa adicionar `downloader_status.instagram_web`** (chave faltando dá `KeyError`).
- ✅ Validado: 415 testes; post real de foto + música virou `.mp4` H.264 1088×1104 + AAC com **exatamente 90 s** (o trecho escolhido no post), sem Instagrapi.

## v1.2.34 — Instagram que exige login: gallery-dl com a sessão do Firefox quando o Instagrapi não loga

**Causa:** desde 02/10/2026 o login novo do Instagrapi por senha leva **HTTP 429** no envio das credenciais (fluxo CAA) — problema geral, sem correção ainda ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)). Sem sessão do Instagrapi, um post que o yt-dlp marcava como "exige login" não tinha mais saída: o bot pulava todos os outros caminhos de propósito (pra não mandar o logo da página de erro).

**Major changes:**

- 🖼️ **gallery-dl entra depois do Instagrapi** nos erros de autenticação do Instagram (`sign_in_required`, `age_restricted`, `unavailable`). Ele usa a **sessão web** dos cookies do Firefox (`FIREFOX_PROFILE_PATH`), não a API do app — continua funcionando com o login do Instagrapi fora do ar. Respeita `SCRAPE_GALLERY_DL_ENABLE`.
- ⬆️ **gallery-dl `1.32.0` → `1.32.15`.**
- ⚠️ **Não use o `sessionid` do navegador no Instagrapi** (`login_by_sessionid`): o Instagram rejeita sessão web na API do app e pode **derrubar a sessão do navegador** junto — que é justamente a que o gallery-dl usa.
- ✅ Validado: 413 testes (novo: gallery-dl resolve o post depois do Instagrapi falhar); post real baixado pela `_gallery_dl_run` do bot com a sessão do Firefox.

## v1.2.33 — YTDLP_YT_CLIENTS volta a valer + idade restrita via PO Token + proxy no processo inteiro

**Causa (vídeo com restrição de idade, conta logada e verificada):** o bot respondia "🔞 Vídeo com restrição de idade". Eram dois problemas empilhados:

1. **O `YTDLP_YT_CLIENTS` nunca chegava ao yt-dlp.** O `extractor_args` era montado no formato da linha de comando (`{'youtube': ['player_client=...']}`), que a API do yt-dlp **ignora em silêncio** — rodava sempre o `default`. Passava despercebido porque `default` é o padrão.
2. **O YouTube mudou em set/2026:** com conta comum, vídeo com restrição de idade só sai pelo client `mweb` **com PO Token**; os `web*` passam da checagem mas ficam sem formatos (SABR).

**Major changes:**

- 🐛 **`extractor_args` no formato da API** (`{'youtube': {'player_client': [...]}}`) — o `YTDLP_YT_CLIENTS` passa a valer de fato.
- 🔑 **Suporte a PO Token** — `bgutil-ytdlp-pot-provider==2.0.1` entra nas dependências; com o servidor `bgutil` rodando e `YTDLP_YT_CLIENTS=default,mweb`, vídeo com restrição de idade baixa. Passo a passo em [YouTube → Idade restrita](platforms/youtube.md#idade-restrita-po-token-bgutil). Sem o servidor nada muda.
- 🌐 **Proxy do processo inteiro** — o `aiohttp` passa a respeitar `HTTPS_PROXY`/`NO_PROXY` (`trust_env`) e o Chromium do Playwright abre com o proxy (ele ignora a variável). yt-dlp, gallery-dl, instagrapi e curl_cffi já respeitavam. Sem as variáveis, nada muda.
- 🧹 **Playwright bloqueia service workers** — o `sw.js` do x.com logado prendia um renderer de ~300–500 MB vivo depois do `page.close()`.
- ⬆️ **instagrapi `2.16.0` → `3.0.20`** — a 2.16 se apresentava com versão de app que o Instagram passou a recusar em login novo (*"Your version of Instagram is out of date"*).
- 📌 **yt-dlp pinado no nightly `2026.09.27.232945`.**
- ✅ Validado: 412 testes; vídeo com restrição de idade baixado pelas próprias funções do bot (`default,mweb` + bgutil 2.0.1) e vídeo comum em 4K.

## v1.2.32 — Instagrapi baixa direto do CDN (timeout de 1s derrubava reels) + enxugamento do código

**Causa (reel `/reel/Dc6NTWNhZKu/`):** o bot respondia "Vídeo exige login", mas a conta do Instagrapi **tinha acesso** — ele resolvia o reel pela API privada e quebrava só ao baixar o arquivo do CDN: `ReadTimeout (read timeout=1)`. O `video_download`/`album_download` do instagrapi baixam com o `request_timeout` da lib, **1s por padrão**, e esse mesmo valor é a **pausa antes de cada chamada da API** — subir pra 15s adicionaria 30–45s a cada reel. Como o Instagrapi é o fallback, a falha caía no motivo do yt-dlp (`sign_in_required`) e a mensagem ficava enganosa.

**Major changes:**

- 📥 **Instagrapi só resolve, o bot baixa** — o `media_info` continua vindo da API privada autenticada; os arquivos saem direto das URLs (`video_url` / `thumbnail_url` / `resources` do álbum) via `requests`, com `DOWNLOAD_TIMEOUT_SECONDS` por leitura. Vídeo e álbum **não buscam mais o `media_info` duas vezes**, e a pausa anti-ban da API segue em 1s.
- 📦 `requests` vira dependência direta (já vinha instalado pelo instagrapi).
- ♻️ **Enxugamento do código (sem mudança de comportamento):** 6 wrappers de ffmpeg/ffprobe viraram um `_run_proc`; os 4 callbacks e 3 prompts sim/não do Telegram viraram um handler e uma função; 3 resolvedores de redirect viraram um; `lifecycle/chat_lock.py` e `lifecycle/metrics_log.py` foram para `services.py`; `requirements.txt` passou de `pip freeze` (76 pinos) para as dependências diretas; código morto removido. −343 linhas.
- ✅ Validado: 412 testes; download real do CDN (vídeo 1080×1920) em 0,1s pelo servidor que estourava o timeout; teste cobre foto, vídeo e álbum.

## v1.2.31 — Reddit: sessão anônima fura o 403 da API JSON + suporte a crosspost

**Duas causas (link `/r/riodejaneiro/.../s/WqKj4dUF3T`):**

1. **A API JSON do Reddit passou a bloquear (403 "Blocked") requisições sem cookie de sessão.** O `--print-traffic` do yt-dlp revelou o truque: ele **visita o Reddit primeiro** pra ganhar cookies de sessão **anônima** (`token_v2`, `loid`, `session_tracker`) e só então pede o `.json` — que aí volta 200. O bot mandava o `.json` sem cookie nenhum → 403 → caía no yt-dlp, que batia no rate limit e ficava **7 min** tentando até desistir.
2. **Era um crosspost** ("post dentro do post") — a mídia (galeria de 4 imagens) fica em `crosspost_parent_list`, que o extrator ignorava.

**Major changes:**

- 🪪 **Bootstrap de sessão anônima do Reddit** — antes do `.json`, o bot faz um GET no Reddit pra obter os cookies de guest (`_ensure_reddit_session`), manda `over18=1`, e em caso de 403/429 refaz a sessão e tenta 1x. Restaura a **extração normal** (API Nativa/Imagens), sem delegar pro yt-dlp.
- 🔁 **Suporte a crosspost** — quando o post tem `crosspost_parent_list`, a mídia é extraída do post **original** (galeria, imagem única ou preview). Vídeo no original continua indo pro yt-dlp.
- ✅ Validado end-to-end: o link baixou as **4 imagens** da galeria via API Nativa.

## v1.2.30 — YouTube travava o bot: impersonation obrigatória (TLS anti-bot) + client `default`

**Causa raiz (stack trace do hang):** todos os links do YouTube pararam de baixar e **congelavam o bot**. O trace mostrou o yt-dlp pendurado em `networking/_requests.py:_send` ao baixar a página inicial — o YouTube passou a **tarpitar conexões cujo fingerprint TLS não é de navegador**. O backend `requests`/urllib3 do yt-dlp ficava preso pra sempre (nem `socket_timeout` cortava); o `curl` comum e o `curl_cffi` (impersonation) baixavam a página em ~1s. Não era versão do yt-dlp nem do deno — era **anti-bot de TLS**.

**Major changes:**

- 🕵️ **Impersonation (curl_cffi/chrome) agora no `base_opts`** — cobre os três caminhos do YouTube (detecção de idioma, pré-extração e download), que antes usavam o backend `requests` e travavam. O bot já usava impersonation, mas a lista de plataformas **tinha esquecido o YouTube**.
- 📺 **Client do YouTube: `ios,mweb,web` → `default`** — o experimento SABR do YouTube estava capando os clients `ios`/`mweb` em **360p** (formatos DASH de alta resolução exigem PO token). O conjunto `default` do yt-dlp entrega **1080p H.264 + áudio** sem PO token/bgutil. Validado end-to-end: Rick Astley baixou em 1920×1080.
- ⬆️ **yt-dlp atualizado pro nightly `2026.08.20`** (melhora o conjunto `default`).

## v1.2.29 — Foto+música: capa a resolução em 1280 (1930px estourava o decoder do celular)

**Causa raiz (probe do vídeo real):** o vídeo mesclado estava **tecnicamente perfeito** — H.264 Constrained Baseline, yuv420p, faststart, AAC — mas com resolução **1448×1930** (resolução original da foto do IG). Os **1930px de altura ultrapassam o limite dos decoders H.264 de hardware da maioria dos celulares (~1920)**, então o app não conseguia decodificar → **"unable to play, use external player"**. Não era codec nem metadados; era **resolução**.

**Major changes:**

- 📉 **Merge foto+música capa o lado maior em 1280px** (`scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease`, sem upscale, dimensões pares). Ex: 1448×1930 → 960×1280 — decodifica em qualquer aparelho. É o próprio limite "inline" que o Telegram usa; pra um clipe de foto+música a diferença é imperceptível.

## v1.2.28 — Passa width/height/duration no envio de vídeo (Bot API local não auto-detecta)

**Pesquisa:** o bot usa o **Bot API local** (`LOCAL_API_HOST`). Diferente da API na nuvem, o servidor local **não auto-detecta os metadados do vídeo** — `width`, `height` e `duration` precisam ser passados explicitamente no `sendVideo`/`InputMediaVideo`. Sem eles, o cliente do Telegram às vezes não consegue montar o player e mostra **"App was unable to play this video. Try external player?"** — mesmo com o codec certo (H.264/AAC/yuv420p/faststart). Era o caso da foto+música do IG e de outros vídeos.

**Major changes:**

- 📐 **`send_video` e `InputMediaVideo` agora recebem `width`, `height`, `duration` (via `ffprobe`) + `supports_streaming`.** Vale pra todo vídeo enviado — single e álbum. Novo helper `async_ffprobe_video_meta` em `utils.py`.

**Adicionado:**

- `async_ffprobe_video_meta` em `utils.py`; `_video_meta_kwargs` em `telegram_io.py`

## v1.2.27 — Checagem de codec agora roda pra TODOS os vídeos (fecha o furo do .mp4)

O `async_ensure_telegram_video` do v1.2.25 passou a checar o codec, mas o wrapper `_ensure_video` (em `telegram_io.py`) **retornava cedo pela extensão** antes de chamá-lo — então `.mp4` com **AV1/VP9/HEVC** (comum em TikTok/IG via instagrapi, scraper, etc.) continuava indo incompatível. A checagem de codec do v1.2.25 era, na prática, ignorada pra `.mp4`.

**Major changes:**

- 🔧 **`_ensure_video` agora delega direto pro `async_ensure_telegram_video`** (sem curto-circuito por extensão). Agora **todo** vídeo enviado — single ou álbum, de qualquer plataforma — passa pelo `ffprobe`: se já for H.264+AAC, vai como está; se for AV1/VP9/HEVC, re-encoda pra H.264/AAC com faststart. Isso fecha o furo e faz a correção do v1.2.25 valer de verdade.

**Adicionado:**

- Teste atualizado em `tests/test_telegram_io_timeouts.py` (`.mp4` também passa pela checagem de codec)

## v1.2.26 — Corrige regressão: foto+música do IG voltava só a foto

O `-framerate 30` do v1.2.25 fazia o merge ffmpeg **estourar o timeout de 60s** (encoda 30x mais frames; numa imagem grande + máquina carregada passava de 60s), então o merge falhava e o bot mandava **só a foto**. Ajustado:

- 🎬 **Merge foto+música: 30 fps → 15 fps** (metade dos frames, ~20s numa imagem 1440×1800; ainda um framerate normal e compatível com o Telegram) e **timeout 60s → 180s** (folga pra máquina sob carga). Mantém H.264 + AAC + faststart. Validado ponta a ponta no post reportado: volta "Vídeo com Música" (h264 15fps + aac + faststart) em ~38s.

## v1.2.25 — Vídeos "incompatíveis / precisa de player externo" no Telegram

O Telegram só toca **H.264 + AAC** inline. Vídeos que não batiam com isso vinham marcados como incompatíveis. Três frentes:

**Major changes:**

- 🎬 **Foto+música do Instagram (merge ffmpeg) agora é compatível.** O merge usava **`-framerate 1`** (vídeo a 1 fps, que o player do Telegram rejeita) e **não tinha `-movflags +faststart`** (sem streaming inline). Corrigido pra **30 fps + faststart** (`-tune stillimage` mantém o arquivo do mesmo tamanho).
- 🔎 **`async_ensure_telegram_video` agora checa o codec antes de decidir**, não só a extensão. Antes, qualquer `.mp4` passava direto — então um `.mp4` com **AV1/VP9/HEVC** (comum em YouTube/TikTok/FB) ia incompatível pro chat. Agora faz `ffprobe`: se já for H.264+AAC, envia como está (sem re-encode); se não, re-encoda pra H.264/AAC com faststart.
- 🎯 **yt-dlp passa a preferir H.264/AAC** (`format_sort: ['vcodec:h264', 'acodec:aac']`). Assim a maioria dos downloads já vem compatível e evita o re-encode (mais rápido). Confirmado: YouTube que pegava `av01 @ 1440p` agora pega `avc1 @ 1080p` (compatível). Quando só existe AV1/HEVC, o re-encode acima garante a compatibilidade.

**Adicionado:**

- 4 testes em `tests/test_video_convert.py` (`.mp4` H.264 passa direto; `.mp4` AV1 e HEVC re-encodam; merge usa 30 fps + faststart)

## v1.2.24 — YouTube volta a baixar em alta qualidade (atualiza yt-dlp)

**Major changes:**

- ✅ **YouTube em alta qualidade (1080p/1440p) de volta.** A causa raiz do 403 era simplesmente o **yt-dlp desatualizado**: a última *stable* (`2026.7.4`, de julho) estava ~6 semanas atrás das mudanças do YouTube, e os consertos do YouTube saem primeiro nas **nightlies**. Atualizado para a nightly `2026.8.18.122307.dev0`. Confirmado no pipeline completo do bot: baixa **1440p** e **1080p**, sem nenhuma dependência ou serviço extra.

**Adicionado:**

- yt-dlp atualizado para `2026.8.18.122307.dev0` (nightly) no `requirements.txt`

**Nota:** o YouTube é alvo móvel — quando quebrar de novo, o conserto vem numa **nightly nova** (`pip install -U --pre yt-dlp`), não na stable. Vale checar a nightly antes de qualquer outra investigação.

## v1.2.23 — Reddit: link externo de vídeo embedado (YouTube) volta a ser re-despachado

**Major changes:**

- 🔗 **Post do Reddit que é link pra vídeo externo (YouTube, etc.) volta a ser tratado pelo destino.** O `reddit_external_link` (v1.2.19) excluía posts com `post_hint == 'rich:video'` achando que era vídeo nativo — mas `rich:video` é justamente **vídeo externo embedado** (YouTube/streamable/…); o nativo do Reddit é `hosted:video` (v.redd.it). Por causa disso, um post-link pro YouTube caía no `download_reddit_json` → yt-dlp na URL do Reddit → scraper (imagens da página), em vez de re-despachar pro YouTube. Corrigido: só `hosted:video`/`is_video` (nativo) são excluídos; `rich:video` passa pela checagem de domínio e é re-despachado como link externo. Confirmado no post reportado (`youtu.be/d0avNDsWslg`).

**Adicionado:**

- Teste em `tests/test_reddit_common.py` (`rich:video` externo vira link externo)

## v1.2.22 — YouTube: não despejar fragmentos DASH quando o yt-dlp falha

**Contexto:** quando o yt-dlp falhava num link do YouTube, o dispatcher caía no scraper genérico, que baixava os **fragmentos DASH picotados** (dezenas de `.mp4`) e mandava tudo pro chat.

**Major changes:**

- 🚫 **Quando o yt-dlp falha num link do YouTube, o scraper genérico é pulado** (`_run_platform_fallbacks` retorna cedo pra `platform.youtube`). O scraper nunca produz um vídeo útil pro YouTube — só fragmentos — então agora falha limpo (com botão de retry) em vez de despejar 27–53 arquivos picotados.

**Adicionado:**

- Chave de log `dispatcher.youtube_skip_scraper` (PT/EN)
- Teste em `tests/test_dispatcher_integration.py` (falha do yt-dlp no YouTube não chama `scrape_fallback`)

## v1.2.21 — Proxy opcional para o TikTok (TIKTOK_PROXY)

**Major changes:**

- 🌐 **Nova config `TIKTOK_PROXY`** — roteia **só** as requisições do TikTok no yt-dlp por um proxy (o TikTok bloqueia IPs de servidor/VPN com WAF). Aplicado em `_apply_format_selection` apenas quando `platform.tiktok` e a env está setada; impersonation (chrome) e cookies logados continuam iguais. Aceita `http://` e `socks5://`. Inerte quando vazio — nenhuma mudança de comportamento sem configurar. Uso típico: um container gluetun com `HTTPPROXY=on` → `TIKTOK_PROXY=http://127.0.0.1:8888`.

**Adicionado:**

- Constante `TIKTOK_PROXY` em `config.py`; wiring em `downloaders/_ytdlp.py`
- Doc no `.env_example`/`.en`
- 3 testes em `tests/test_ytdlp_format_selection.py` (proxy setado só pro TikTok quando configurado; ignorado quando vazio; ignorado em outras plataformas)

**Nota:** o TikTok bloqueia muitas faixas de IP de VPN (inclusive ProtonVPN). Setar o proxy não garante o bypass — pode ser preciso trocar o país de saída do VPN até achar um IP aceito.

## v1.2.20 — Post de link do Reddit sempre re-despacha o link externo (notícia inclusa)

**Major changes:**

- 🔗 **Ajuste do comportamento do v1.2.19:** agora **todo** link externo de um post do Reddit é baixado **como se o próprio link tivesse sido enviado** — não só os "alvos conhecidos". Antes, link de notícia virava um card só com thumbnail + título; agora ele re-despacha `download_media` no link da notícia, que passa pelo fluxo normal (yt-dlp → scraper/extração de artigo). Resultado prático: um post-link pra uma matéria vem com a **imagem do artigo + título + corpo da notícia** (via Scraper Deep Search / trafilatura), igual a mandar o link da notícia direto pro bot.
- 🖼️ **Card de thumbnail (thumb + título + link) virou fallback:** só é usado se o re-despacho não trouxer **nada** (sem arquivos e sem legenda), garantindo que o usuário nunca fique sem resposta.
- Removido o `_is_known_media_target` (a distinção alvo-conhecido-vs-notícia não é mais necessária).

**Validado ponta a ponta:** post `r/Maromba/...fisiculturista...` → resolve pra `folha.uol.com.br` → yt-dlp "Unsupported URL" → scraper retorna a imagem do artigo + o corpo da matéria como legenda.

## v1.2.19 — Posts de link do Reddit: card de notícia ou re-despacho do alvo conhecido

**Major changes:**

- 🔗 **Post do Reddit que é só um link externo agora é tratado pelo destino, não pela thumbnail solta.** Antes, um post-link (ex: notícia) caía no `download_reddit_json` que baixava a imagem de preview e enviava com o título/link do Reddit. Agora o dispatcher, antes de baixar, resolve o link externo do post (`resolve_reddit_external_link`, via o mesmo JSON do Reddit — reaproveitado pra não buscar duas vezes) e decide:
  - **Alvo conhecido do mediaraven** (YouTube, Instagram, TikTok, X, Facebook, Threads, Kwai): **re-despacha** `download_media` no link interno — baixa a mídia como se aquele link tivesse sido enviado direto (com guarda de profundidade contra loop).
  - **Link de notícia / site genérico**: envia um **card** com a **thumbnail** do post + **título** + **link pra notícia** (não o link do Reddit). A legenda vem incluída por padrão (tratado como artigo).
- Mídia nativa do Reddit (imagens, galerias, vídeos, self-posts) segue exatamente o fluxo de antes — só links externos mudam de comportamento.

**Adicionado:**

- Helper puro `reddit_external_link(post_data)` em `downloaders/reddit_common.py` (classifica link externo vs mídia nativa)
- `resolve_reddit_external_link(url)` em `downloaders/reddit_json.py` (retorna `(link, post_data)`, reaproveitando o fetch); `download_reddit_json` aceita `post_data` pré-buscado
- `_is_known_media_target(url)` e `_reddit_news_card(...)` no dispatcher; `download_media` ganhou guarda de recursão `_depth`
- Mensagem `downloader_status.reddit_link_card` (PT/EN) e 3 chaves de log do dispatcher
- 10 testes (8 de `reddit_external_link` em `tests/test_reddit_common.py`, 2 de integração: re-despacho de alvo conhecido e card de notícia)

## v1.2.18 — TikTok: yt-dlp atualizado + cookies logados primeiro com impersonation

**Contexto:** o TikTok passou a bloquear o IP do servidor com WAF/captcha. O yt-dlp 2026.6.9 nem tentava o novo desafio do TikTok (falha determinística "Unexpected response from webpage request"), e o fallback do scraper só pegava um preview de 2s (não o vídeo real). Bloqueio de IP não se resolve 100% por código, mas dá pra maximizar a chance com uma sessão logada.

**Major changes:**

- ⬆️ **yt-dlp `2026.6.9` → `2026.7.4`.** A versão nova resolve o desafio WAF do TikTok (proof-of-work em Python nativo) — o 2026.6.9 não tinha esse suporte e falhava sempre.
- 🍪 **TikTok agora é um platform reconhecido e prioriza a sessão logada.** Adicionado `tiktok` ao `Platform`/`_PLATFORM_HOSTS` (`tiktok.com`, `vt.tiktok.com`, `vm.tiktok.com`). Para TikTok, `_attempt_order` tenta **`with_cookie` primeiro** (antes de `no_cookie`), e `_apply_format_selection` aplica **impersonation (curl_cffi chrome)** — sessão logada + fingerprint de browser é a melhor combinação pra passar pelo WAF. Só 2 tentativas (ambas impersonadas, cookie-first) pra não estourar rate-limit.

**⚠️ Ação necessária:** pra funcionar, é preciso **estar logado no TikTok no perfil do Firefox** que o bot usa (`FIREFOX_PROFILE_PATH`). O bot injeta esses cookies; sem uma sessão logada válida o WAF continua bloqueando.

**Adicionado:**

- 7 testes em `tests/test_ytdlp_format_selection.py` (detecção de host do TikTok, `_attempt_order` cookie-first, impersonation aplicada)

## v1.2.17 — Links `/share/` do Threads voltam a baixar

**Major changes:**

- 🧵 **Links de compartilhamento do Threads (`threads.com/share/XXXX`) voltam a baixar.** O formato novo de share não expõe o código do post na URL, então `_extract_post_code` (regex `/post/(...)`) falhava e o bot abortava com "Não consegui extrair código do post da URL" antes mesmo de carregar a página. O `/share/` não faz redirect HTTP (responde 200 e redireciona via JS), mas o Playwright — que o Threads já usa — segue o redirect: após carregar, `page.url` vira a URL canônica (`/@user/post/CODE`). **Correção:** `_fetch_html` agora também devolve a URL final, e o novo `_resolve_post_code` obtém o código na ordem url → URL final (pós-redirect) → `og:url` do HTML. Links `/@user/post/CODE` normais seguem funcionando igual. Validado ponta a ponta: um `/share/` real resolve pra `Db0CFC1jJmq` e extrai o vídeo.

**Adicionado:**

- `_resolve_post_code` e `_OG_URL_RE` em `downloaders/threads.py`; `_fetch_html` retorna `(html, final_url)`
- 4 testes de `_resolve_post_code` em `tests/test_threads.py` (url direta, URL final pós-share, fallback `og:url`, irresolvível)

## v1.2.16 — Detecta live em andamento e cancela o download

**Major changes:**

- 🔴 **Lives em andamento agora são detectadas e o download é cancelado.** O bot já fazia um pre-extract (`extract_info(download=False)`) antes de baixar; aproveitando isso, o novo `_live_reason(info)` (`downloaders/_ytdlp.py`) lê `live_status`/`is_live` do yt-dlp: `is_live`/`live_status=="is_live"` → `live_in_progress` (cancela); `live_status=="is_upcoming"` → `live_not_started` (barra também live agendada); `was_live`/`post_live`/`not_live` → segue normal (VOD de live encerrada continua baixável). Assim que a live é identificada, `_run_ytdlp_with_cookie_fallback` retorna o motivo **antes de tentar baixar** — o download de fato nem é iniciado. O dispatcher já trata `unrecoverable_reason`, então mostra a mensagem e pula os fallbacks. Motivo: baixar uma live em andamento trava/consome recursos sem nunca finalizar.
- 💬 Nova mensagem de status `🔴 Live em andamento. Download cancelado.` (PT/EN) e log `🔴 Live detectada (...); cancelando download.`

**Adicionado:**

- 10 casos de teste para `_live_reason` + teste async provando que o download (`_yt_dlp_extract`) não é chamado quando a live é detectada, em `tests/test_ytdlp_format_selection.py`

## v1.2.15 — Foto única do Instagram falhava (Instagrapi re-buscava pelo GraphQL público bloqueado)

**Major changes:**

- 📸 **Posts de foto única do Instagram voltam a baixar.** O bot já obtinha o `media_info` pela API privada autenticada (`i.instagram.com/api/v1/media/{pk}/info/`, funciona), mas pra foto única (`media_type == 1`) chamava `photo_download(media_pk)`, que internamente **re-busca os metadados pelo GraphQL público** (`media_info_gql`). O Instagram fechou esse endpoint público: ele agora responde `401 Unauthorized`, o instagrapi devolve `None` e o download estourava `AttributeError: 'NoneType' object has no attribute 'get'`. Resultado prático: o usuário mandava uma foto e recebia erro/"exige login" ou a capa do embed, mesmo com a conta logada. Vídeos e álbuns nunca foram afetados porque `video_download`/`album_download` usam a API privada (`media_info_v1`/`media_info`), não o GraphQL público — só o caminho de foto única usava `media_info_gql`.
- 🔧 **Correção:** foto única agora baixa via `photo_download_by_url(media_info.thumbnail_url)`, reusando o `media_info` que já temos da API privada — o re-fetch pelo GraphQL público bloqueado é eliminado. Validado ao vivo contra o post que falhava: baixa a imagem real (1311×1452 JPEG) em vez de erro.

**Adicionado:**

- `tests/test_instagram_instagrapi.py` — teste de regressão garantindo que foto única usa `photo_download_by_url` e nunca `photo_download(media_pk)`

## v1.2.14 — Reels do Instagram vinham como imagem (capa do embed) + atualização yt-dlp/instagrapi

**Major changes:**

- 📸 **Reels do Instagram voltam a vir como vídeo.** O endpoint de embed (`/embed/captioned/`) passou a devolver, pra vários reels, `is_video=true` mas **sem `video_url`** (só a capa em `display_url`/`display_resources`, `product_type=clips`). Em `_media_from_node` (`downloaders/instagram_embed.py`), como `is_video` era verdadeiro mas `video_url` vazio, o código **caía no branch de imagem e retornava a capa** — o embed tratava isso como sucesso e o dispatcher devolvia a imagem sem nunca tentar yt-dlp/Instagrapi (que pegam o vídeo). Corrigido: um nó marcado como vídeo nunca degrada pra capa — retorna vazio, o embed falha e o fallback assume. Confirmado: reels que vinham como `IG Embed (Imagem/Álbum)` agora são baixados em vídeo pelo yt-dlp.
- ⬆️ **yt-dlp `2026.3.17` → `2026.6.9` e instagrapi `2.3.0` → `2.16.0`.** As duas libs que dirigem a extração de IG/FB estavam defasadas (instagrapi 13 versões atrás). Validado: `pip check` limpo, yt-dlp extrai reels reais, todos os métodos do instagrapi usados pelo bot (`media_pk_from_url`, `media_info`, `photo_download`, `video_download`, `album_download`, `login`, `dump_settings`, `load_settings`) presentes na 2.16.0. Pillow `11.3.0` → `12.2.0` e requests `2.32.5` → `2.34.2` subiram como dependências transitivas do instagrapi.

**Adicionado:**

- Teste de regressão em `tests/test_instagram_embed.py` (nó de vídeo sem `video_url` não cai pra capa)

## v1.2.13 — Reels do Facebook falhavam por nome de arquivo longo (ENAMETOOLONG)

**Major changes:**

- 🐦 **Reels do Facebook (e qualquer vídeo de título longo) baixam corretamente de novo.** O `outtmpl` do yt-dlp usava `%(title)s [%(id)s].%(ext)s`; Reels do FB trazem a legenda inteira (300+ caracteres) como título, e mesmo com `restrictfilenames` o yt-dlp não limita o comprimento, então o nome estourava o limite de 255 bytes do filesystem e o download morria com `[Errno 36] File name too long`. Como o `base_opts` tem `ignoreerrors=True`, o erro era engolido em silêncio: nenhum arquivo, nenhuma exceção — as 4 tentativas do yt-dlp "falhavam", caía no scraper genérico, que devolvia thumbnails de UI (40x40/10x10) como `🕸️ Scraper Deep Search (Imagens)`. Resultado prático: usuário mandava um Reel e recebia imagens aleatórias em vez do vídeo. Corrigido truncando o título pra `%(title).150B` (150 bytes) — o sufixo `[id].ext` mantém o nome final em ~170 bytes, com folga sob 255. Vale pra todas as plataformas. A extração do yt-dlp sempre funcionou (formatos AV1 disponíveis); só o nome de saída quebrava.

**Adicionado:**

- 2 testes em `tests/test_ytdlp_format_selection.py` (outtmpl contém o truncamento; título de 600 chars gera nome ≤ 255 bytes via `YoutubeDL.prepare_filename`, preservando `[id].ext`)

## v1.2.12 — Ignorar domínios silenciosamente (IGNORED_DOMAINS)

**Major changes:**

- 🔇 **Nova config `IGNORED_DOMAINS` pra ignorar domínios sem nenhum feedback no chat.** Links de domínios na lista passam batido: sem reação (emoji), sem prompt de download, sem mensagem de status — apenas ficam registrados no `bot.log` (`handlers.dominio_ignorado`). O filtro roda em `_extract_urls_from_update` (em `handlers.py`), logo após o dedup e **antes** do limite `MAX_URLS_PER_MESSAGE`, então domínios ignorados não consomem a cota de URLs. Se todas as URLs da mensagem forem ignoradas, o `handle_message` retorna cedo e nem a reação é setada.
- ⚙️ **Configurável global ou por chat/usuário.** Global via `.env` (`IGNORED_DOMAINS=twitch.tv,spotify.com`) ou por chat/user via `customization.json` (`"IGNORED_DOMAINS": ["twitch.tv"]`), respeitando a precedência usual user > chat > default > .env.
- 🌐 **Match por domínio exato e subdomínios.** Nova função pura `is_ignored_domain` em `utils.py` compara via `hostname` (case-insensitive, ignora porta): `example.com` também ignora `www.example.com`/`m.example.com`, mas `example.com.evil.com` não casa.

**Adicionado:**

- Constante `IGNORED_DOMAINS` em `config.py` (CSV do `.env`)
- Função `is_ignored_domain` em `utils.py`
- Chave de log `handlers.dominio_ignorado` (PT/EN)
- Doc do campo `IGNORED_DOMAINS` em `customization.example.json`/`.en.json` e `.env_example`/`.en`
- 6 testes de `is_ignored_domain` em `tests/test_utils_helpers.py` e 4 testes de filtragem em `tests/test_url_extraction.py`

## v1.2.11 — X devolvia vídeo de reply em post de imagem + Instagram tenta Instagrapi autenticado em erro de login

**Major changes:**

- 🐦 **X: post de imagem retornava vídeo de uma reply da mesma thread.** Causa raiz tripla em `downloaders/x.py`: (1) `_tweet_ids` incluía `conversation_id_str`, que é compartilhado por TODAS as replies da conversa — então qualquer reply "casava" com o ID do tweet alvo na resposta `TweetDetail` do GraphQL; (2) `_extract_from_data` só lia `tweet["extended_entities"]`, mas no GraphQL a mídia do tweet focal fica em `tweet["legacy"]["extended_entities"]`, então ficava vazio e caía num fallback frágil; (3) `_walk_for_tweet_media` tinha guarda permissiva `if not ids or tweet_id in ids` que pegava a mídia do primeiro objeto que casasse (uma reply com vídeo) ou que não tivesse ID nenhum. Correção: identidade agora é só `id_str`/`rest_id`/`id` (sem `conversation_id_str`), extração lê também `legacy.extended_entities`, e o walk exige match estrito de ID. Confirmado pelos logs: o link reportado vinha de guest vazio → Playwright autenticado → vídeo de reply.
- 🔑 **Instagram: erro de login do yt-dlp não desiste mais sem tentar a sessão autenticada.** Quando o yt-dlp reporta `sign_in_required`/`age_restricted`/`unavailable` pra Instagram (conteúdo sensível/restrição de idade), o dispatcher agora tenta `download_instagram_instagrapi` (sessão logada de `ig_session.json`) antes de desistir, em vez de abortar no short-circuit `unrecoverable_reason`. O scraper genérico continua pulado nesses casos (preserva o motivo original do short-circuit: não pegar o logo da página de erro). Razões genuinamente irrecuperáveis (`private`/`removed`/etc.) continuam abortando direto.

**Adicionado:**

- Constante `_IG_AUTH_RETRY_REASONS = {"sign_in_required", "age_restricted", "unavailable"}` em `downloaders/dispatcher.py`
- Chave de log `dispatcher.unrecoverable_try_instagrapi` (PT/EN)
- 2 testes de regressão em `tests/test_x.py` (foto focal + reply com vídeo na mesma conversa → extrai a foto; walk ignora reply da mesma conversa)
- 3 testes em `tests/test_dispatcher_integration.py` (IG `sign_in_required` → tenta Instagrapi e dá sucesso; Instagrapi vazio → desiste sem scraper; IG `private` → não tenta Instagrapi)

## v1.2.10 — Handler dedicado pro Facebook (carrosséis via gallery-dl) + validação de uploader no yt-dlp + ordem unificada de tentativas + cobertura ampliada do classifier

**Major changes:**

- 📘 **Novo handler dedicado pra Facebook em `downloaders/facebook.py`**. Pra qualquer link FB, o dispatcher agora tenta `gallery-dl` primeiro (com cookies do Firefox) — gallery-dl extrai carrosséis de imagens corretamente via API SSR, sem cair no scraping da timeline. Se gallery-dl achar arquivos → usa direto, status `📘 Facebook Gallery [N arquivos]`. Caso contrário, segue pro fluxo normal (yt-dlp pra vídeo). Confirmado: post de carrossel de 20 imagens que retornava vídeo errado agora vem completo (~250KB cada).
- 🛡️ **Validação `facebook_owner_mismatch` após yt-dlp success pra FB.** O extractor do Facebook no yt-dlp tem bug: quando o post original é só imagens, ele "encontra" qualquer vídeo embedado na página (sponsored/recomendação/comentário) e retorna como "sucesso". Resultado prático: user mandava link de carrossel e recebia vídeo aleatório de outro user. Agora: comparamos o `uploader_id` retornado pelo yt-dlp com o user_id numérico da URL (`facebook.com/<UID>/posts/...`). Se não baterem, descartamos o resultado e seguimos pros fallbacks.
- 🍪 **`_gallery_dl_run` agora injeta cookies do Firefox** (via `gdl_config.set(('extractor',), 'cookies', ('firefox', profile))`). Necessário pro FB; sem efeito colateral em outras plataformas (Pinterest/Imgur já funcionavam sem auth).
- 🖼️ **Carrosséis de imagens do Facebook agora baixam mesmo sem login.** A heurística `_drop_facebook_image_only` (introduzida no v1.0.x pra evitar 50+ thumbnails de UI quando user mandava link de vídeo) era agressiva demais: descartava QUALQUER post FB sem `.mp4` como "lixo de UI", o que incluía posts legítimos de fotos/carrosséis. **Função removida.** No lugar, expandi `is_junk_url` com hosts/paths conhecidos de UI do FB/Reddit (`static.xx.fbcdn.net`, `static.cdninstagram.com`, `styles.redditmedia.com`, `alb.reddit.com`, `id.rlcdn.com`, `/rsrc.php/`, `/safe_image.php`, `headshot`, `snoovatar`, `_profile`, `communityicon`, `profileicon`, `awardicon`) — agora UI é filtrada na fonte (antes do download) e imagens reais de posts passam.
- 🔁 **`_expand_attempts_with_impersonate` agora aplica o padrão "no_imp primeiro, imp como fallback" pra Facebook/Instagram também** (antes era só Reddit). Resultado pra FB/IG/Reddit: 4 tentativas `[no_cookie+no_imp, with_cookie+no_imp, no_cookie+imp, with_cookie+imp]`. Pra YouTube/outros (que não usam impersonate): 2 tentativas como antes. Motivo: testes manuais com Facebook mostraram que `impersonate=chrome` faz o FB devolver SPA pesada que yt-dlp não consegue parsear (`"Cannot parse data"`), enquanto sem impersonate retorna erro semântico (`"No video formats found"`) que o classifier pode reconhecer e responder corretamente.
- 🛑 **Facebook com "This video is only available for registered users" não estava sendo classificado pelo v1.2.9** — caía pro scraper e a heurística descartava tudo. Adicionados padrões: `only available for registered users`, `only available for registered`, `only available to registered`, `use --cookies`, `requires login`, `please log in`. Outros patterns novos: `this account is private` → `private`, `restricted to subscribers` → `members_only`, `this content isn't available`/`this tweet is unavailable`/`no video formats found`/`no media found`/`cannot parse data` → `unavailable`, `this video is no longer available` → `removed`, `too many requests` → `rate_limited`.

**Removido:**

- Função `_drop_facebook_image_only` em `downloaders/fallback.py` (e 4 call sites)
- Chave de log `fallback.facebook_image_only_dropped` (PT/EN)

**Adicionado:**

- Novo módulo `downloaders/facebook.py` com `download_facebook_gallery` e `facebook_owner_mismatch`
- Mensagem UI `downloader_status.facebook_gallery` (PT/EN) e 2 chaves de log `facebook.tentando_gallery_dl`, `facebook.gallery_dl_ok`, `dispatcher.facebook_owner_mismatch`
- 5 testes em `tests/test_facebook.py` (mismatch detection: no info / match / mismatch / share URL / sem uploader_id)
- 4 testes em `tests/test_ytdlp_format_selection.py` (registered users / use --cookies / 429 / private account)
- Teste `test_expand_attempts_facebook_and_instagram_also_try_no_imp_first` em `tests/test_ytdlp_format_selection.py`
- 3 testes em `tests/test_scrape_helpers.py` cobrindo os novos junk patterns (FB static, Reddit UI, real FB post image)

## v1.2.9 — Detecta erros não recuperáveis do yt-dlp (privado/removido/geo/etc.) e pula fallbacks

**Major changes:**

- 🛑 **Vídeo privado/removido/geo-bloqueado/etc. agora retorna mensagem clara** em vez de cair pro scraper genérico (que pegava o logo do YouTube/Google da página de erro como se fosse a mídia). Antes: link de vídeo privado → yt-dlp falha → scraper raspa página → manda logo do Google pro chat. Agora: yt-dlp captura o erro, classifica como `private`/`removed`/`geo_blocked`/`members_only`/`age_restricted`/`sign_in_required`/`live_not_started`/`unavailable`/`rate_limited`, e o dispatcher para na hora com mensagem específica.
- 🪵 **Captura de erros do yt-dlp via `logger=` no opts** em vez de mexer com `ignoreerrors`. Cada chamada de extração agora retorna `(info, error_messages)` quando `capture_errors=True`. O classifier compara contra 21 padrões conhecidos (case-insensitive) e retorna a categoria.

**Refatorações:**

- `_yt_dlp_extract` aceita `capture_errors: bool = False`; quando True retorna tupla `(info, errors)` em vez de só `info`
- Novo helper `_classify_ytdlp_errors(error_messages) -> Optional[str]` em `downloaders/_ytdlp.py` com padrões pra: `private`, `members_only`, `age_restricted`, `geo_blocked`, `removed`, `live_not_started`, `unavailable`, `sign_in_required`, `rate_limited`
- `_run_ytdlp_with_cookie_fallback` agora retorna `(files, info, unrecoverable_reason)`. Em vez de só listar arquivos, acumula erros de todas as tentativas e classifica no final
- `dispatcher.download_media` checa `unrecoverable_reason` antes de chamar fallbacks; se setado, retorna `msg("downloader_status.ytdlp_{reason}")` direto

**Adicionado:**

- 9 mensagens UI (PT/EN) em `downloader_status.ytdlp_{private,unavailable,removed,geo_blocked,members_only,age_restricted,sign_in_required,live_not_started,rate_limited}`
- 2 chaves de log: `_ytdlp.unrecoverable_reason`, `dispatcher.unrecoverable_skip_fallbacks`
- 9 testes em `tests/test_ytdlp_format_selection.py` (classifier por categoria + fallback None) + 1 teste de integração em `tests/test_dispatcher_integration.py`

## v1.2.8 — Threads: extrai mídia de `linked_inline_media` (posts media_type=19)

**Major changes:**

- 🧵 **Posts Threads com `media_type=19` (audio-augmented / format novo) tinham a mídia em `text_post_app_info.linked_inline_media`**, campo que `_extract_media` não cobria. O post tem `video_versions` no nível raiz como falsy/empty e `image_versions2.candidates: []`, daí o bot caía no branch "sem mídia, só caption" e respondia com texto. Agora `_extract_media` chama-se recursivamente em `linked_inline_media` (mesma estrutura: `carousel_media`/`video_versions`/`image_versions2`) antes do fallback de `share_info.quoted_post`. Mídia direta continua tendo precedência.

**Adicionado:**

- 3 testes em `tests/test_threads.py` (`linked_inline_media` com vídeo, com imagem, precedência da mídia direta)

## v1.2.7 — AIORateLimiter agora retenta de verdade (max_retries=3)

**Major changes:**

- 🐛 **No v1.2.4 o `AIORateLimiter` foi adicionado, mas com `max_retries=0` (default).** Resultado: ao bater em flood control (`Retry in N seconds`), o limiter só logava `Rate limit hit after maximum of 0 retries` e relançava a `RetryAfter`, fazendo a request original falhar e o handler explodir — exatamente o sintoma que o v1.2.4 tentou corrigir. O status_msg ficava travado em "baixando" porque o `_safe_edit` para "internal_error" também caía no mesmo flood. Agora `AIORateLimiter(max_retries=3)`: o limiter espera o `Retry-After` informado pelo Telegram e retenta até 3 vezes automaticamente.

## v1.2.6 — Reddit: tentativa sem impersonate primeiro (corrige IP-block)

**Major changes:**

- 🐛 **Reddit estava retornando `Your IP address is unable to access the Reddit API` quando o yt-dlp era chamado com `impersonate=ImpersonateTarget('chrome')`** (ativado pra Reddit no v1.0.x). Resultado: `bestvideo+bestaudio/best` falhava em qualquer post de vídeo, e o bot caía no scraper genérico que pegava avatares/ícones de comunidade em vez do vídeo. Agora, pra Reddit, as tentativas são expandidas pra `[no_cookie+no_imp, with_cookie+no_imp, no_cookie+imp, with_cookie+imp]` — o impersonate vira fallback em vez de default. Facebook/Instagram não mudam (continuam sempre com impersonate).
- 🧪 Confirmado manualmente: sem impersonate, yt-dlp baixa o vídeo do Reddit normalmente (~5 MB em 2s); com impersonate, retorna IP-block.

**Refatorações:**

- `_apply_format_selection` ganhou parâmetro `use_impersonate: bool = True` em `downloaders/_ytdlp.py` — quando False, faz `opts.pop('impersonate', None)` (gating só de adicionar não basta porque o dispatcher injeta impersonate em `base_opts` antes do loop, e o `current_opts.copy()` herda)
- Novo helper `_expand_attempts_with_impersonate(attempts, platform)` — pra Reddit retorna `[(m, False) for m in attempts] + [(m, True) for m in attempts]`; pra outros mantém `[(m, True) for m in attempts]`
- Loop principal de `_run_ytdlp_with_cookie_fallback` agora itera `(mode, use_imp)`, chama `_apply_format_selection` em toda iteração (não só quando há info do pre-extract — senão o gating é pulado), e pula `_pre_extract` pra Reddit (Reddit usa `format='bestvideo+bestaudio/best'` direto)
- Log da tentativa inclui sufixo `_imp`/`_noimp` no `mode` pra diagnose

**Adicionado:**

- 6 testes em `tests/test_ytdlp_format_selection.py` (impersonate gating + pop quando herdado + expand_attempts)

## v1.2.5 — Conversão automática de vídeo pra MP4 quando necessário

**Major changes:**

- 🎞️ **Vídeos em formato incompatível com player nativo do Telegram são convertidos pra MP4 antes de enviar.** Telegram só garante player de streaming pra MP4 H.264+AAC ([Bot API docs](https://core.telegram.org/bots/api#sendvideo): "other formats may be sent as Document"). Antes, `.webm`/`.mkv`/`.avi`/`.flv` caíam como documento sem player; agora viram MP4 antes do `send_video`.
- 🧠 **Estratégia smart (probe + remux/re-encode mínimo)**: `ffprobe` detecta vcodec/acodec do arquivo. Se já for H.264 → `-c:v copy` (instantâneo, sem perda). Se for AAC → `-c:a copy`. Caso contrário, re-encode só do stream incompatível. Se o remux falhar (codec não cabe em MP4 container), faz fallback automático pra re-encode completo.
- ✅ Extensões compatíveis (`.mp4`/`.m4v`/`.mov`) passam direto sem ffprobe nem ffmpeg.

**Adicionado:**

- `state.FFPROBE_PATH` + `init_ffmpeg` agora descobre tanto `ffmpeg` quanto `ffprobe` no PATH em `lifecycle/startup.py`
- `is_telegram_compatible_video_ext`, `async_ffprobe_codecs`, `async_ensure_telegram_video` em `utils.py`
- Helper `_ensure_video` em `telegram_io.py` (single-file e media_group)
- Config `VIDEO_CONVERT_TIMEOUT` (default 900s) em `config.py` + `customization.example.{json,en.json}`
- 13 chaves de log novas (PT/EN): `startup.ffprobe_*`, `utils.ffprobe_*`, `utils.video_convert_*`
- 11 testes em `tests/test_video_convert.py` + 4 testes em `tests/test_telegram_io_timeouts.py`

## v1.2.4 — Rate limiter pra evitar Flood control exceeded

**Major changes:**

- 🚦 **`AIORateLimiter` ativado** no `ApplicationBuilder`. Antes, quando Telegram retornava `RetryAfter: Flood control exceeded. Retry in N seconds` (em `edit_text`/`send_*`), a exception subia sem retry, e a request do user falhava. Agora o PTB respeita `Retry-After` em todos os requests automaticamente — espera N+ε e tenta de novo, sem propagar erro pro handler.

**Adicionado:**

- `builder.rate_limiter(AIORateLimiter())` em `mediaraven.py`
- `python-telegram-bot[rate-limiter]==22.7` em `requirements.txt` (puxa `aiolimiter` como dependência transitiva)

## v1.2.3 — GIFs vão como animação (não vídeo bugado)

**Major changes:**

- 🎞️ **GIFs agora vão via `send_animation`** em vez de `send_video`. Telegram tratava GIF como vídeo (sem autoplay, sem loop, com player feio). Com `send_animation`, vira animação nativa.
- 🎞️ **GIF é convertido pra MP4 (H.264) com ffmpeg antes de enviar**. Telegram converte GIF cru com perda de qualidade e renderiza pequeno; MP4 silencioso é o formato nativo de "GIF animado" do Telegram (mesmo que o cliente oficial usa) — qualidade muito melhor e tamanho cheio.
- 📐 Dimensões (`width`/`height`) extraídas do GIF original via PIL e passadas pro `send_animation` — garante renderização no tamanho correto mesmo quando ffmpeg não está disponível.

**Adicionado:**

- `_ANIMATION_EXTS_DEFAULT = ('.gif',)` em `config.py` (extensível via env `ANIMATION_EXTS_EXTRA`); `.gif` removido de `VIDEO_EXTS_DEFAULT`
- `async_gif_to_mp4(input_path, output_path, timeout=60)` em `utils.py` (ffmpeg `-c:v libx264 -pix_fmt yuv420p -an -movflags +faststart`)
- Helper `_get_image_dims` + branch `send_animation` em `telegram_io.py` (com fallback pro `.gif` original se ffmpeg falhar)
- 6 chaves de log `utils.gif_to_mp4_*` em PT/EN
- 3 testes em `tests/test_telegram_io_timeouts.py` (rota gif→animation, conversão bem-sucedida, fallback quando ffmpeg falha)

## v1.2.2 — Cap dinâmico pra HLS / lives finalizados do YouTube

**Major changes:**

- 📺 **Live finalizado do YouTube agora cabe**: lives que terminaram (`live_status: post_live`) só expõem formats HLS sem `filesize_approx` declarado. Antes o seletor caía no `best` e pegava 1094p (~3.8 GB pra 1h53min) → `File_parts_invalid` no upload. Agora, **pre-extract** descobre `duration` + formats e:
    - Aplica **cap dinâmico de bitrate** `[tbr<=N]` calculado por `(TELEGRAM_MAX_UPLOAD_MB × 8 × 1024) ÷ duration_s × 0.95`. Pra um live de 1h53min com cap 2 GB → `tbr<=2289 kbps`.
    - Detecta **HLS-only** (todos formats com vídeo são `m3u8_native`/`http_dash_segments`) e aplica cap conservador de altura via novo config `YTDLP_HLS_MAX_HEIGHT` (default 720).
- 🎯 **Format selector ordenado em tiers**: 1) DASH com filesize cap → 2) progressive com filesize cap → 3) progressive com tbr cap → 4) fallback puro. Garante que VOD normal continua escolhendo melhor qualidade dentro do limite.

**Refatorações:**

- Helpers extraídos em `downloaders/_ytdlp.py`: `_calc_max_tbr_kbps`, `_is_hls_only`, `_build_format_selector`, `_pre_extract`.
- `_apply_format_selection` aceita `info: Optional[dict]` e ajusta seletor dinamicamente.
- `_run_ytdlp_with_cookie_fallback` aceita `platform` opcional; quando passado, faz pre-extract por attempt (cookie/no-cookie) e re-aplica format selection com info real.

**Adicionado:**

- Config `YTDLP_HLS_MAX_HEIGHT` (default 720) em `customization.example.{json,en.json}`
- 3 chaves de log novas: `_ytdlp.hls_only_height_cap`, `_ytdlp.tbr_cap`, `_ytdlp.pre_extract_falhou`
- 15 testes em `tests/test_ytdlp_format_selection.py`

## v1.2.1 — Cap de upload pra evitar File_parts_invalid

**Major changes:**

- 📤 **Cap de tamanho no yt-dlp**: novo config `TELEGRAM_MAX_UPLOAD_MB` (default 2000) aplicado como `[filesize_approx<...M]` no seletor de formato. Antes, vídeos longos do YouTube em 1440p60 podiam dar > 2 GB e falhar com `BadRequest: File_parts_invalid` no upload (limite hard do Telegram pra bots; **Premium não afeta bots** — [tdlib/telegram-bot-api#583](https://github.com/tdlib/telegram-bot-api/issues/583)). Agora o seletor reserva ~100 MB pro stream de áudio + container e cai pra 1080p quando 1440p ultrapassaria o cap.
- 📤 **PTB local_mode**: `telegram_io.send_downloaded_media` agora passa o **path como string** em vez de file handle. Com servidor `telegram-bot-api --local`, PTB envia `file:///path` URI e o servidor lê do filesystem direto, sem multipart upload — evita timeouts em arquivos grandes mas dentro do limite. Documentação do `parse_file_input` confirma esse caminho (telegram/_utils/files.py:145-149).
- 📚 **Doc corrigida**: README/site/`.env_example` mencionavam "4 GB com Premium" — falso. Bots não podem ser Premium; o limite é 2 GB sempre.

**Refatorações:**

- `telegram_io.py` aplica `TELEGRAM_UPLOAD_TIMEOUT` em `read_timeout`/`write_timeout`/`connect_timeout` no path single-file (antes só o media_group aplicava).
- `_apply_format_selection` em `downloaders/_ytdlp.py` e `download_with_ytdlp_generic` em `downloaders/fallback.py` montam seletor com cap de filesize.

**Adicionado:**

- Config `TELEGRAM_MAX_UPLOAD_MB` em `customization.example.json` + `.example.en.json` (default 2000, min 50, max 2000)
- 5 testes em `tests/test_telegram_io_timeouts.py`

## v1.2.0 — Pinterest, Kwai e captions em chunks

**Maiores mudanças:**

- 📌 **Pinterest**: links de pin (`pin.it/XXX`, `pinterest.com/pin/<id>`, regionais como `br.pinterest.com`) agora baixam só a mídia do pin via filtro `og:image`/`og:video`/JSON-LD com cap=1. Antes vinham 60+ imagens recomendadas da página.
- 🎬 **Kwai / SnackVideo**: shortlinks (`kwai-video.com/p/XXX`, `s.kw.ai`, `snackvideo.com/in`) resolvidos antes do yt-dlp; query string de tracking removida pra evitar erro `File name too long` no ID gerado pelo generic extractor. Hosts cobertos: `kwai-video.com`, `kwai.com`, `m.kwai.com`, `kw.ai`, `s.kw.ai`, `snackvideo.com`, `snackvideo.in`.
- ✂️ **Captions longas em chunks**: caption acima de 1024 chars não é mais truncada. A mídia vai sem caption e o texto completo é enviado em chunks de até 4096 chars (separadores preferidos: `\n\n` > `\n` > `". "` > `" "`). Caption que cabe em 1024 segue sendo colada na mídia normalmente. Sem duplicação de texto.
- 📰 **Filtro de mídia em artigos**: quando um artigo é detectado por trafilatura, só `og:image`/`og:video`/JSON-LD são considerados (cap=1), em vez de todas as imagens scrapadas. Antes vinham banners, ads, related articles.

**Refatorações:**

- `_build_caption` agora retorna tupla `(short, full)` propagada por todos os downloaders (Threads, X, Reddit, Instagram, Instagram Embed, fallback). `short` ≤ 1024, `full` sem truncamento.
- Novo helper `chunk_html_text(text, limit)` em `utils.py` quebra texto preservando limites semânticos (parágrafo > linha > frase > palavra).
- `_send_text_in_chunks` em `handlers.py` envia chunks em sequência com delay configurável.

**Adicionado:**

- `_is_pinterest()` em `downloaders/fallback.py`
- `_is_kwai_host()` + `_resolve_kwai_url()` em `downloaders/_platform.py`
- 4 chaves de log novas: `fallback.pinterest_media_filtered`, `_platform.resolvendo_kwai`, `_platform.kwai_resolvido`, `_platform.falha_ao_resolver_kwai`
- 16 testes novos: `tests/test_fallback_pinterest.py` (7), `tests/test_kwai_resolver.py` (9)
- 6 testes novos pra `chunk_html_text` em `tests/test_utils_helpers.py`

## v1.1.0 — Customização granular + extração de artigo + bypass de paywall

**Maiores mudanças:**

- 🎚️ **42 configs customizáveis por chat e por usuário** via `customization.json`. Precedência `user > chat > default > .env`. Inclui timeouts, defaults de prompt, qualidade, scraper, caption, plataformas. Helper `cfg(key)` + ContextVar `request_context` permitem lookup transparente sem propagar IDs.
- 🌐 **180+ strings de log customizáveis** via `log_messages.json` (separado das mensagens UI). Helper `lmsg(key, **kw)` com fallback graceful pra keys ausentes.
- 🔒 **Bypass de paywall soft** (Googlebot UA + archive.ph) ativável via `SCRAPE_PAYWALL_BYPASS=yes`. Cobre NYT, Folha, FT, Estadão, etc.
- 📰 **Extração de artigo via trafilatura** como caption. Detecta automaticamente em qualquer URL com >= 300 chars de texto. Prompt opt-in dedicado (`ASK_ARTICLE_*`).
- 📝 **Posts só de texto** (Threads, X) viram mensagem de texto formatada (`📄 @user` + corpo + link), em vez de "falha".
- 🌍 **Documentação bilíngue PT/EN** + site de docs com MkDocs Material.
- 🛡️ **`ALLOW_ALL`** env pra rodar como bot público (whitelist ignorada).

**Refatorações:**

- `_build_caption` redesenhado pra ter `uploader` + `title` separados. YT Shorts detectados (não duplicam título no body). Threads/X agora usam `@username` no header.
- Scraper genérico paraleliza HTTP fast path + Playwright deep scrape (`asyncio.gather`).
- Logs com line numbers (`%(name)s:%(lineno)d`) + libs barulhentas silenciadas (httpx, urllib3, playwright, etc.).
- `exc_info=True` em ~10 catches de exceções fatais — stack traces preservados no log.
- Removido `MIN_CONTENT_LENGTH_BYTES` (filtro de 20KB nukava avatares legítimos).

**Adicionado:**

- `version.py` (`__version__ = "1.1.0"`)
- `customization.example.json` + `.example.en.json` (PT/EN, com `_doc_KEY` inline)
- `log_messages.example.json` + `.example.en.json`
- `messages.example.en.json`
- `.env_example.en`
- `README.en.md`
- `gallery-dl` como tier 3 do scraper
- `trafilatura` como dependência (extração de artigo)
- 5 badges adicionais no README (gallery-dl, trafilatura, instagrapi, curl-cffi, ffmpeg)

**Removido:**

- Envs `PROMPT_*_OFF_CHATS / ON_USERS / OFF_USERS` (substituídas por `PROMPT_*_ENABLED` no `customization.json`)
- 25+ envs movidas pro `customization.json` (todas as ASK_*, SCRAPE_*, MEDIA_GROUP_*, etc.)

## v1.0.0 — Lançamento inicial

- Bot do Telegram com Bot API local
- Plataformas: YouTube, Instagram, Reddit, Threads, X, Facebook
- Scraper genérico em cascata (HTTP + yt-dlp generic + gallery-dl + Playwright)
- Mensagens 100% customizáveis via `messages.json`
- Whitelist por chat e por usuário
- ~80 envs de tuning
