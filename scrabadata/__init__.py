"""Init module of scrabadata project
"""

from pathlib import Path
import logging
import configparser

import daiquiri
import daiquiri.formatter


_HERE = Path().absolute()
_CONFIG_FILE = _HERE / "scrabadata" / "config.ini"

FORMAT = (
    "%(asctime)s :: %(color)s%(levelname)s :: %(name)s :: %(funcName)s :"
    "%(message)s%(color_stop)s"
    )
daiquiri.setup(level=logging.INFO, outputs=(
    daiquiri.output.Stream(formatter=daiquiri.formatter.ColorFormatter(
        fmt=FORMAT)),
    ))
logger = daiquiri.getLogger("root")

if not _CONFIG_FILE.is_file():
    logger.error("Configuration file '%s' not found", _CONFIG_FILE)
    config = None
else:
    config = configparser.ConfigParser(allow_no_value=True)
    with open(_CONFIG_FILE) as fobj:
        config.read_file(fobj)
