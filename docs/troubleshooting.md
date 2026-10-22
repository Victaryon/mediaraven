# Solução de problemas

## Erros de configuração

### `BASE_DOWNLOAD_DIR deve ser um caminho absoluto`

O bot rejeita paths relativos no boot. Use:

- Linux/macOS: `BASE_DOWNLOAD_DIR=/mnt/storage/mediaraven`
- Windows: `BASE_DOWNLOAD_DIR=C:/mediaraven/downloads` (barras normais, não invertidas)

### `LOCAL_API_HOST não configurado no .env`

Você precisa do servidor Bot API local rodando + `LOCAL_API_HOST=host:port` apontando pra ele. Detalhes em [Configuração](getting-started/config.md#1-bot-api-local-obrigatorio).

### `Token não configurado`

Falta `TELEGRAM_BOT_TOKEN` no `.env`. Pegue o token do @BotFather.

## Bot não responde

### Em chat privado, mas responde em grupo

Falta autorização. Verifique:

- `ALLOWED_USER_IDS` contém seu user ID (de @userinfobot)
- ou `ALLOWED_CHAT_ID` contém o ID do chat
- ou `ALLOW_ALL=yes` (cuidado: bot público)

### Em grupo

- **Group Privacy** desligado no @BotFather (Bot Settings → Group Privacy → OFF)
- Bot adicionado ao grupo (não é só o handle no chat)
- `ALLOWED_CHAT_ID` contém o ID do grupo (`-100...` pra supergrupos, `-...` pra grupos comuns)

### Sem erros aparentes

Cheque o log: `tail -f bot.log`. Se "📥 Iniciando download" aparece mas nada vem, é problema do downloader específico. Se nem isso aparece, o handler não foi disparado — confira whitelist.

## Erros do downloader

### `Invalid file http url specified`

Bot API local não tá acessível. Confira:

- Container Docker do Bot API tá rodando (`docker ps`)
- `LOCAL_API_HOST` aponta pro host:port certo
- Porta 8081 não tá em uso por outro processo

### `ffmpeg não encontrado`

Posts do IG com música externa precisam de ffmpeg pra mixar áudio + foto. Reddit videos precisam pra mixar DASH.

```bash
sudo apt install ffmpeg              # Linux
brew install ffmpeg                  # macOS
choco install ffmpeg                 # Windows
```

### Instagram pede login / challenge

`API web do Instagram falhou` ou `Sem sessão do Instagram no Firefox` no log. Possíveis causas:

- A sessão do Instagram no Firefox caiu (troca de senha, logout, recuperação de conta)
- Conta foi sinalizada por atividade suspeita

Solução: abra o Firefox do perfil em `FIREFOX_PROFILE_PATH` e logue no Instagram de novo. O bot lê os cookies do disco — não precisa reiniciar.

Se ainda falhar, use VPN ou aguarde algumas horas. Em casos persistentes, troque a conta — IG bloqueia contas que aparecem fazendo download em massa.

### YouTube: "Sign in to confirm you're not a bot"

YouTube tá detectando como bot. Cookies do Firefox de uma conta logada resolvem:

```ini
FIREFOX_PROFILE_PATH=/caminho/perfil/firefox
```

Confira que o perfil tem cookies recentes (você abriu o YouTube no Firefox recentemente).

### YouTube: vídeo de idade restrita

Cookies de conta logada e maior de idade **e** PO Token pro client `mweb` — ver [YouTube → Idade restrita](platforms/youtube.md#idade-restrita-po-token-bgutil).

### YouTube: vídeo privado / removido / geo-bloqueado

Desde v1.2.9 o bot detecta esses erros do yt-dlp e responde com mensagem clara (🔒/🗑️/🌍/etc.) em vez de cair pro scraper genérico (que costumava mandar o logo do YouTube/Google da página de erro). Lista completa em [YouTube → Detecção de erros não recuperáveis](platforms/youtube.md#deteccao-de-erros-nao-recuperaveis-v129).

Pra vídeo privado de verdade não tem como — só se sua conta no Firefox tiver acesso.

### YouTube: vídeo `.webm` chegou como documento sem player

Pré-v1.2.5 o bot mandava `webm`/`mkv`/`avi`/`flv` como vídeo, mas Telegram só renderiza player nativo pra MP4 H.264+AAC. A partir do v1.2.5, vídeo nesses formatos é convertido pra MP4 antes do envio (probe + remux/re-encode mínimo via ffmpeg). Configurável via `VIDEO_CONVERT_TIMEOUT` (default 900s).

### Reddit: 403 Forbidden

Desde 21/10/2026 a API JSON do Reddit dá 403 pra qualquer anônimo, e o bot lê a página do post no lugar (veja [Reddit](platforms/reddit.md#pagina-do-post-quando-a-api-json-da-403)). Se ainda assim falhar, o desafio JS da página pode ter mudado de formato — abra uma issue com o log `LOG_LEVEL=DEBUG`.

### Threads: "Post X não encontrado em scripts JSON do HTML"

Threads mudou o formato do SSR. Abrir issue no GitHub.

## Erros do scraper genérico

### "Nenhuma mídia encontrada na página"

Pode ser:

1. Página é SPA pesada (React/Angular/Vue) sem SSR — Playwright deveria pegar mas pode falhar
2. og:image / og:video / JSON-LD ausentes — site sem SEO básico
3. Conteúdo atrás de paywall hard (Substack, Patreon)
4. Conteúdo atrás de login

Tente o prompt de screenshot (default ativo).

### Imagens de UI sendo enviadas (avatar, logo)

`SCRAPE_MIN_IMAGE_SIZE` muito baixo. Aumente pra 100-200 (se 50 não tá filtrando).

### Demora muito

Cheque os tiers que tão rodando:

```bash
grep "🕸️\|⚡\|🧩\|🖼️" bot.log | tail -20
```

Se o Playwright tá tomando 30s+, ajuste `PW_GOTO_TIMEOUT_MS` pra menos. Se gallery-dl tá demorando, ajuste `SCRAPE_GALLERY_DL_TIMEOUT_S` pra menos ou desligue (`SCRAPE_GALLERY_DL_ENABLE=no`).

## Captions

### Caption não veio

Você tem 5 segundos pra clicar no prompt "📝 Descrição encontrada — incluir como legenda?". Se ignorar, o default é `no` (descarta).

Pra mudar default: `ASK_CAPTION_DEFAULT=yes` no `customization.json`.

### Caption do Twitter sem `@username`

URL é do tipo `/i/status/...` (anônima) e o JSON do tweet também não tem o screen_name. Bot tenta lookup mas pode não achar. Saída: usar a URL canônica `/<username>/status/<id>`.

## Performance

### Bot lento, RAM crescendo

O Playwright vaza memória ao longo do tempo. O bot recicla automaticamente quando RSS > `PW_REFRESH_RSS_MB_THRESHOLD` (default 1500MB). Se ainda assim tá ruim, baixe o threshold ou aumente `PW_REFRESH_CHECK_INTERVAL_MIN` (cheque mais frequente).

### CPU 100%

Possíveis causas:

- ffmpeg processando vídeo grande (espere terminar)
- yt-dlp num vídeo gigante
- Pool de Playwright cheio

Verifique via `LOG_LEVEL=DEBUG` o que tá rodando.

## Pra debug profundo

```ini
LOG_LEVEL=DEBUG
```

Aí todos os módulos (incluindo `httpx`, `urllib3`, `playwright`, etc.) voltam a logar. Volume sobe MUITO — desligue depois.

## Reportando bugs

Se encontrou um bug:

1. Reproduza com `LOG_LEVEL=DEBUG`
2. Anote a URL exata que falhou (ofusca infos sensíveis)
3. Cole o trecho relevante do `bot.log`
4. Mencione versão (`python -c "from version import __version__; print(__version__)"`)
5. Abra issue em [github.com/LordAztur/mediaraven/issues](https://github.com/LordAztur/mediaraven/issues)
