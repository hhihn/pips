#!/usr/bin/env python3
"""Run the full analysis pipeline described in readme.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"


def run_step(name: str, cmd: list[str], cwd: Path) -> None:
    print(f"\n[{name}]", flush=True)
    print(f"Running: {' '.join(cmd)} (cwd={cwd})", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def can_import_pandas(python_executable: str) -> bool:
    result = subprocess.run(
        [python_executable, "-c", "import pandas"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def resolve_python_executable() -> str:
    if can_import_pandas(sys.executable):
        return sys.executable

    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists() and can_import_pandas(str(venv_python)):
        return str(venv_python)

    return sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run transform, detection, ordering, count analysis, and row view."
    )
    parser.add_argument(
        "--skip-count-analysis",
        action="store_true",
        help="Skip src/count_analysis.py (interactive plotting step).",
    )
    args = parser.parse_args()

    python = resolve_python_executable()
    print(f"Using Python interpreter: {python}", flush=True)

    try:
        run_step(
            "1/5 Transform data",
            [python, "transform_data.py"],
            cwd=REPO_ROOT,
        )
        run_step(
            "2/5 Detect codes within",
            [python, "detect_codes_within.py"],
            cwd=SRC_DIR,
        )
        run_step(
            "3/5 Analyse order",
            [python, "analyse_order.py"],
            cwd=SRC_DIR,
        )
        if not args.skip_count_analysis:
            run_step(
                "4/5 Count analysis",
                [python, "count_analysis.py"],
                cwd=SRC_DIR,
            )
        else:
            print("\n[4/5 Count analysis]", flush=True)
            print("Skipped (--skip-count-analysis).", flush=True)
        run_step(
            "5/5 Create row view",
            [python, "create_row_view.py"],
            cwd=SRC_DIR,
        )
    except subprocess.CalledProcessError as exc:
        print(f"\nPipeline failed in step command: {exc.cmd}", file=sys.stderr)
        print(f"Exit code: {exc.returncode}", file=sys.stderr)
        return exc.returncode

    print("\nPipeline completed successfully.", flush=True)
    print("Expected outputs include:", flush=True)
    print("- data/transformed/ (transformed Excel files)", flush=True)
    print("- data/transformed/analysis_results/sequence_analysis.csv", flush=True)
    print("- src/extracted_sequences.csv", flush=True)
    print("- src/übersicht_situationen_länge_pro_datei.csv and .xlsx", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
