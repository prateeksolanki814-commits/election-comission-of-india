"""
Structured logging configuration. Rule: this is the ONLY place log
processors are configured, and it always includes a redaction processor so
that even if a developer accidentally passes a sensitive field (otp,
password, token, candidate_id, voter_code) into a log call, it gets
scrubbed before it hits stdout/log storage.
"""
import logging

import structlog

from app.core.config import get_settings

_REDACT_KEYS = {
    "otp",
    "password",
    "password_hash",
    "token",
    "voting_token",
    "raw_token",
    "candidate_id",
    "candidate_choice",
    "voter_code",
    "synthetic_voter_code",
}


def _redact_processor(logger, method_name, event_dict):
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
