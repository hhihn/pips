import re
import csv
from collections import defaultdict


def parse_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by "File:" blocks
    file_blocks = re.split(r"\n(?=File:)", content.strip())
    print(file_blocks)
    # Data structure to store count of (code, rank)
    code_rank_count = defaultdict(lambda: defaultdict(int))

    for block in file_blocks:
        # Find all "Sequence" parts inside the block
        sequences = re.findall(
            r"↳ Sequence \(\d+ events\):\s*((?:\s*\d+\.\s+.+?$$[^)]+$$\s*$$[^)]+$$\s*)+)",
            block,
            re.DOTALL,
        )

        print(sequences[0])
        for seq in sequences:
            lines = seq.strip().split("\n")
            for line in lines:
                match = re.match(r"^\s*(\d+)\.\s*([\d\.]+)", line.strip())
                if match:
                    rank = int(match.group(1))
                    code = match.group(2)
                    code_rank_count[code][rank] += 1

    return code_rank_count


def save_to_csv(data, output_file="code_rank_counts.csv"):
    # Get all unique codes and sort them
    all_codes = sorted(data.keys(), key=lambda x: [int(part) for part in x.split(".")])

    # Determine max rank seen across all codes
    max_rank = max(max(ranks.keys()) for ranks in data.values()) if data else 0

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        # Write header row: Code, Rank_1, Rank_2, ..., Rank_N
        header = ["Code"] + [f"Rank_{i}" for i in range(1, max_rank + 1)]
        writer.writerow(header)

        # Write rows for each code
        for code in all_codes:
            row = [code]
            ranks_dict = data[code]
            for rank in range(1, max_rank + 1):
                row.append(ranks_dict.get(rank, 0))
            writer.writerow(row)


# --- Run the script ---
input_file = "../data/transformed/analysis_results/analysis_summary.txt"  # Replace with your actual input file path
output_csv = "code_rank_counts.csv"

counts = parse_file(input_file)
save_to_csv(counts, output_csv)

print(f"Results saved to {output_csv}")
