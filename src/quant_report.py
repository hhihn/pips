import pandas as pd
import numpy as np
from collections import defaultdict, Counter
from itertools import combinations
from typing import Dict, List, Tuple, Set
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from scipy.cluster.hierarchy import dendrogram, linkage, fcluster
from scipy.spatial.distance import squareform


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def time_to_seconds(time_str: str) -> float:
    """Convert time string like '0:00:29,6' to seconds."""
    if not isinstance(time_str, str) or not time_str.strip():
        return 0.0
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
    except ValueError:
        pass
    return 0.0


def extract_base_code(code: str) -> str:
    """Extract numeric code without PK/AK suffix."""
    if pd.isna(code):
        return ""
    return code.replace(" PK", "").replace(" AK", "").strip()


def load_and_prepare_data(csv_path: str) -> pd.DataFrame:
    """Load CSV and add computed columns."""
    df = pd.read_csv(csv_path)
    df['base_code'] = df['Sequence_Code'].apply(extract_base_code)
    df['child_type'] = df['Sequence_Code'].str.extract(r' (PK|AK)$')[0].fillna('NA')
    df['start_sec'] = df['Sequence_Start'].apply(time_to_seconds)
    df['end_sec'] = df['Sequence_End'].apply(time_to_seconds)
    df['duration'] = df['end_sec'] - df['start_sec']
    return df


# =============================================================================
# 1. GRUNDLEGENDE HÄUFIGKEITSANALYSEN
# =============================================================================

def analyze_code_frequencies(df: pd.DataFrame) -> Dict:
    """Analyze basic frequency statistics for codes."""

    results = {
        'code_counts': df['base_code'].value_counts().to_dict(),
        'codes_per_situation': df.groupby('id')['base_code'].nunique().describe().to_dict(),
        'situations_per_code': df.groupby('base_code')['id'].nunique().to_dict(),
    }

    # Prevalence: In wie vielen Situationen kommt jeder Code vor?
    n_situations = df['id'].nunique()
    results['code_prevalence'] = {
        code: count / n_situations
        for code, count in results['situations_per_code'].items()
    }

    return results


def print_frequency_analysis(results: Dict):
    """Pretty print frequency analysis."""
    print("=" * 80)
    print("HÄUFIGKEITSANALYSE")
    print("=" * 80)

    print("\n1. Häufigste Codes (absolute Anzahl):")
    print("-" * 40)
    sorted_counts = sorted(results['code_counts'].items(), key=lambda x: x[1], reverse=True)
    for code, count in sorted_counts[:15]:
        print(f"  {code:15} : {count:4d}x")

    print("\n2. Codes pro Situation (Statistik):")
    print("-" * 40)
    stats = results['codes_per_situation']
    print(f"  Mittelwert: {stats['mean']:.1f}")
    print(f"  Median:     {stats['50%']:.1f}")
    print(f"  Min:        {stats['min']:.0f}")
    print(f"  Max:        {stats['max']:.0f}")
    print(f"  Std:        {stats['std']:.1f}")

    print("\n3. Code-Prävalenz (% der Situationen):")
    print("-" * 40)
    sorted_prev = sorted(results['code_prevalence'].items(), key=lambda x: x[1], reverse=True)
    for code, prev in sorted_prev[:15]:
        print(f"  {code:15} : {prev:6.1%}")


# =============================================================================
# 2. CO-OCCURRENCE ANALYSE (Welche Codes kommen gemeinsam vor?)
# =============================================================================

def analyze_co_occurrence(df: pd.DataFrame,
                          time_tolerance: float = 0.5) -> Dict:
    """
    Analyze which codes occur together.

    Returns:
        Dict with co-occurrence matrices and statistics
    """
    all_codes = sorted(df['base_code'].unique())
    n_codes = len(all_codes)
    code_to_idx = {code: i for i, code in enumerate(all_codes)}

    # Matrix für gemeinsames Auftreten in gleicher Situation
    situation_cooccurrence = np.zeros((n_codes, n_codes), dtype=int)

    # Matrix für zeitlich überlappende Codes
    temporal_cooccurrence = np.zeros((n_codes, n_codes), dtype=int)

    # Matrix für Codes mit identischer Startzeit
    simultaneous_cooccurrence = np.zeros((n_codes, n_codes), dtype=int)

    for situation_id in df['id'].unique():
        situation_df = df[df['id'] == situation_id]
        codes_in_situation = situation_df['base_code'].unique()

        # Situation-level co-occurrence
        for code1, code2 in combinations(codes_in_situation, 2):
            i, j = code_to_idx[code1], code_to_idx[code2]
            situation_cooccurrence[i, j] += 1
            situation_cooccurrence[j, i] += 1

        # Temporal co-occurrence (überlappende Zeitintervalle)
        for idx1, row1 in situation_df.iterrows():
            for idx2, row2 in situation_df.iterrows():
                if idx1 >= idx2:
                    continue

                code1, code2 = row1['base_code'], row2['base_code']
                if code1 == code2:
                    continue

                # Check temporal overlap
                if row1['start_sec'] <= row2['end_sec'] and row1['end_sec'] >= row2['start_sec']:
                    i, j = code_to_idx[code1], code_to_idx[code2]
                    temporal_cooccurrence[i, j] += 1
                    temporal_cooccurrence[j, i] += 1

                # Check simultaneous start
                if abs(row1['start_sec'] - row2['start_sec']) <= time_tolerance:
                    i, j = code_to_idx[code1], code_to_idx[code2]
                    simultaneous_cooccurrence[i, j] += 1
                    simultaneous_cooccurrence[j, i] += 1

    return {
        'codes': all_codes,
        'code_to_idx': code_to_idx,
        'situation_matrix': situation_cooccurrence,
        'temporal_matrix': temporal_cooccurrence,
        'simultaneous_matrix': simultaneous_cooccurrence,
    }


def get_top_co_occurrences(cooc_result: Dict,
                           matrix_type: str = 'temporal',
                           top_n: int = 20) -> List[Tuple]:
    """Get top co-occurring code pairs."""

    if matrix_type == 'situation':
        matrix = cooc_result['situation_matrix']
    elif matrix_type == 'temporal':
        matrix = cooc_result['temporal_matrix']
    else:
        matrix = cooc_result['simultaneous_matrix']

    codes = cooc_result['codes']
    pairs = []

    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            if matrix[i, j] > 0:
                pairs.append((codes[i], codes[j], matrix[i, j]))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs[:top_n]


def get_never_co_occurring(cooc_result: Dict,
                           min_individual_count: int = 5,
                           df: pd.DataFrame = None) -> List[Tuple]:
    """Find code pairs that never occur together despite being common."""

    matrix = cooc_result['situation_matrix']
    codes = cooc_result['codes']

    # Get code frequencies
    code_counts = df['base_code'].value_counts().to_dict() if df is not None else {}

    never_together = []

    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            if matrix[i, j] == 0:
                code1, code2 = codes[i], codes[j]
                count1 = code_counts.get(code1, 0)
                count2 = code_counts.get(code2, 0)

                # Only include if both codes are reasonably common
                if count1 >= min_individual_count and count2 >= min_individual_count:
                    never_together.append((code1, code2, count1, count2))

    # Sort by combined frequency (most surprising absences first)
    never_together.sort(key=lambda x: x[2] + x[3], reverse=True)
    return never_together


def visualize_co_occurrence_matrix(cooc_result: Dict,
                                   matrix_type: str = 'temporal',
                                   min_count: int = 3,
                                   save_path: str = None) -> plt.Figure:
    """Create heatmap of co-occurrence matrix."""

    if matrix_type == 'situation':
        matrix = cooc_result['situation_matrix']
        title = 'Co-Occurrence in gleicher Situation'
    elif matrix_type == 'temporal':
        matrix = cooc_result['temporal_matrix']
        title = 'Zeitliche Überlappung'
    else:
        matrix = cooc_result['simultaneous_matrix']
        title = 'Simultaner Start'

    codes = cooc_result['codes']

    # Filter to codes with sufficient co-occurrence
    row_sums = matrix.sum(axis=1)
    active_mask = row_sums >= min_count
    filtered_matrix = matrix[active_mask][:, active_mask]
    filtered_codes = [c for c, m in zip(codes, active_mask) if m]

    if len(filtered_codes) == 0:
        print("No codes meet the minimum count threshold")
        return None

    # Create figure
    fig_size = max(10, len(filtered_codes) * 0.5)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))

    # Mask diagonal
    mask = np.eye(len(filtered_codes), dtype=bool)

    sns.heatmap(
        filtered_matrix,
        xticklabels=filtered_codes,
        yticklabels=filtered_codes,
        annot=True,
        fmt='d',
        cmap='YlOrRd',
        mask=mask,
        ax=ax,
        cbar_kws={'label': 'Anzahl'},
        linewidths=0.5
    )

    ax.set_title(f'Co-Occurrence Matrix: {title}', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.yticks(rotation=0, fontsize=9)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")

    plt.show()
    return fig


# =============================================================================
# 3. ASSOZIATIONSANALYSE (Lift, Jaccard, etc.)
# =============================================================================

def compute_association_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute association metrics between code pairs.

    Metrics:
    - Support: P(A and B)
    - Confidence: P(B|A)
    - Lift: P(A and B) / (P(A) * P(B))
    - Jaccard: |A ∩ B| / |A ∪ B|
    """

    n_situations = df['id'].nunique()

    # Get codes present in each situation
    situation_codes = df.groupby('id')['base_code'].apply(set).to_dict()

    # Count occurrences of each code
    code_counts = Counter()
    for codes in situation_codes.values():
        code_counts.update(codes)

    # Count co-occurrences
    pair_counts = Counter()
    for codes in situation_codes.values():
        for pair in combinations(sorted(codes), 2):
            pair_counts[pair] += 1

    # Compute metrics
    results = []

    for (code_a, code_b), count_ab in pair_counts.items():
        count_a = code_counts[code_a]
        count_b = code_counts[code_b]

        # Support
        support = count_ab / n_situations

        # Confidence (both directions)
        confidence_a_to_b = count_ab / count_a if count_a > 0 else 0
        confidence_b_to_a = count_ab / count_b if count_b > 0 else 0

        # Lift
        expected = (count_a / n_situations) * (count_b / n_situations)
        lift = support / expected if expected > 0 else 0

        # Jaccard
        union = count_a + count_b - count_ab
        jaccard = count_ab / union if union > 0 else 0

        results.append({
            'code_a': code_a,
            'code_b': code_b,
            'count_a': count_a,
            'count_b': count_b,
            'count_ab': count_ab,
            'support': support,
            'confidence_a_to_b': confidence_a_to_b,
            'confidence_b_to_a': confidence_b_to_a,
            'lift': lift,
            'jaccard': jaccard,
        })

    return pd.DataFrame(results)


def print_association_analysis(assoc_df: pd.DataFrame, top_n: int = 15):
    """Print top associations by different metrics."""

    print("=" * 80)
    print("ASSOZIATIONSANALYSE")
    print("=" * 80)

    print("\n1. Stärkste positive Assoziationen (nach Lift):")
    print("-" * 60)
    print("   Lift > 1: Codes kommen häufiger zusammen als erwartet")
    top_lift = assoc_df.nlargest(top_n, 'lift')
    for _, row in top_lift.iterrows():
        print(f"   {row['code_a']:12} + {row['code_b']:12} | "
              f"Lift: {row['lift']:5.2f} | "
              f"Jaccard: {row['jaccard']:.2f} | "
              f"n={row['count_ab']}")

    print("\n2.Höchste Jaccard-Ähnlichkeit:")
    print("-" * 60)
    top_jaccard = assoc_df.nlargest(top_n, 'jaccard')
    for _, row in top_jaccard.iterrows():
        print(f"   {row['code_a']:12} + {row['code_b']:12} | "
              f"Jaccard: {row['jaccard']:.2f} | "
              f"n={row['count_ab']}")

    print("\n3. Stärkste Implikationen (Confidence):")
    print("-" * 60)
    print("   'Wenn A, dann meist auch B'")
    # Create expanded view for both directions
    implications = []
    for _, row in assoc_df.iterrows():
        if row['count_ab'] >= 3:  # Minimum support
            implications.append({
                'condition': row['code_a'],
                'consequence': row['code_b'],
                'confidence': row['confidence_a_to_b'],
                'count': row['count_ab']
            })
            implications.append({
                'condition': row['code_b'],
                'consequence': row['code_a'],
                'confidence': row['confidence_b_to_a'],
                'count': row['count_ab']
            })

    impl_df = pd.DataFrame(implications)
    impl_df = impl_df.sort_values('confidence', ascending=False).head(top_n)

    for _, row in impl_df.iterrows():
        print(f"   {row['condition']:12} → {row['consequence']:12} | "
              f"Conf: {row['confidence']:.0%} | n={row['count']}")


# =============================================================================
# 4. DAUER-ANALYSE
# =============================================================================

def analyze_durations(df: pd.DataFrame) -> Dict:
    """Analyze code durations."""

    # Duration by code
    duration_by_code = df.groupby('base_code')['duration'].agg([
        'count', 'mean', 'std', 'min', 'max', 'median'
    ]).round(2)

    # Total duration per situation
    situation_durations = df.groupby('id').apply(
        lambda x: x['end_sec'].max() - x['start_sec'].min()
    )

    # Duration by phase (6.1.x codes)
    phase_codes = ['6.1.1', '6.1.2', '6.1.3', '6.1.4']
    phase_durations = df[df['base_code'].isin(phase_codes)].groupby('base_code')['duration']

    return {
        'by_code': duration_by_code,
        'situation_durations': situation_durations,
        'phase_durations': {code: phase_durations.get_group(code).describe()
                            for code in phase_codes if code in phase_durations.groups}
    }


def visualize_duration_analysis(df: pd.DataFrame, save_path: str = None):
    """Create duration visualizations."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # 1. Duration by phase
    ax1 = axes[0, 0]
    phase_codes = ['6.1.1', '6.1.2', '6.1.3', '6.1.4']
    phase_df = df[df['base_code'].isin(phase_codes)].copy()
    phase_labels = {
        '6.1.1': 'Gesamt',
        '6.1.2': 'Trans. vor',
        '6.1.3': 'Handlung',
        '6.1.4': 'Trans. nach'
    }
    phase_df['phase_label'] = phase_df['base_code'].map(phase_labels)

    sns.boxplot(data=phase_df, x='phase_label', y='duration',
                order=['Gesamt', 'Trans. vor', 'Handlung', 'Trans. nach'],
                palette='Set2', ax=ax1)
    ax1.set_xlabel('Phase')
    ax1.set_ylabel('Dauer (Sekunden)')
    ax1.set_title('Dauer nach Pflegephase')

    # 2. Duration by care type (6.2.x)
    ax2 = axes[0, 1]
    care_df = df[df['base_code'].str.startswith('6.2')].copy()
    if not care_df.empty:
        care_counts = care_df['base_code'].value_counts()
        top_care = care_counts.head(5).index.tolist()
        care_df_filtered = care_df[care_df['base_code'].isin(top_care)]
        sns.boxplot(data=care_df_filtered, x='base_code', y='duration',
                    palette='Set3', ax=ax2)
        ax2.set_xlabel('Art der Pflege')
        ax2.set_ylabel('Dauer (Sekunden)')
        ax2.set_title('Dauer nach Pflegeart')
        plt.sca(ax2)
        plt.xticks(rotation=45, ha='right')

    # 3. Body contact duration (2.2.x)
    ax3 = axes[1, 0]
    contact_df = df[df['base_code'].str.startswith('2.2')].copy()
    if not contact_df.empty:
        contact_counts = contact_df['base_code'].value_counts()
        top_contact = contact_counts.head(6).index.tolist()
        contact_df_filtered = contact_df[contact_df['base_code'].isin(top_contact)]
        sns.boxplot(data=contact_df_filtered, x='base_code', y='duration',
                    palette='Pastel1', ax=ax3)
        ax3.set_xlabel('Körperkontakt-Typ')
        ax3.set_ylabel('Dauer (Sekunden)')
        ax3.set_title('Dauer von Körperkontakt')
        plt.sca(ax3)
        plt.xticks(rotation=45, ha='right')

    # 4. Situation total duration distribution
    ax4 = axes[1, 1]
    situation_durations = df.groupby('id').apply(
        lambda x: x['end_sec'].max() - x['start_sec'].min()
    )
    ax4.hist(situation_durations, bins=20, edgecolor='black', alpha=0.7, color='steelblue')
    ax4.axvline(situation_durations.mean(), color='red', linestyle='--',
                label=f'Mittel: {situation_durations.mean():.1f}s')
    ax4.axvline(situation_durations.median(), color='orange', linestyle='--',
                label=f'Median: {situation_durations.median():.1f}s')
    ax4.set_xlabel('Gesamtdauer (Sekunden)')
    ax4.set_ylabel('Anzahl Situationen')
    ax4.set_title('Verteilung der Situationsdauer')
    ax4.legend()

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")

    plt.show()
    return fig


# =============================================================================
# 5. CLUSTERING VON SITUATIONEN
# =============================================================================

def cluster_situations(df: pd.DataFrame, n_clusters: int = 5) -> Dict:
    """Cluster situations based on code profiles."""

    # Create situation × code matrix
    exclude_prefixes = ["6.1", "6.2"]
    df_filtered = df[~df['base_code'].apply(
        lambda x: any(x.startswith(prefix) for prefix in exclude_prefixes)
    )].copy()
    print(df_filtered.columns)
    print(df_filtered.columns)
    df['fachkraft'] = df['Filename'].apply(extract_fachkraft_id)
    situation_codes = df_filtered.groupby(['fachkraft', 'base_code']).size().unstack(fill_value=0)

    # Binary version (present/absent)
    binary_matrix = (situation_codes > 0).astype(int)

    # Hierarchical clustering
    if len(binary_matrix) > 1:
        linkage_matrix = linkage(binary_matrix.values, method='ward')
        clusters = fcluster(linkage_matrix, n_clusters, criterion='maxclust')

        situation_codes['cluster'] = clusters

        # Characterize clusters
        cluster_profiles = {}
        for cluster_id in range(1, n_clusters + 1):
            cluster_situations = situation_codes[situation_codes['cluster'] == cluster_id]
            cluster_profile = cluster_situations.drop('cluster', axis=1).mean()
            cluster_profiles[cluster_id] = {
                'n_situations': len(cluster_situations),
                'common_codes': cluster_profile[cluster_profile > 0.5].index.tolist(),
                'mean_profile': cluster_profile.to_dict()
            }

        return {
            'situation_codes': situation_codes,
            'binary_matrix': binary_matrix,
            'linkage_matrix': linkage_matrix,
            'clusters': clusters,
            'cluster_profiles': cluster_profiles
        }

    return None


def visualize_situation_clusters(cluster_result: Dict, save_path: str = None):
    """Visualize situation clustering."""

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    # 1. Dendrogram
    ax1 = axes[0]
    dendrogram(
        cluster_result['linkage_matrix'],
        ax=ax1,
        leaf_rotation=90,
        leaf_font_size=8
    )
    ax1.set_title('Hierarchisches Clustering der Situationen')
    ax1.set_xlabel('Situation')
    ax1.set_ylabel('Distanz')

    # 2. Cluster sizes and characteristics
    ax2 = axes[1]
    profiles = cluster_result['cluster_profiles']
    cluster_ids = list(profiles.keys())
    sizes = [profiles[c]['n_situations'] for c in cluster_ids]

    bars = ax2.bar(cluster_ids, sizes, color='steelblue', edgecolor='black')
    ax2.set_xlabel('Cluster')
    ax2.set_ylabel('Anzahl Situationen')
    ax2.set_title('Cluster-Größen')

    # Add common codes as annotations
    for i, cluster_id in enumerate(cluster_ids):
        common = profiles[cluster_id]['common_codes'][:3]
        if common:
            ax2.annotate(
                '\n'.join(common),
                xy=(cluster_id, sizes[i]),
                xytext=(0, 5),
                textcoords='offset points',
                ha='center',
                va='bottom',
                fontsize=7,
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8)
            )

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")

    plt.show()
    return fig


# =============================================================================
# 6. VERGLEICH ZWISCHEN FACHKRÄFTEN
# =============================================================================

def extract_fachkraft_id(filename: str) -> str:
    """Extract Fachkraft ID from filename like '11-P-4_transformed.xlsx'."""
    parts = filename.split('-')
    if len(parts) >= 1:
        id = parts[0]
        print(f"got {id} from {filename}")
        return id
    return 'unknown'


def analyze_by_fachkraft(df: pd.DataFrame) -> pd.DataFrame:
    """Compare code usage across Fachkräfte."""

    df = df.copy()
    df['fachkraft'] = df['Filename'].apply(extract_fachkraft_id)

    # Codes per Fachkraft
    fk_codes = df.groupby(['fachkraft', 'base_code']).size().unstack(fill_value=0)

    # Normalize by number of situations
    situations_per_fk = df.groupby('fachkraft')['id'].nunique()
    fk_codes_normalized = fk_codes.div(situations_per_fk, axis=0)

    return {
        'raw_counts': fk_codes,
        'normalized': fk_codes_normalized,
        'situations_per_fk': situations_per_fk
    }


def visualize_fachkraft_comparison(fk_result: Dict,
                                   codes_to_compare: List[str] = None,
                                   save_path: str = None):
    """Compare code usage across Fachkräfte."""

    normalized = fk_result['normalized']

    if codes_to_compare is None:
        # Use most variable codes
        code_variance = normalized.var()
        codes_to_compare = code_variance.nlargest(8).index.tolist()

    # Filter to selected codes
    plot_data = normalized[codes_to_compare]

    fig, ax = plt.subplots(figsize=(14, 8))

    plot_data.plot(kind='bar', ax=ax, width=0.8)

    ax.set_xlabel('Fachkraft')
    ax.set_ylabel('Codes pro Situation')
    ax.set_title('Code-Verwendung nach Fachkraft (normalisiert)')
    ax.legend(title='Code', bbox_to_anchor=(1.02, 1), loc='upper left')

    plt.xticks(rotation=0)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")

    plt.show()
    return fig


# =============================================================================
# 7. VOLLSTÄNDIGER ANALYSEBERICHT
# =============================================================================

def generate_full_report(csv_path: str, output_dir: str = 'analysis_report'):
    """Generate complete analysis report."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    print("Loading data...")
    df = load_and_prepare_data(csv_path)
    print(f"Loaded {len(df)} rows, {df['id'].nunique()} situations, "
          f"{df['base_code'].nunique()} unique codes")

    # 1. Frequency Analysis
    print("\n" + "=" * 80)
    freq_results = analyze_code_frequencies(df)
    print_frequency_analysis(freq_results)

    # 2. Co-occurrence Analysis
    print("\n" + "=" * 80)
    print("COMPUTING CO-OCCURRENCE...")
    cooc_results = analyze_co_occurrence(df)

    print("\nHäufigste zeitliche Überlappungen:")
    top_temporal = get_top_co_occurrences(cooc_results, 'temporal', 15)
    for code1, code2, count in top_temporal:
        print(f"  {code1:12} + {code2:12} : {count:3d}x")

    print("\nCodes, die NIE gemeinsam vorkommen (trotz Häufigkeit):")
    never = get_never_co_occurring(cooc_results, min_individual_count=10, df=df)
    for code1, code2, c1, c2 in never[:10]:
        print(f"  {code1:12} ({c1}x) + {code2:12} ({c2}x)")

    visualize_co_occurrence_matrix(
        cooc_results, 'temporal', min_count=3,
        save_path=f'{output_dir}/cooccurrence_temporal.png'
    )

    visualize_co_occurrence_matrix(
        cooc_results, 'simultaneous', min_count=2,
        save_path=f'{output_dir}/cooccurrence_simultaneous.png'
    )

    # 3. Association Analysis
    print("\n")
    assoc_df = compute_association_metrics(df)
    print_association_analysis(assoc_df)
    assoc_df.to_csv(f'{output_dir}/association_metrics.csv', index=False)

    # 4. Duration Analysis
    print("\n" + "=" * 80)
    print("DAUER-ANALYSE")
    print("=" * 80)
    dur_results = analyze_durations(df)
    print("\nDauer nach Code:")
    print(dur_results['by_code'].head(15))
    visualize_duration_analysis(df, save_path=f'{output_dir}/duration_analysis.png')

    # 5. Clustering
    print("\n" + "=" * 80)
    print("CLUSTERING")
    print("=" * 80)
    cluster_results = cluster_situations(df, n_clusters=3)
    if cluster_results:
        for cid, profile in cluster_results['cluster_profiles'].items():
            print(f"\nCluster {cid} (n={profile['n_situations']}):")
            print(f"  Häufige Codes: {', '.join(profile['common_codes'][:5])}")
        visualize_situation_clusters(
            cluster_results,
            save_path=f'{output_dir}/clustering.png'
        )

    # 6. Fachkraft Comparison
    print("\n" + "=" * 80)
    print("FACHKRAFT-VERGLEICH")
    print("=" * 80)
    fk_results = analyze_by_fachkraft(df)
    print("\nSituationen pro Fachkraft:")
    print(fk_results['situations_per_fk'])
    visualize_fachkraft_comparison(
        fk_results,
        save_path=f'{output_dir}/fachkraft_comparison.png'
    )

    print(f"\n{'=' * 80}")
    print(f"Report complete! All outputs saved to {output_dir}/")
    print(f"{'=' * 80}")

    return {
        'frequency': freq_results,
        'cooccurrence': cooc_results,
        'association': assoc_df,
        'duration': dur_results,
        'clustering': cluster_results,
        'fachkraft': fk_results
    }


# =============================================================================
# HAUPTAUSFÜHRUNG
# =============================================================================

if __name__ == "__main__":
    results = generate_full_report(
        "extracted_sequences.csv",
        output_dir="analysis_report"
    )