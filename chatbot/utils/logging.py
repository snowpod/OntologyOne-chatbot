# utils/logging.py

import logging
import os
import sys

from logging.handlers import RotatingFileHandler
from pathlib import Path

def get_stdout_logger(name="stdout", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

def get_logger(log_name: str, level=logging.INFO,
               log_dir="log", max_bytes=5 * 1024 * 1024, backup_count=5) -> logging.Logger:
    """
    Create a logger that writes to `log/{log_name}.log`, with file rotation.

    :param log_name: Logical name of the logger (also used for file name).
    :param level: Logging level.
    :param log_dir: Directory to store logs.
    :param max_bytes: Maximum size before rotating.
    :param backup_count: Number of backup files to keep.
    """
    logger = logging.getLogger(log_name)
    logger.setLevel(level)

    if not logger.handlers:
        env = os.environ.get("APP_ENV", "dev")
        use_file = env == "dev"

        if use_file:
            log_path = Path(log_dir) / f"{log_name}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            handler = RotatingFileHandler(
                log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
        else:
            handler = logging.StreamHandler(sys.stdout)

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger