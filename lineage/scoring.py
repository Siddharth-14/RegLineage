"""Computes per-node data quality metrics against the synthetic CSVs.

Thresholds are collected here, in one place, instead of being scattered as
magic numbers through the scoring logic, so they're visibly configurable.
"""

from pathlib import Path

import networkx as nx
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIG = {
    "completeness_threshold": 0.90,
    "freshness_threshold": 0.90,
    "referential_threshold": 0.90,
    "accuracy_threshold": 0.90,
    "staleness_days": 30,
    "accuracy_tolerance_pct": 0.02,   # 2% relative tolerance
    "accuracy_tolerance_abs": 25.0,   # or $25 absolute, whichever is larger
}

THRESHOLD_KEY_FOR_METRIC = {
    "completeness": "completeness_threshold",
    "freshness": "freshness_threshold",
    "referential_consistency": "referential_threshold",
    "accuracy": "accuracy_threshold",
}

# Which checks apply to which node, and (for FK checks) what parent
# table/column they must resolve against. Declared explicitly rather than
# inferred, in keeping with this tool's "lineage is declared, not
# discovered" philosophy.
NODE_CHECKS = {
    "customers.customer_id": {"checks": ["completeness"]},
    "customers.kyc_status": {"checks": ["completeness"]},
    "accounts.account_id": {"checks": ["completeness"]},
    "accounts.customer_id": {
        "checks": ["completeness", "referential_consistency"],
        "parent_table": "customers",
        "parent_column": "customer_id",
    },
    "transactions.account_id": {
        "checks": ["completeness", "referential_consistency"],
        "parent_table": "accounts",
        "parent_column": "account_id",
    },
    "transactions.amount": {"checks": ["completeness"]},
    "transactions.txn_date": {"checks": ["completeness", "freshness"]},
    "reg_report_extract.reported_value": {"checks": ["accuracy"]},
}


def load_dataframes(data_dir: Path = DATA_DIR) -> dict:
    data_dir = Path(data_dir)
    return {
        "customers": pd.read_csv(data_dir / "customers.csv"),
        "accounts": pd.read_csv(data_dir / "accounts.csv"),
        "transactions": pd.read_csv(data_dir / "transactions.csv"),
        "reg_report_extract": pd.read_csv(data_dir / "reg_report_extract.csv"),
    }


def _completeness(df: pd.DataFrame, column: str) -> float:
    if len(df) == 0:
        return 1.0
    return 1.0 - df[column].isna().mean()


def _referential_consistency(
    child_df: pd.DataFrame, child_col: str, parent_df: pd.DataFrame, parent_col: str
) -> float:
    if len(child_df) == 0:
        return 1.0
    parent_values = set(parent_df[parent_col].dropna())
    matched = child_df[child_col].apply(lambda v: pd.notna(v) and v in parent_values)
    return float(matched.mean())


def _freshness(df: pd.DataFrame, date_col: str, group_col: str, staleness_days: int) -> float:
    if len(df) == 0:
        return 1.0
    working = df.copy()
    working[date_col] = pd.to_datetime(working[date_col])
    group_max = working.groupby(group_col)[date_col].transform("max")
    stale = (group_max - working[date_col]).dt.days > staleness_days
    return 1.0 - float(stale.mean())


def _accuracy(
    report_df: pd.DataFrame,
    transactions_df: pd.DataFrame,
    tolerance_pct: float,
    tolerance_abs: float,
) -> float:
    if len(report_df) == 0:
        return 1.0
    rollup = transactions_df.groupby("account_id")["amount"].sum()

    def in_tolerance(row) -> bool:
        source_total = float(rollup.get(row["source_account_id"], 0.0))
        tolerance = max(tolerance_abs, tolerance_pct * abs(source_total))
        return abs(row["reported_value"] - source_total) <= tolerance

    matches = report_df.apply(in_tolerance, axis=1)
    return float(matches.mean())


def _compute_node_metrics(node_id: str, dataframes: dict, config: dict) -> dict:
    table, _, column = node_id.partition(".")
    spec = NODE_CHECKS[node_id]
    df = dataframes[table]
    metrics = {}

    for check in spec["checks"]:
        if check == "completeness":
            metrics["completeness"] = _completeness(df, column)
        elif check == "referential_consistency":
            parent_df = dataframes[spec["parent_table"]]
            metrics["referential_consistency"] = _referential_consistency(
                df, column, parent_df, spec["parent_column"]
            )
        elif check == "freshness":
            metrics["freshness"] = _freshness(
                df, column, "account_id", config["staleness_days"]
            )
        elif check == "accuracy":
            metrics["accuracy"] = _accuracy(
                df,
                dataframes["transactions"],
                config["accuracy_tolerance_pct"],
                config["accuracy_tolerance_abs"],
            )

    return metrics


def score_graph(graph: nx.DiGraph, dataframes: dict, config: dict = CONFIG) -> dict:
    """Scores every node in the graph.

    Source/report fields get their own directly-measured metrics. Transform
    nodes have no metric of their own; they inherit the worst score seen
    anywhere upstream, since a transform can't be healthier than the data
    it consumes. Report fields likewise take the min of their own accuracy
    score and whatever their upstream transforms inherited, so a graph-wide
    issue is visible all the way down the lineage path.
    """
    results = {}

    for node_id in nx.topological_sort(graph):
        node_type = graph.nodes[node_id].get("type")

        own_metrics = {}
        if node_id in NODE_CHECKS:
            own_metrics = _compute_node_metrics(node_id, dataframes, config)

        flagged_metrics = [
            metric
            for metric, score in own_metrics.items()
            if score < config[THRESHOLD_KEY_FOR_METRIC[metric]]
        ]

        candidate_scores = list(own_metrics.values())
        inherited_issue = False
        for pred in graph.predecessors(node_id):
            pred_result = results[pred]
            candidate_scores.append(pred_result["worst_score"])
            if pred_result["worst_score"] < min(config[k] for k in THRESHOLD_KEY_FOR_METRIC.values()):
                inherited_issue = True

        worst_score = min(candidate_scores) if candidate_scores else 1.0
        worst_metric = None
        if own_metrics:
            worst_metric = min(own_metrics, key=own_metrics.get)

        results[node_id] = {
            "type": node_type,
            "metrics": own_metrics,
            "flagged_metrics": flagged_metrics,
            "flagged": len(flagged_metrics) > 0,
            "worst_score": worst_score,
            "worst_metric": worst_metric,
            "inherited_issue": inherited_issue and not flagged_metrics,
        }

    return results
