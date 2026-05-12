import re


def normalize_code_for_lookup(code: str) -> str:
    return re.sub(r"\s+(PK|AK)$", "", str(code).strip())
