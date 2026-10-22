# Reddit

Reddit tem **dois caminhos** dedicados:

## 1. Reddit JSON (`reddit_json.py`)

Adiciona `.json?raw_json=1` no fim da URL e parseia. Cobre:

- ✅ Posts de imagem única
- ✅ Galerias (`media_metadata` + `gallery_data`)
- ✅ Reposts de outras subs
- ❌ Vídeos (delega pro yt-dlp porque DASH precisa de merge)
- ❌ Posts NSFW sem login → cai no Playwright
- ❌ Spoilers blurred → cai no Playwright

Cookies do Firefox são injetados na sessão `aiohttp` automaticamente quando disponíveis.

### Página do post (quando a API JSON dá 403)

Desde **21/10/2026** a API JSON responde `403 Blocked` pra anônimo — de IP residencial ou de datacenter, com ou sem cookies — e o yt-dlp cai em *"Account authentication is required"*. A página do post ainda abre, e o mesmo `reddit_json.py` passa a lê-la:

1. **Digital TLS de navegador:** o GET sai pelo `curl_cffi` (`impersonate="firefox"`); com `aiohttp` o Reddit devolve 403 mesmo resolvendo o desafio.
2. **Desafio JS:** a primeira resposta é um form oculto e um script `(async e=>e+e)("<semente>")`. O bot dobra a semente e reenvia o form por GET (`solution`, `js_challenge`, `jsc_token`, `jsc_orig_r`), recebendo a página completa.
3. **`<shreddit-post>`:** de lá saem `post-title`, `post-type` e `content-href`:
    - imagem/galeria → as URLs `i.redd.it` do corpo do post, na ordem (avatares e ícones ficam de fora)
    - vídeo → o `src` do `<shreddit-player>` do post (HLS), que o dispatcher entrega direto pro yt-dlp
    - crosspost → `content-href` relativo ao post original (vira URL absoluta); o vídeo está na própria página
    - sem `post-type` → usa o `content-href` se for imagem
4. **Link `/s/` do app:** o Reddit redireciona com o slug codificado duas vezes (`hist%25C3%25B3ria`) e a página não acha o post; o bot decodifica antes de abrir.
5. **Mídia apagada:** se a imagem dá 404 no `i.redd.it`, a resposta é `downloader_status.reddit_media_removed` (*"🗑️ A mídia desse post foi removida do Reddit."*), sem passar pelo yt-dlp.

## 2. Reddit Playwright (`reddit_playwright.py`)

Quando o JSON falha (NSFW gate, spoilers, "no preview"), abre `old.reddit.com` no Playwright:

> ⚠️ Desde out/2026 o `old.reddit.com` manda anônimo pro login (`reason=lor2`); esse caminho só serve com cookies de sessão logada.

- ✅ Clica no botão NSFW automaticamente
- ✅ Remove blur de spoilers (incluindo Shadow DOM)
- ✅ Extrai mídia da Shadow Tree
- ❌ Vídeos (mesmo motivo: DASH)

## Configurações relevantes

| Chave | Default | O que faz |
|---|---|---|
| `REDDIT_JSON_UA` | UA do Firefox 123 | UA usado na API JSON. Reddit detecta UAs de bot — use um realista. |

## Caption

Vem de `title` + `selftext`:

```
📄 Título do post
Self-text aqui (se houver)...

🔗 Link Original
```

Username/subreddit não estão na caption hoje (poderia adicionar — abrir issue se quiser).

## Vídeos do Reddit

URL como `v.redd.it/xxx` ou post com `is_video=true` → o `reddit_json` detecta e **retorna vazio de propósito**, fazendo o dispatcher cair no `yt-dlp`. O yt-dlp baixa o stream DASH (vídeo + áudio separados) e mixa.

Caption do vídeo vem do `info_dict` do yt-dlp (title + description).

Quando o post veio da página (API JSON bloqueada), o yt-dlp recebe a URL HLS do `<shreddit-player>` em vez do link do post, e a caption usa o título do post.

## NSFW

Bot consegue baixar NSFW se você tem cookies do Firefox de uma sessão logada com NSFW habilitado nas preferências do Reddit. Sem cookies, o `reddit_playwright` clica no botão NSFW automaticamente como fallback.

## Falhas comuns

- **403 / "blocked"** na API JSON → esperado desde 21/10/2026; o bot lê a página do post (acima). Se a página também der 403, confira se o desafio JS mudou de formato (log `reddit_json.usando_pagina_html` seguido de erro).
- **"🗑️ A mídia desse post foi removida do Reddit."** → a imagem foi apagada (404 no `i.redd.it`); não há o que baixar.
- **Galeria com algumas imagens faltando** → API às vezes retorna `media_metadata` parcial. Bot usa o que veio.
- **`v.redd.it` retorna sem áudio** → yt-dlp + ffmpeg deveriam mixar. Se não, ffmpeg não tá no PATH ou DASH falhou. Ative `LOG_LEVEL=DEBUG`.
