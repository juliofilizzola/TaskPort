"""Logs estruturados em JSON com remoção de credenciais."""

import json
import logging
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime

_RESERVED_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}

# Padrões genéricos de credenciais, aplicados mesmo que o valor exato não seja conhecido.
_SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(oauth_consumer_key|oauth_token)=\\?"[^"\\]*\\?"'),
    re.compile(r"(?i)\b(key|token|api_key|apikey)=([^&\s\"']+)"),
]
REDACTED = "***"


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    for pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    return text


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str, ensure_ascii=False), self._secrets)


def configure_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(secrets))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # O httpx registra URLs completas em INFO; mantemos apenas avisos.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
