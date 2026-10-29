import sys

from telegram.ext import AIORateLimiter, ApplicationBuilder, CallbackQueryHandler, Defaults, MessageHandler, filters

from config import (
    LOCAL_API_URL,
    LOCAL_FILE_URL,
    TOKEN,
    setup_logging,
    validate_runtime_config,
)
from handlers import error_handler, future_callback, handle_message, retry_callback
from lifecycle import init_deno, init_ffmpeg, init_globals, stop_globals
from messages import msg
from version import __version__


if __name__ == '__main__':
    setup_logging()

    if not TOKEN:
        print(msg("startup.token_missing"))
        sys.exit(1)

    config_errors = validate_runtime_config()
    if config_errors:
        for err in config_errors:
            print(f"❌ Config inválida: {err}")
        sys.exit(1)

    init_deno()
    init_ffmpeg()

    print(msg("startup.connecting", api_url=LOCAL_API_URL, version=__version__))

    builder = ApplicationBuilder().token(TOKEN)
    builder.base_url(LOCAL_API_URL)
    builder.base_file_url(LOCAL_FILE_URL)
    builder.local_mode(True)
    builder.rate_limiter(AIORateLimiter(max_retries=3))
    # Se a mensagem com o link for apagada durante o download, envia sem o
    # reply em vez de perder a mídia ("Message to be replied not found").
    builder.defaults(Defaults(allow_sending_without_reply=True))
    builder.post_init(init_globals)
    builder.post_shutdown(stop_globals)
    application = builder.concurrent_updates(True).build()
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern=r"^retry_"))
    application.add_handler(CallbackQueryHandler(future_callback, pattern=r"^(dl|lang|cap|scrn)\|"))
    application.add_error_handler(error_handler)

    print(msg("startup.ready"))
    application.run_polling()
