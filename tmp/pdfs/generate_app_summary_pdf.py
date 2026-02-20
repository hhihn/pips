from pathlib import Path
import matplotlib.pyplot as plt

output_pdf = Path('output/pdf/pips_app_summary_one_page.pdf')
preview_png = Path('tmp/pdfs/pips_app_summary_one_page_preview.png')
output_pdf.parent.mkdir(parents=True, exist_ok=True)
preview_png.parent.mkdir(parents=True, exist_ok=True)

lines = [
    ("PIPS Repo - One-Page App Summary", 16, 'bold'),
    ("", 11, 'normal'),
    ("What it is", 12, 'bold'),
    (
        "A Python analysis toolkit for coded educational video/event data.",
        10,
        'normal',
    ),
    (
        "It transforms source Excel files, detects temporal code patterns, and produces CSV/XLSX/plot outputs.",
        10,
        'normal',
    ),
    ("", 11, 'normal'),
    ("Who it is for", 12, 'bold'),
    (
        "Primary persona: education/behavior researchers or analysts working with time-coded observation data.",
        10,
        'normal',
    ),
    (
        "Evidence: module docstrings reference educational video coding and temporal pattern detection.",
        9,
        'normal',
    ),
    ("", 11, 'normal'),
    ("What it does", 12, 'bold'),
    ("- Transforms raw Excel code columns into normalized files under data/transformed/.", 10, 'normal'),
    ("- Detects temporal relationships among code families (5.4.*, 6.1.1, 6.2.*, 5.5.*).", 10, 'normal'),
    ("- Extracts ordered code sequences and tags outputs (for example PK/AK/NA).", 10, 'normal'),
    ("- Exports analysis artifacts (summary, detailed, matched pairs, sequence CSV files).", 10, 'normal'),
    ("- Builds row-view summary tables and XLSX outputs for downstream review.", 10, 'normal'),
    ("- Produces visual analytics scripts (stacked frequency charts, clustering, sunburst, transition graphs).", 10, 'normal'),
    ("", 11, 'normal'),
    ("How it works (repo-evidence architecture)", 12, 'bold'),
    ("- Input: data/*.xlsx", 10, 'normal'),
    ("- transform_data.py -> data/transformed/*.xlsx (normalizes Code column)", 10, 'normal'),
    ("- src/detect_codes_within.py -> PatternAnalyzer orchestrates PatternDetector + SequenceAnalyzer + TimeConverter", 10, 'normal'),
    ("- ResultExporter writes data/transformed/analysis_results/*.csv", 10, 'normal'),
    ("- src/analyse_order.py reads sequence_analysis.csv -> src/extracted_sequences.csv", 10, 'normal'),
    ("- src/count_analysis.py and src/create_row_view.py consume extracted CSV for charts/tables", 10, 'normal'),
    ("", 11, 'normal'),
    ("How to run (minimal)", 12, 'bold'),
    ("1. Run: python transform_data.py", 10, 'normal'),
    ("2. Run: python src/detect_codes_within.py", 10, 'normal'),
    ("3. Run: python src/analyse_order.py", 10, 'normal'),
    ("4. Optional outputs: python src/count_analysis.py and python src/create_row_view.py", 10, 'normal'),
    ("5. Exact dependency install command: Not found in repo.", 10, 'normal'),
    ("6. Deployment/runtime service info: Not found in repo.", 10, 'normal'),
]

fig = plt.figure(figsize=(8.5, 11))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_axis_off()

left = 0.07
y = 0.96

for text, size, weight in lines:
    if text == "":
        y -= 0.018
        continue

    ax.text(
        left,
        y,
        text,
        fontsize=size,
        fontweight=weight,
        family='DejaVu Sans',
        va='top',
        ha='left',
        wrap=True,
    )

    if size >= 16:
        y -= 0.038
    elif size >= 12:
        y -= 0.027
    else:
        y -= 0.021

if y < 0.04:
    raise RuntimeError(f"Content overflowed page (final y={y:.3f})")

fig.savefig(output_pdf, format='pdf', dpi=300, bbox_inches='tight', pad_inches=0.25)
fig.savefig(preview_png, format='png', dpi=200, bbox_inches='tight', pad_inches=0.25)
print(str(output_pdf.resolve()))
print(str(preview_png.resolve()))
