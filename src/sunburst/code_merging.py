import json
from typing import Dict, List, Tuple

from src.sunburst.code_util import CodeUtil


def _load_rules_from_json(path: str) -> List[Tuple[str, List[str]]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out: List[Tuple[str, List[str]]] = []
    if isinstance(data, dict):
        for meta_code, codes in data.items():
            if not isinstance(codes, list):
                raise ValueError(
                    f"Invalid merge JSON at '{path}': value for '{meta_code}' must be a list."
                )
            out.append(
                (str(meta_code), [str(c).strip() for c in codes if str(c).strip()])
            )
        return out

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(
                    f"Invalid merge JSON at '{path}': list entries must be objects."
                )
            meta_code = (
                item.get("meta_code") or item.get("target") or item.get("merged_code")
            )
            codes = item.get("codes") or item.get("source_codes") or item.get("members")
            if not meta_code or not isinstance(codes, list):
                raise ValueError(
                    f"Invalid merge JSON at '{path}': each rule needs meta_code/target and codes/source_codes list."
                )
            out.append(
                (str(meta_code), [str(c).strip() for c in codes if str(c).strip()])
            )
        return out

    raise ValueError(
        f"Invalid merge JSON at '{path}': expected object or list of objects."
    )


def _parse_inline_rule(rule: str) -> Tuple[str, List[str]]:
    if "=" not in rule:
        raise ValueError(
            f"Invalid --merge_rule '{rule}'. Expected format META=code1,code2,..."
        )
    meta_code, raw_codes = rule.split("=", 1)
    meta_code = meta_code.strip()
    codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
    if not meta_code or not codes:
        raise ValueError(
            f"Invalid --merge_rule '{rule}'. Expected format META=code1,code2,..."
        )
    return meta_code, codes


def build_merge_map(
    merge_rules: List[str] | None = None,
    merge_rules_json: str | None = None,
) -> Dict[str, str]:
    """
    Build source->meta mapping from inline rules and optional JSON file.
    """
    parsed_rules: List[Tuple[str, List[str]]] = []

    if merge_rules_json:
        parsed_rules.extend(_load_rules_from_json(merge_rules_json))

    for rule in merge_rules or []:
        parsed_rules.append(_parse_inline_rule(rule))

    merge_map: Dict[str, str] = {}
    for meta_code, sources in parsed_rules:
        for src in sources:
            if src == meta_code:
                continue
            prev = merge_map.get(src)
            if prev and prev != meta_code:
                raise ValueError(
                    f"Code '{src}' is mapped to both '{prev}' and '{meta_code}'."
                )
            merge_map[src] = meta_code
    return merge_map


def register_meta_codes_in_code_util(
    code_util: CodeUtil,
    merge_map: Dict[str, str],
) -> None:
    """
    Register meta-codes in label/priority/group structures for downstream logic.
    """
    if not merge_map:
        return

    by_meta: Dict[str, List[str]] = {}
    for src, meta in merge_map.items():
        by_meta.setdefault(meta, []).append(src)

    for meta, sources in by_meta.items():
        # Ensure label exists.
        if meta not in code_util.LABEL_MAP:
            code_util.LABEL_MAP[meta] = meta

        # Priority: inherit best (lowest) available source priority.
        prios = [
            code_util.CODE_TO_PRIO.get(s)
            for s in sources
            if s in code_util.CODE_TO_PRIO
        ]
        if prios:
            code_util.CODE_TO_PRIO[meta] = min(prios)
        else:
            code_util.CODE_TO_PRIO.setdefault(meta, (999, 999))

        # Add to groups where any source is present.
        for group_name, group_codes in code_util.GROUP_NAME_TO_CODES.items():
            if any(src in group_codes for src in sources):
                group_codes.add(meta)

        code_util.ALLOWED_CODES.add(meta)


def summarize_merge_map(merge_map: Dict[str, str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for src, meta in sorted(merge_map.items(), key=lambda x: (x[1], x[0])):
        rows.append({"source_code": src, "meta_code": meta})
    return rows
