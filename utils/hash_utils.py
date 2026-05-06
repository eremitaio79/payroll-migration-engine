from __future__ import annotations

import hashlib
from typing import Any


def stable_hash(*parts: Any) -> str:
    normalized = "||".join("" if part is None else str(part).strip() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
