#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import html
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import gradio as gr

BASE_DIR = Path(__file__).resolve().parent
SUNBURST_DIR = BASE_DIR.parent
SRC_DIR = SUNBURST_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
DEFAULT_CSV = (SRC_DIR / "extracted_sequences.csv").resolve()
LOGO_PATH = BASE_DIR / "PIPS_Logo_mit_Untertitel.png"

CSS_PATH = BASE_DIR / "gradio_theme.css"


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
        return (
            "",
            None,
            f"Fehler: CSV-Datei nicht gefunden: {csv_input}",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="sunburst_gradio_"))
    if out_prefix and out_prefix.strip():
        out_prefix_path = tmp_dir / out_prefix.strip()
    else:
        out_prefix_path = tmp_dir / "out_paths"

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
        )

    sunburst_html_path = Path(f"{out_prefix_path}_sunburst.html")

    if no_sunburst:
        info = (
            "Lauf erfolgreich, aber Sunburst wurde deaktiviert (--no_sunburst).\n"
            f"Ausgabepräfix: {out_prefix_path}\n\n{log_text}"
        )
        return "", None, info

    if not sunburst_html_path.exists():
        info = (
            "Lauf erfolgreich, aber Sunburst-HTML wurde nicht gefunden.\n"
            f"Erwarteter Pfad: {sunburst_html_path}\n\n{log_text}"
        )
        return "", None, info

    iframe_html = _build_iframe_from_html_file(sunburst_html_path)
    info = (
        f"Lauf erfolgreich.\nSunburst-Datei: {sunburst_html_path}\n"
        f"Ausgabepräfix: {out_prefix_path}\n\n{log_text}"
    )
    return iframe_html, str(sunburst_html_path), info


def build_demo() -> gr.Blocks:
    with gr.Blocks(
        title="Datengetriebene Sequenzanalyse", theme=gr.themes.Soft(), css=_load_theme_css()
    ) as demo:
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

                gr.Markdown("### Kern-Einstellungen")
                max_depth = gr.Number(label="Maximale Sunburst-Tiefe", value=4, precision=0)
                start_lookahead_n = gr.Number(label="Lookahead N", value=5, precision=0)
                min_support = gr.Number(label="Mindest-Support", value=1, precision=0)
                rare_label = gr.Textbox(label="Label für seltene Pfade", value="Andere (selten)")
                drop_rare_paths = gr.Checkbox(label="Seltene Pfade verwerfen", value=False)

                gr.Markdown("### Co-Occurrence / Regeln")
                cooccurrence_csv = gr.Textbox(
                    label="Co-Occurrence CSV",
                    value="out_paths_cooccurrence_same_window.csv",
                )
                min_window_count = gr.Number(label="Minimale Fensteranzahl", value=5, precision=0)
                refresh_data_driven_rules = gr.Checkbox(
                    label="Data-driven Regeln neu berechnen",
                    value=False,
                )

                gr.Markdown("### Analyse-Schalter")
                no_sunburst = gr.Checkbox(label="Sunburst nicht erzeugen (--no_sunburst)", value=False)
                no_branching_analysis = gr.Checkbox(
                    label="Branching-Analyse deaktivieren",
                    value=False,
                )
                branching_max_depth = gr.Number(
                    label="Branching max depth (leer = max_depth)",
                    value=None,
                    precision=0,
                )
                min_branch_parent_count = gr.Number(label="Min Branch Parent Count", value=3, precision=0)
                min_branch_child_count = gr.Number(label="Min Branch Child Count", value=1, precision=0)
                min_branch_children = gr.Number(label="Min Distinct Branch Children", value=2, precision=0)
                all_codes_together = gr.Checkbox(label="Alle Codes zusammen", value=False)
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
                gr.Markdown("### Ergebnis")
                sunburst_view = gr.HTML(label="Sunburst")
                sunburst_file = gr.File(label="Sunburst HTML herunterladen")
                protokoll = gr.Textbox(
                    label="Protokoll",
                    lines=20,
                    max_lines=40,
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
            outputs=[sunburst_view, sunburst_file, protokoll],
        )

    return demo


if __name__ == "__main__":
    demo = build_demo()
    demo.launch()
