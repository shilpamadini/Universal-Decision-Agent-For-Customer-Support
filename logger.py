import logging
import json
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


LOG_DIR = "logs"
LOG_FILE = "logs/uda_hub.jsonl"

os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Formats logs as JSON lines."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if hasattr(record, "ticket_id"):
            log_entry["ticket_id"] = record.ticket_id

        if hasattr(record, "thread_id"):
            log_entry["thread_id"] = record.thread_id

        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data

        return json.dumps(log_entry)


def get_logger(name="uda_hub"):
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger   

    logger.setLevel(logging.INFO)

    # Stream → console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())

    # File handler → rotating JSONL file
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5
    )
    file_handler.setFormatter(JsonFormatter())

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger
