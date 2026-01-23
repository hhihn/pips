import re


def extract_code_prefix(code: str, level: int | None = None) -> str:
    if not isinstance(code, str):
        return "OTHER"
    parts = re.findall(r"\d+", code)
    if not parts:
        return "OTHER"
    if level is None or level >= len(parts):
        return ".".join(parts)
    return ".".join(parts[:level])


print(extract_code_prefix("2.1.1.14 asdfasdf"))
