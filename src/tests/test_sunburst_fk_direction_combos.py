import pandas as pd

from src.sunburst.bundling import ExactBundleStrategy
from src.sunburst.context import AnalysisContext
from src.sunburst.helper import apply_bundle_combos, label_for_token
from src.sunburst.sequence_builders import PartsSequenceBuilder


def _context() -> AnalysisContext:
    prio_groups = [
        ("innen", ["2.1.2.3", "6.5.1", "2.2.3.14"]),
        ("mitte", ["6.4.2", "6.5.4", "2.2.3.14"]),
        ("aussen", ["2.1.3.1", "6.5.3", "6.4.3", "6.4.4", "6.4.5"]),
        ("aussenring", ["2.1.3.5", "2.2.3.14", "2.2.3.4", "6.5.4"]),
    ]
    code_to_prio = {
        code: (group_idx, code_idx)
        for group_idx, (_name, codes) in enumerate(prio_groups)
        for code_idx, code in enumerate(codes)
    }
    label_map = {
        "2.1.2.3": "FK benennt Ziel",
        "2.1.3.1": "FK führt Hdlg. aus",
        "6.4.3": "FK von vorn",
        "6.4.4": "FK von der Seite",
        "6.4.5": "FK von hinten",
        "2.2.3.14": "KK Objektbezug",
        "2.2.3.4": "KK Halten",
        "2.1.3.1 & 6.4.4": "FK führt Hdlg. aus + FK von der Seite",
        "2.1.3.1 & 6.4.4 & 2.2.3.14 & 2.2.3.4": (
            "FK führt Hdlg. aus + FK von der Seite + KK Objektbezug + KK Halten"
        ),
    }
    predefined_combo_rules = [
        (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
        (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
        (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
        (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
        (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
        (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
    ]
    data_driven_combo_rules = [
        (
            ("2.1.3.1", "6.4.4", "2.2.3.14", "2.2.3.4"),
            "FK führt Hdlg. aus + FK von der Seite + KK Objektbezug + KK Halten",
            10,
        )
    ]
    combo_rules = predefined_combo_rules + [
        (codes, label) for codes, label, _count in data_driven_combo_rules
    ]
    return AnalysisContext(
        placeholder_other="Andere",
        prio_groups=prio_groups,
        code_to_prio=code_to_prio,
        group_name_to_codes={name: set(codes) for name, codes in prio_groups},
        label_map=label_map,
        predefined_combo_rules=predefined_combo_rules,
        data_driven_combo_rules=data_driven_combo_rules,
        combo_rules=combo_rules,
        allowed_codes=set(code_to_prio),
        acting_codes={"2.1.3.1", "2.1.3.1 & 6.4.4"},
    )


def test_apply_bundle_combos_prefers_long_fk_direction_combo():
    context = _context()

    tokens = apply_bundle_combos(
        ["2.1.3.1", "6.4.4", "2.2.3.14", "2.2.3.4"],
        context=context,
    )

    assert tokens == ["2.1.3.1 & 6.4.4 & 2.2.3.14 & 2.2.3.4"]
    assert "FK von der Seite" in label_for_token(tokens[0], context=context)


def test_parts_builder_keeps_fk_direction_in_aussen_token():
    context = _context()
    df = pd.DataFrame(
        [
            {
                "Filename": "case.xlsx",
                "id": "0",
                "Sequence_Code": "2.1.2.3 PK",
                "Sequence_Start": "0:00:01,0",
                "Sequence_End": "0:00:02,0",
            },
            {
                "Filename": "case.xlsx",
                "id": "0",
                "Sequence_Code": "2.1.3.1 PK",
                "Sequence_Start": "0:00:03,0",
                "Sequence_End": "0:00:05,0",
            },
            {
                "Filename": "case.xlsx",
                "id": "0",
                "Sequence_Code": "6.4.4 PK",
                "Sequence_Start": "0:00:03,0",
                "Sequence_End": "0:00:05,0",
            },
        ]
    )

    _seqs, per_path = PartsSequenceBuilder(
        context=context,
        bundle_strategy=ExactBundleStrategy(),
    ).build(df, start_lookahead_n=5)

    assert per_path.loc[0, "aussen_token"] == "['2.1.3.1 & 6.4.4']"
    assert "6.4.4" in per_path.loc[0, "sequence_tokens"]
    assert "FK von der Seite" in per_path.loc[0, "sequence_labels"]
