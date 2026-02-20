#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import gradio as gr

BASE_DIR = Path(__file__).resolve().parent
SUNBURST_DIR = BASE_DIR.parent
SRC_DIR = SUNBURST_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
DEFAULT_CSV = (SRC_DIR / "extracted_sequences.csv").resolve()
LOGO_PATH = BASE_DIR / "PIPS_Logo_mit_Untertitel.png"

CSS_PATH = BASE_DIR / "gradio_theme.css"
CODE_UTIL_CONFIG_PATH = SUNBURST_DIR / "code_util_config.json"
CODE_DESCRIPTIONS_PATH = BASE_DIR / "code_descriptions.json"
DATA_DRIVEN_COMBO_RULES_PATH = SUNBURST_DIR / "DATA_DRIVEN_COMBO_RULES.json"


def _load_theme_css() -> str:
    if CSS_PATH.exists():
        return CSS_PATH.read_text(encoding="utf-8")
    return ""


def _to_flag(cmd: list[str], flag: str, value, enabled: bool = True) -> None:
    if not enabled:
        return
    if isinstance(value, bool):
        if value:
            cmd.append(flag)
        return
    if value is None:
        return
    cmd.extend([flag, str(value)])


def _build_iframe_from_html_file(html_path: Path) -> str:
    content = html_path.read_text(encoding="utf-8")
    escaped = html.escape(content, quote=True)
    return (
        '<iframe style="width:100%;height:820px;border:1px solid #ddd;border-radius:8px;" '
        f'srcdoc="{escaped}"></iframe>'
    )


def refresh_sunburst_view(last_sunburst_path: str | None, existing_log: str) -> tuple[str, str | None, str]:
    if not last_sunburst_path:
        return "", None, (existing_log or "") + "\n\nKein Sunburst-Pfad vorhanden. Bitte zuerst einen Lauf starten."

    html_path = Path(last_sunburst_path)
    if not html_path.exists():
        return "", None, (existing_log or "") + f"\n\nSunburst-Datei nicht gefunden: {html_path}"

    iframe_html = _build_iframe_from_html_file(html_path)
    log_msg = (existing_log or "") + f"\n\nSunburst-Ansicht neu geladen aus: {html_path}"
    return iframe_html, str(html_path), log_msg


def lade_code_util_config() -> tuple[str, str]:
    if not CODE_UTIL_CONFIG_PATH.exists():
        return "", f"Fehler: Datei nicht gefunden: {CODE_UTIL_CONFIG_PATH}"
    try:
        data = json.loads(CODE_UTIL_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "", f"Fehler beim Lesen der JSON-Datei: {exc}"
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return pretty, f"Konfiguration geladen: {CODE_UTIL_CONFIG_PATH}"


def speichere_code_util_config(config_text: str) -> str:
    if not config_text or not config_text.strip():
        return "Fehler: Leerer Inhalt. Bitte gültiges JSON eingeben."
    try:
        parsed = json.loads(config_text)
    except json.JSONDecodeError as exc:
        return f"Fehler: Ungültiges JSON: {exc}"

    required_keys = {
        "placeholder_other",
        "prio_groups",
        "label_map",
        "predefined_combo_rules",
        "acting_codes",
    }
    missing = [k for k in required_keys if k not in parsed]
    if missing:
        return f"Fehler: Pflichtfelder fehlen: {', '.join(sorted(missing))}"

    try:
        if CODE_UTIL_CONFIG_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = CODE_UTIL_CONFIG_PATH.with_suffix(f".backup_{ts}.json")
            backup_path.write_text(CODE_UTIL_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        CODE_UTIL_CONFIG_PATH.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        return f"Fehler beim Speichern: {exc}"

    return f"Konfiguration gespeichert: {CODE_UTIL_CONFIG_PATH}"


def lade_code_descriptions() -> tuple[str, str]:
    if not CODE_DESCRIPTIONS_PATH.exists():
        return "", f"Fehler: Datei nicht gefunden: {CODE_DESCRIPTIONS_PATH}"
    try:
        data = json.loads(CODE_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "", f"Fehler beim Lesen der JSON-Datei: {exc}"
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return pretty, f"Beschreibungskonfiguration geladen: {CODE_DESCRIPTIONS_PATH}"


def speichere_code_descriptions(config_text: str) -> str:
    if not config_text or not config_text.strip():
        return "Fehler: Leerer Inhalt. Bitte gültiges JSON eingeben."
    try:
        parsed = json.loads(config_text)
    except json.JSONDecodeError as exc:
        return f"Fehler: Ungültiges JSON: {exc}"

    try:
        if CODE_DESCRIPTIONS_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = CODE_DESCRIPTIONS_PATH.with_suffix(f".backup_{ts}.json")
            backup_path.write_text(
                CODE_DESCRIPTIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
        CODE_DESCRIPTIONS_PATH.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        return f"Fehler beim Speichern: {exc}"

    return f"Beschreibungskonfiguration gespeichert: {CODE_DESCRIPTIONS_PATH}"


def lade_data_driven_combo_rules() -> tuple[str, str]:
    if not DATA_DRIVEN_COMBO_RULES_PATH.exists():
        return "", f"Fehler: Datei nicht gefunden: {DATA_DRIVEN_COMBO_RULES_PATH}"
    try:
        data = json.loads(DATA_DRIVEN_COMBO_RULES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "", f"Fehler beim Lesen der JSON-Datei: {exc}"
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return pretty, f"Regeldatei geladen: {DATA_DRIVEN_COMBO_RULES_PATH}"


def speichere_data_driven_combo_rules(config_text: str) -> str:
    if not config_text or not config_text.strip():
        return "Fehler: Leerer Inhalt. Bitte gültiges JSON eingeben."
    try:
        parsed = json.loads(config_text)
    except json.JSONDecodeError as exc:
        return f"Fehler: Ungültiges JSON: {exc}"

    try:
        if DATA_DRIVEN_COMBO_RULES_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = DATA_DRIVEN_COMBO_RULES_PATH.with_suffix(
                f".backup_{ts}.json"
            )
            backup_path.write_text(
                DATA_DRIVEN_COMBO_RULES_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        DATA_DRIVEN_COMBO_RULES_PATH.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        return f"Fehler beim Speichern: {exc}"

    return f"Regeldatei gespeichert: {DATA_DRIVEN_COMBO_RULES_PATH}"


def starte_sunburst(
    csv_upload,
    csv_pfad,
    out_prefix,
    max_depth,
    start_lookahead_n,
    min_support,
    rare_label,
    drop_rare_paths,
    cooccurrence_csv,
    min_window_count,
    refresh_data_driven_rules,
    no_sunburst,
    no_branching_analysis,
    branching_max_depth,
    min_branch_parent_count,
    min_branch_child_count,
    min_branch_children,
    all_codes_together,
    combo_time_match_mode,
    log_level,
):
    work_dir = SUNBURST_DIR

    if csv_upload is not None:
        csv_input = Path(csv_upload)
    else:
        csv_input = Path(csv_pfad).expanduser().resolve() if csv_pfad else DEFAULT_CSV

    if not csv_input.exists():
        return ("", None, f"Fehler: CSV-Datei nicht gefunden: {csv_input}", None)

    if out_prefix and out_prefix.strip():
        raw_out_prefix = Path(out_prefix.strip()).expanduser()
    else:
        raw_out_prefix = Path("out_paths")

    if raw_out_prefix.is_absolute():
        out_prefix_path = raw_out_prefix
    else:
        out_prefix_path = (SUNBURST_DIR / raw_out_prefix).resolve()

    out_prefix_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(SUNBURST_DIR / "sunburst_min_paths.py")]
    _to_flag(cmd, "--csv", str(csv_input))
    _to_flag(cmd, "--out_prefix", str(out_prefix_path))
    _to_flag(cmd, "--max_depth", max_depth)
    _to_flag(cmd, "--start_lookahead_n", start_lookahead_n)
    _to_flag(cmd, "--min_support", min_support)
    _to_flag(cmd, "--rare_label", rare_label)
    _to_flag(cmd, "--drop_rare_paths", drop_rare_paths)
    _to_flag(cmd, "--cooccurrence_csv", cooccurrence_csv)
    _to_flag(cmd, "--min_window_count", min_window_count)
    _to_flag(cmd, "--refresh_data_driven_rules", refresh_data_driven_rules)
    _to_flag(cmd, "--no_sunburst", no_sunburst)
    _to_flag(cmd, "--no_branching_analysis", no_branching_analysis)
    if branching_max_depth is not None:
        _to_flag(cmd, "--branching_max_depth", branching_max_depth)
    _to_flag(cmd, "--min_branch_parent_count", min_branch_parent_count)
    _to_flag(cmd, "--min_branch_child_count", min_branch_child_count)
    _to_flag(cmd, "--min_branch_children", min_branch_children)
    _to_flag(cmd, "--all_codes_together", all_codes_together)
    _to_flag(cmd, "--combo_time_match_mode", combo_time_match_mode)
    _to_flag(cmd, "--log_level", log_level)

    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )

    log_text = (
        f"Befehl:\n{' '.join(cmd)}\n\n"
        f"Rückgabecode: {proc.returncode}\n\n"
        f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}"
    )

    if proc.returncode != 0:
        return (
            "",
            None,
            f"Fehler beim Lauf. Details siehe Protokoll.\n\n{log_text}",
            None,
        )

    sunburst_html_path = Path(f"{out_prefix_path}_sunburst.html")

    if no_sunburst:
        info = (
            "Lauf erfolgreich, aber Sunburst wurde deaktiviert (--no_sunburst).\n"
            f"Ausgabepräfix: {out_prefix_path}\n\n{log_text}"
        )
        return "", None, info, None

    if not sunburst_html_path.exists():
        info = (
            "Lauf erfolgreich, aber Sunburst-HTML wurde nicht gefunden.\n"
            f"Erwarteter Pfad: {sunburst_html_path}\n\n{log_text}"
        )
        return "", None, info, None

    iframe_html = _build_iframe_from_html_file(sunburst_html_path)
    info = (
        f"Lauf erfolgreich.\nSunburst-Datei: {sunburst_html_path}\n"
        f"Ausgabepräfix: {out_prefix_path}\n"
        f"CSV-Ausgaben unter: {out_prefix_path.parent / 'csv_analysen'}\n\n{log_text}"
    )
    return iframe_html, str(sunburst_html_path), info, str(sunburst_html_path)


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Datengetriebene Sequenzanalyse") as demo:
        with gr.Row(elem_classes=["pips-header"]):
            with gr.Column(scale=1, min_width=220):
                if LOGO_PATH.exists():
                    gr.Image(
                        value=str(LOGO_PATH),
                        show_label=False,
                        container=False,
                        interactive=False,
                        elem_classes=["pips-logo"],
                    )
                else:
                    gr.Markdown("**PIPS**")
            with gr.Column(scale=3, elem_classes=["pips-title"]):
                gr.Markdown(
                    "## Sunburst-Generierung\n"
                    "Starte die Analyse und visualisiere den erzeugten Sunburst direkt hier."
                )

        with gr.Row():
            with gr.Column(scale=1, elem_classes=["pips-panel"]):
                gr.Markdown("### Eingabe")
                csv_upload = gr.File(
                    label="CSV-Datei hochladen (optional)",
                    file_types=[".csv"],
                    type="filepath",
                )
                csv_pfad = gr.Textbox(
                    label="CSV-Pfad (wenn kein Upload)",
                    value=str(DEFAULT_CSV),
                )
                out_prefix = gr.Textbox(
                    label="Ausgabepräfix",
                    value="out_paths",
                )

                with gr.Tabs():
                    with gr.Tab("Kern-Einstellungen"):
                        max_depth = gr.Number(
                            label="Maximale Sunburst-Tiefe", value=4, precision=0
                        )
                        start_lookahead_n = gr.Number(
                            label="Lookahead N", value=5, precision=0
                        )
                        min_support = gr.Number(
                            label="Mindest-Support", value=1, precision=0
                        )
                        rare_label = gr.Textbox(
                            label="Label für seltene Pfade", value="Andere (selten)"
                        )
                        drop_rare_paths = gr.Checkbox(
                            label="Seltene Pfade verwerfen", value=False
                        )

                    with gr.Tab("Erweiterte Einstellungen"):
                        cooccurrence_csv = gr.Textbox(
                            label="Co-Occurrence CSV",
                            value="csv_analysen/cooccurrence/out_paths_cooccurrence_same_window.csv",
                        )
                        min_window_count = gr.Number(
                            label="Minimale Fensteranzahl", value=5, precision=0
                        )
                        refresh_data_driven_rules = gr.Checkbox(
                            label="Data-driven Regeln neu berechnen",
                            value=False,
                        )
                        no_sunburst = gr.Checkbox(
                            label="Sunburst nicht erzeugen (--no_sunburst)", value=False
                        )
                        no_branching_analysis = gr.Checkbox(
                            label="Branching-Analyse deaktivieren",
                            value=False,
                        )
                        branching_max_depth = gr.Number(
                            label="Branching max depth (leer = max_depth)",
                            value=None,
                            precision=0,
                        )
                        min_branch_parent_count = gr.Number(
                            label="Min Branch Parent Count", value=3, precision=0
                        )
                        min_branch_child_count = gr.Number(
                            label="Min Branch Child Count", value=1, precision=0
                        )
                        min_branch_children = gr.Number(
                            label="Min Distinct Branch Children", value=2, precision=0
                        )
                        all_codes_together = gr.Checkbox(
                            label="Alle Codes zusammen", value=False
                        )
                        combo_time_match_mode = gr.Radio(
                            label="Combo-Zeitmodus",
                            choices=["keine", "exact", "overlap"],
                            value="exact",
                        )
                        log_level = gr.Radio(
                            label="Log-Level",
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            value="INFO",
                        )

                run_btn = gr.Button(
                    "Sunburst starten", variant="primary", elem_classes=["pips-primary"]
                )

            with gr.Column(scale=2, elem_classes=["pips-panel"]):
                with gr.Tabs():
                    with gr.Tab("Ergebnis"):
                        gr.Markdown("### Ergebnis")
                        last_sunburst_path = gr.State(value=None)
                        sunburst_view = gr.HTML(label="Sunburst")
                        sunburst_file = gr.File(label="Sunburst HTML herunterladen")
                        refresh_sunburst_btn = gr.Button(
                            "Sunburst neu laden",
                            elem_classes=["pips-primary"],
                        )
                        protokoll = gr.Textbox(
                            label="Protokoll",
                            lines=20,
                            max_lines=40,
                        )
                    with gr.Tab("Code-Config Editor"):
                        gr.Markdown(
                            "### `code_util_config.json` bearbeiten\n"
                            "Änderungen werden direkt in die Konfigurationsdatei geschrieben."
                        )
                        config_editor = gr.Code(
                            label="JSON-Konfiguration",
                            language="json",
                            lines=28,
                            value=lade_code_util_config()[0],
                        )
                        with gr.Row():
                            laden_btn = gr.Button("Konfiguration laden")
                            speichern_btn = gr.Button(
                                "Konfiguration speichern",
                                variant="primary",
                                elem_classes=["pips-primary"],
                            )
                        config_status = gr.Textbox(
                            label="Status",
                            lines=3,
                            max_lines=6,
                            value=lade_code_util_config()[1],
                        )
                    with gr.Tab("Code-Descriptions Editor"):
                        gr.Markdown(
                            "### `app/code_descriptions.json` bearbeiten\n"
                            "Änderungen werden direkt in die Konfigurationsdatei geschrieben."
                        )
                        code_desc_editor = gr.Code(
                            label="JSON-Beschreibungen",
                            language="json",
                            lines=28,
                            value=lade_code_descriptions()[0],
                        )
                        with gr.Row():
                            laden_desc_btn = gr.Button("Beschreibungen laden")
                            speichern_desc_btn = gr.Button(
                                "Beschreibungen speichern",
                                variant="primary",
                                elem_classes=["pips-primary"],
                            )
                        code_desc_status = gr.Textbox(
                            label="Status",
                            lines=3,
                            max_lines=6,
                            value=lade_code_descriptions()[1],
                        )
                    with gr.Tab("Data-Driven Combo Rules"):
                        gr.Markdown(
                            "### `DATA_DRIVEN_COMBO_RULES.json` bearbeiten\n"
                            "Änderungen werden direkt in die Regeldatei geschrieben.",
                            elem_classes=["pips-info"],
                        )
                        combo_rules_editor = gr.Code(
                            label="JSON-Regeln",
                            language="json",
                            lines=28,
                            value=lade_data_driven_combo_rules()[0],
                        )
                        with gr.Row():
                            laden_rules_btn = gr.Button("Regeln laden")
                            speichern_rules_btn = gr.Button(
                                "Regeln speichern",
                                variant="primary",
                                elem_classes=["pips-primary"],
                            )
                        combo_rules_status = gr.Textbox(
                            label="Status",
                            lines=3,
                            max_lines=6,
                            value=lade_data_driven_combo_rules()[1],
                        )

        run_btn.click(
            fn=starte_sunburst,
            inputs=[
                csv_upload,
                csv_pfad,
                out_prefix,
                max_depth,
                start_lookahead_n,
                min_support,
                rare_label,
                drop_rare_paths,
                cooccurrence_csv,
                min_window_count,
                refresh_data_driven_rules,
                no_sunburst,
                no_branching_analysis,
                branching_max_depth,
                min_branch_parent_count,
                min_branch_child_count,
                min_branch_children,
                all_codes_together,
                combo_time_match_mode,
                log_level,
            ],
            outputs=[sunburst_view, sunburst_file, protokoll, last_sunburst_path],
        )
        refresh_sunburst_btn.click(
            fn=refresh_sunburst_view,
            inputs=[last_sunburst_path, protokoll],
            outputs=[sunburst_view, sunburst_file, protokoll],
        )

        laden_btn.click(
            fn=lade_code_util_config,
            inputs=[],
            outputs=[config_editor, config_status],
        )
        speichern_btn.click(
            fn=speichere_code_util_config,
            inputs=[config_editor],
            outputs=[config_status],
        )
        laden_desc_btn.click(
            fn=lade_code_descriptions,
            inputs=[],
            outputs=[code_desc_editor, code_desc_status],
        )
        speichern_desc_btn.click(
            fn=speichere_code_descriptions,
            inputs=[code_desc_editor],
            outputs=[code_desc_status],
        )
        laden_rules_btn.click(
            fn=lade_data_driven_combo_rules,
            inputs=[],
            outputs=[combo_rules_editor, combo_rules_status],
        )
        speichern_rules_btn.click(
            fn=speichere_data_driven_combo_rules,
            inputs=[combo_rules_editor],
            outputs=[combo_rules_status],
        )

    return demo


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(
        theme=gr.themes.Soft(),
        css=_load_theme_css(),
        allowed_paths=[str(SUNBURST_DIR), str(BASE_DIR)],
    )
