"""
Configuracao centralizada de logging.

- bot.log          -> INFO+  (historico completo, rotacao diaria)
- bot.error.log    -> WARNING+ (erros rapidos de diagnostico)
- console          -> INFO+ com UTF-8
"""

import sys
import logging
import logging.handlers


def setup_logging() -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    if hasattr(console.stream, "reconfigure"):
        console.stream.reconfigure(encoding="utf-8", errors="replace")

    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)
    logger.addHandler(console)

    # Handlers de arquivo: opcionais -- ignorados no Fargate (sem volume)
    try:
        file_main = logging.handlers.TimedRotatingFileHandler(
            "/app/logs/bot.log", when="midnight", interval=1, backupCount=0, encoding="utf-8"
        )
        file_main.setFormatter(fmt)
        file_main.setLevel(logging.INFO)
        logger.addHandler(file_main)

        file_err = logging.handlers.TimedRotatingFileHandler(
            "/app/logs/bot.error.log", when="midnight", interval=1, backupCount=0, encoding="utf-8"
        )
        file_err.setFormatter(fmt)
        file_err.setLevel(logging.WARNING)
        logger.addHandler(file_err)

    except OSError:
        logger.warning("Diretorio de logs indisponivel -- usando apenas console (modo Fargate)")

    return logger
