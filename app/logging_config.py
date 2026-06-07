import logging
from app.config import LOG_LEVEL


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    for noisy in ("aiohttp.access", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
