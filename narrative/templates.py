"""Deterministic, free, plain-English narrative generator for flagged nodes.

This is the always-available fallback: no network calls, no API key, no
cost. narrative/llm_narrative.py uses this whenever the optional LLM path
is unavailable or fails.
"""

METRIC_DESCRIPTIONS = {
    "completeness": "the completeness check",
    "referential_consistency": "referential consistency",
    "freshness": "the freshness check",
    "accuracy": "the accuracy check",
}


def _narrative_for_metric(node_id: str, metric: str, score: float, config: dict) -> str:
    gap_pct = round((1.0 - score) * 100, 1)

    if metric == "completeness":
        threshold_pct = round(config["completeness_threshold"] * 100)
        return (
            f"Field `{node_id}` failed the completeness check: {gap_pct}% of records "
            f"were missing a value as of the last run, against a {threshold_pct}% "
            f"completeness threshold. Any regulatory report field sourced from this "
            f"column inherits that gap until it's remediated upstream."
        )

    if metric == "referential_consistency":
        threshold_pct = round(config["referential_threshold"] * 100)
        return (
            f"Field `{node_id}` failed referential consistency: {gap_pct}% of rows had "
            f"no matching parent record, below the {threshold_pct}% threshold. This "
            f"would block a clean lineage trace from this field into the regulatory "
            f"report until the orphaned records are resolved or excluded."
        )

    if metric == "freshness":
        threshold_pct = round(config["freshness_threshold"] * 100)
        days = config["staleness_days"]
        return (
            f"Field `{node_id}` failed the freshness check: {gap_pct}% of records were "
            f"more than {days} days older than the latest activity on the same account, "
            f"below the {threshold_pct}% threshold. Stale source data of this kind can "
            f"understate current activity in the downstream report."
        )

    if metric == "accuracy":
        threshold_pct = round(config["accuracy_threshold"] * 100)
        return (
            f"Field `{node_id}` failed the accuracy check: {gap_pct}% of reported values "
            f"fell outside tolerance versus the source-system rollup, below the "
            f"{threshold_pct}% threshold. This is the kind of discrepancy that would "
            f"need to be explained or corrected before the report field is filed."
        )

    return f"Field `{node_id}` failed {METRIC_DESCRIPTIONS.get(metric, metric)} with a score of {round(score * 100, 1)}%."


def generate_template_narrative(node_id: str, node_result: dict, config: dict) -> str:
    flagged_metrics = node_result.get("flagged_metrics", [])
    if not flagged_metrics:
        return f"Field `{node_id}` has no flagged metrics."

    sentences = [
        _narrative_for_metric(node_id, metric, node_result["metrics"][metric], config)
        for metric in flagged_metrics
    ]
    return " ".join(sentences)
