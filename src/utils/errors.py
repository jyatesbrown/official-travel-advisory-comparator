from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    DESTINATION_NOT_FOUND = "DESTINATION_NOT_FOUND"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    PARSER_FAILED = "PARSER_FAILED"
    UNEXPECTED_SOURCE_FORMAT = "UNEXPECTED_SOURCE_FORMAT"
    INVALID_DESTINATION = "INVALID_DESTINATION"


RETRYABLE_CODES = frozenset({ErrorCode.UPSTREAM_UNAVAILABLE, ErrorCode.UPSTREAM_TIMEOUT})
FORMAT_DRIFT_CODES = frozenset({ErrorCode.PARSER_FAILED, ErrorCode.UNEXPECTED_SOURCE_FORMAT})

_PUBLIC_MESSAGES = {
    ErrorCode.DESTINATION_NOT_FOUND: "{source} does not publish an advisory for this destination.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "{source} source could not be retrieved.",
    ErrorCode.UPSTREAM_TIMEOUT: "{source} source did not respond in time.",
    ErrorCode.PARSER_FAILED: "{source} content was retrieved but could not be parsed.",
    ErrorCode.UNEXPECTED_SOURCE_FORMAT: "{source} content was retrieved but its structure was not recognised.",
    ErrorCode.INVALID_DESTINATION: "Destination could not be resolved to a single country or territory.",
}


def public_message(code: ErrorCode, source_label: str = "") -> str:
    return _PUBLIC_MESSAGES[code].format(source=source_label)


class SourceError(Exception):
    """Controlled, serialisable failure of one government source.

    `detail` is developer-facing and is logged, never written to the public dataset.
    """

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES
