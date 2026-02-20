from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Set, Tuple

from src.sunburst.code_util import CodeUtil


@dataclass(frozen=True)
class AnalysisContext:
    placeholder_other: str
    prio_groups: List[Tuple[str, List[str]]]
    code_to_prio: Dict[str, Tuple[int, int]]
    group_name_to_codes: Dict[str, Set[str]]
    label_map: Dict[str, str]
    predefined_combo_rules: List[Tuple[Tuple[str, ...], str]]
    data_driven_combo_rules: List[Tuple[Tuple[str, ...], str, int]]
    combo_rules: List[Tuple[Tuple[str, ...], str]]
    allowed_codes: Set[str]
    acting_codes: Set[str]

    @classmethod
    def from_code_util(cls, code_util: CodeUtil) -> "AnalysisContext":
        return cls(
            placeholder_other=str(code_util.PLACEHOLDER_OTHER),
            prio_groups=[(name, list(codes)) for name, codes in code_util.PRIO_GROUPS],
            code_to_prio={k: tuple(v) for k, v in code_util.CODE_TO_PRIO.items()},
            group_name_to_codes={
                name: set(codes) for name, codes in code_util.GROUP_NAME_TO_CODES.items()
            },
            label_map=dict(code_util.LABEL_MAP),
            predefined_combo_rules=[
                (tuple(codes), label) for codes, label in code_util.PREDEFINED_COMBO_RULES
            ],
            data_driven_combo_rules=[
                (tuple(codes), label, int(count))
                for codes, label, count in code_util.DATA_DRIVEN_COMBO_RULES
            ],
            combo_rules=[(tuple(codes), label) for codes, label in code_util.COMBO_RULES],
            allowed_codes=set(code_util.ALLOWED_CODES),
            acting_codes=set(code_util.ACTING_CODES),
        )


@lru_cache(maxsize=1)
def get_default_context() -> AnalysisContext:
    return AnalysisContext.from_code_util(CodeUtil())
