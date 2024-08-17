import logging
import os
import sys


class LoggerMixin:
    def __init__(self):
        loglevel = os.environ.get("LOGLEVEL", "INFO").upper()  # noqa: FKA100
        logging.basicConfig(
            format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            encoding="utf-8",
            level=loglevel,
            stream=sys.stdout,
        )
        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        self.log = logging.getLogger(self.__class__.__name__)
