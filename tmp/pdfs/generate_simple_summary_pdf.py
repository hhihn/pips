from pathlib import Path

out_path = Path('output/pdf/pips_app_summary_one_page.pdf')
out_path.parent.mkdir(parents=True, exist_ok=True)

content = [
    ('PIPS Repo - One-Page App Summary', 16),
    ('', 10),
    ('What it is', 12),
    ('A Python analysis toolkit for coded educational video/event data.', 10),
    ('It transforms source Excel files, detects temporal code patterns, and produces CSV/XLSX/plot outputs.', 10),
    ('', 10),
    ('Who it is for', 12),
    ('Primary persona: education/behavior researchers or analysts working with time-coded observation data.', 10),
    ('Evidence: module docstrings reference educational video coding and temporal pattern detection.', 10),
    ('', 10),
    ('What it does', 12),
    ('- Transforms raw Excel code columns into normalized files under data/transformed/.', 10),
    ('- Detects temporal relationships among code families (5.4.*, 6.1.1, 6.2.*, 5.5.*).', 10),
    ('- Extracts ordered code sequences and tags outputs (for example PK/AK/NA).', 10),
    ('- Exports analysis artifacts (summary, detailed, matched pairs, sequence CSV files).', 10),
    ('- Builds row-view summary tables and XLSX outputs for downstream review.', 10),
    ('- Produces visual analytics scripts (stacked charts, clustering, sunburst, transition graphs).', 10),
    ('', 10),
    ('How it works (repo-evidence architecture)', 12),
    ('- Input: data/*.xlsx', 10),
    ('- transform_data.py -> data/transformed/*.xlsx (normalizes Code column)', 10),
    ('- src/detect_codes_within.py -> PatternAnalyzer orchestrates PatternDetector + SequenceAnalyzer + TimeConverter', 10),
    ('- ResultExporter writes data/transformed/analysis_results/*.csv', 10),
    ('- src/analyse_order.py reads sequence_analysis.csv -> src/extracted_sequences.csv', 10),
    ('- src/count_analysis.py and src/create_row_view.py consume extracted CSV for charts/tables', 10),
    ('', 10),
    ('How to run (minimal)', 12),
    ('1. Run: python transform_data.py', 10),
    ('2. Run: python src/detect_codes_within.py', 10),
    ('3. Run: python src/analyse_order.py', 10),
    ('4. Optional: python src/count_analysis.py and python src/create_row_view.py', 10),
    ('5. Exact dependency install command: Not found in repo.', 10),
    ('6. Deployment/runtime service info: Not found in repo.', 10),
]


def pdf_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

lines = []
y = 770
left = 54

for text, size in content:
    if text == '':
        y -= 8
        continue

    if size == 16:
        leading = 20
    elif size == 12:
        leading = 16
    else:
        leading = 13

    lines.append(f"BT /F1 {size} Tf 1 0 0 1 {left} {y} Tm ({pdf_escape(text)}) Tj ET")
    y -= leading

if y < 35:
    raise RuntimeError(f'Content overflow: y={y}')

stream = '\n'.join(lines) + '\n'
stream_bytes = stream.encode('latin-1', errors='replace')

objects = []
objects.append('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
objects.append('2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
objects.append('3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n')
objects.append('4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')
objects.append(f'5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n{stream}endstream\nendobj\n')

pdf = bytearray(b'%PDF-1.4\n')
offsets = [0]
for obj in objects:
    offsets.append(len(pdf))
    pdf.extend(obj.encode('latin-1'))

xref_start = len(pdf)
count = len(objects) + 1
pdf.extend(f'xref\n0 {count}\n'.encode('latin-1'))
pdf.extend(b'0000000000 65535 f \n')
for i in range(1, count):
    pdf.extend(f'{offsets[i]:010d} 00000 n \n'.encode('latin-1'))

pdf.extend(f'trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n'.encode('latin-1'))

out_path.write_bytes(pdf)
print(str(out_path.resolve()))
print(f'final_y={y}')
