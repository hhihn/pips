import json
import logging
from pathlib import Path
from typing import Dict, Optional

from CodeNormalizer import normalize_code_for_lookup
from OMAConfig import OMAConfig


class CodeNameMapper:
    def __init__(self, config: OMAConfig):
        self.config = config
        self.code_names = self._load_code_names(config.code_name_mapping_path)

    def rename_state(self, state: str) -> str:
        if state == self.config.empty_state:
            return state

        return " | ".join(
            self._rename_code(code)
            for code in str(state).split("|")
        )

    def _rename_code(self, code: str) -> str:
        code = str(code).strip()
        lookup_code = normalize_code_for_lookup(code)
        return self.code_names.get(lookup_code, code)

    @staticmethod
    def _load_code_names(path: Optional[Path]) -> Dict[str, str]:
        if path is None:
            return {}

        mapping_path = Path(path)
        if not mapping_path.exists():
            fallback_path = Path(__file__).with_name(mapping_path.name)
            if fallback_path.exists():
                mapping_path = fallback_path
            else:
                logging.warning(
                    "Code name mapping file not found: %s. Codes will not be renamed.",
                    path,
                )
                return {}

        with mapping_path.open(encoding="utf-8") as f:
            raw_mapping = json.load(f)

        return {
            str(code).strip(): str(name).strip()
            for code, name in raw_mapping.items()
        }
