import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx
from collections import defaultdict, Counter


def create_transition_graph_banded_edges(
    csv_file_path,
    output_image_path="grouped_transition_graph.png",
    min_probability=0.01,
    group_code="",
):
    """
    Create a probability‑based transition graph with START/END nodes.
    Only the first three rows per file are used for building the sequence graph.
    Node positions are automatically chosen by NetworkX.
    """

    # ---- Load CSV ---------------------------------------------------------------
    try:
        df = pd.read_csv(csv_file_path)
        required = ["Filename", "Sequence_Code"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return None

    # ---- Sort by time if available ----------------------------------------------
    if "Sequence_Start" in df.columns:

        def parse_time(t):
            if pd.isna(t):
                return 0
            t = str(t).replace(",", ".")
            parts = t.split(":")
            try:
                if len(parts) == 3:
                    h, m, s = map(float, parts)
                    return h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = map(float, parts)
                    return m * 60 + s
                return float(t)
            except ValueError:
                return 0

        df["sort_time"] = df["Sequence_Start"].apply(parse_time)
        df = df.sort_values(["Filename", "sort_time"])

    # ---- ✅ Keep first 3 rows per file -----------------------------------------
    grouping_col = "id" if "id" in df.columns else "Filename"
    df = df.groupby(grouping_col, group_keys=False).head(3)

    # ---- Count transitions -----------------------------------------------------
    transitions = defaultdict(Counter)
    state_counts = Counter()
    start_nodes = Counter()
    end_nodes = Counter()
    total_sequences = 0
    extended_group_code = f"{group_code} PK"

    for fname in df[grouping_col].unique():
        fdata = df[df[grouping_col] == fname]
        codes = fdata["Sequence_Code"].dropna().tolist()
        if not codes or (group_code and extended_group_code not in codes):
            continue

        total_sequences += 1
        clean = [c for c in codes if "AK" not in c and group_code not in c]
        if not clean:
            continue

        # tally start & transitions
        start_nodes[clean[0]] += 1
        for i in range(len(clean) - 1):
            transitions[clean[i]][clean[i + 1]] += 1
            state_counts[clean[i]] += 1
        state_counts[clean[-1]] += 1
        end_nodes[clean[-1]] += 1

    # ---- Probabilities ---------------------------------------------------------
    start_probs = {n: c / total_sequences for n, c in start_nodes.items()}
    end_probs = {n: c / total_sequences for n, c in end_nodes.items()}
    transition_probs = defaultdict(dict)

    for src, targets in transitions.items():
        total_out = sum(targets.values())
        for tgt, count in targets.items():
            p = count / total_out
            if p >= min_probability:
                transition_probs[src][tgt] = p

    # ---- Build Graph -----------------------------------------------------------
    G = nx.DiGraph()
    for node, count in state_counts.items():
        G.add_node(
            node,
            count=count,
            is_start=node in start_probs,
            is_end=node in end_probs,
        )

    for src, tgts in transition_probs.items():
        for tgt, p in tgts.items():
            G.add_edge(src, tgt, weight=p, label=f"{p:.2f}")

    # Add START and END virtual nodes
    if start_probs:
        G.add_node("START", synthetic=True)
        for n, p in start_probs.items():
            G.add_edge("START", n, weight=p, label=f"{p:.2f}")
    if end_probs:
        G.add_node("END", synthetic=True)
        for n, p in end_probs.items():
            G.add_edge(n, "END", weight=p, label=f"{p:.2f}")

    # ---- ❌ Manual positioning removed → automatic layout ----------------------
    pos = nx.spring_layout(G, seed=42)  # or kamada_kawai_layout, etc.

    # ---- Draw ------------------------------------------------------------------
    plt.figure(figsize=(20, 10))

    regular = [
        n
        for n in G.nodes
        if n not in ("START", "END")
        and not G.nodes[n].get("is_start")
        and not G.nodes[n].get("is_end")
    ]
    starts = [n for n in G.nodes if G.nodes[n].get("is_start")]
    ends = [n for n in G.nodes if G.nodes[n].get("is_end")]

    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=regular,
        node_color="lightblue",
        node_size=700,
        alpha=0.85,
        label="Regular",
    )
    nx.draw_networkx_nodes(
        G, pos, nodelist=starts, node_color="orange", node_size=850, label="Start Nodes"
    )
    nx.draw_networkx_nodes(
        G, pos, nodelist=ends, node_color="red", node_size=850, label="End Nodes"
    )
    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=["START"],
        node_color="lightgreen",
        node_size=1000,
        label="START",
    )
    nx.draw_networkx_nodes(
        G, pos, nodelist=["END"], node_color="purple", node_size=1000, label="END"
    )

    nx.draw_networkx_edges(
        G, pos, width=2.5, edge_color="gray", alpha=0.7, arrows=True, arrowsize=18
    )
    nx.draw_networkx_labels(G, pos, font_size=14, font_weight="bold")
    edge_labels = nx.get_edge_attributes(G, "label")
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=12)

    plt.title(
        "Transition Graph (first 3 lines per file, automatic layout)",
        fontsize=14,
    )
    plt.legend(loc="upper right", frameon=False)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_image_path, dpi=300, bbox_inches="tight")
    plt.show()

    print(f"Graph created with {len(G.nodes())} nodes and {len(G.edges())} edges.")
    return G


# ---------- Example usage ----------
if __name__ == "__main__":
    csv_file = "extracted_sequences.csv"
    output_image = "transition_graph_auto.png"
    G = create_transition_graph_banded_edges(
        csv_file,
        output_image,
        min_probability=0.25,
        group_code="6.1.1",
    )
