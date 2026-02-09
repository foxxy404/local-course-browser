from __future__ import annotations

import re


def natural_key(s: str):
    """Sort key that treats digit runs as integers ("2" < "10")."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
