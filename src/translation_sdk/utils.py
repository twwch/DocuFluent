import sys
from loguru import logger

def setup_logging(level="INFO"):
    logger.remove()
    logger.add(sys.stderr, level=level)
