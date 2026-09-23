"""Player handles: 3 to 8 characters, uppercase letters and digits only."""

import re

HANDLE_PATTERN = re.compile(r"^[A-Z0-9]{3,8}$")


class InvalidHandleError(ValueError):
    pass


def normalize_handle(raw: str) -> str:
    """Trim and uppercase the input, then validate it. Raises InvalidHandleError."""
    handle = raw.strip().upper()
    if not HANDLE_PATTERN.fullmatch(handle):
        raise InvalidHandleError("A handle has 3 to 8 characters: letters A-Z and digits 0-9.")
    return handle
