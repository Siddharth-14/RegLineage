"""Optional live-LLM narrative path.

If ANTHROPIC_API_KEY is set, this sends the already-computed, already-flagged
metric data for one node to Claude and asks for a short remediation-memo
narrative. If the key isn't set, the anthropic package isn't installed, or
the call fails for any reason at all, this silently falls back to the
deterministic template narrative -- the app must never break because of
this optional path.
"""

import os

from lineage.scoring import THRESHOLD_KEY_FOR_METRIC
from narrative import templates

SYSTEM_PROMPT = (
    "You write short internal remediation-memo notes for a data governance "
    "quality scorecard. This is entirely synthetic demo data with no "
    "connection to any real institution, bank, or regulator -- never imply "
    "otherwise. Write exactly 2-3 sentences, factual and not alarmist, in "
    "plain English suitable for a data governance memo. Use only the "
    "metric values given to you; do not invent any facts, causes, or "
    "numbers beyond them. Do not name any real company, bank, or regulator."
)

LLM_MODEL = "claude-haiku-4-5-20251001"


def _build_user_prompt(node_id: str, node_result: dict, config: dict) -> str:
    metric_lines = [
        f"- {metric}: score={score:.3f} (threshold={config[THRESHOLD_KEY_FOR_METRIC[metric]]:.2f})"
        for metric, score in node_result["metrics"].items()
        if metric in node_result.get("flagged_metrics", [])
    ]
    return (
        f"Lineage field: {node_id}\n"
        f"Failed metrics:\n" + "\n".join(metric_lines) + "\n\n"
        "Write the remediation-memo narrative now."
    )


def generate_narrative(node_id: str, node_result: dict, config: dict) -> tuple:
    """Returns (narrative_text, source) where source is 'llm' or 'template'."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return templates.generate_template_narrative(node_id, node_result, config), "template"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_user_prompt(node_id, node_result, config)}
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            raise ValueError("empty response from LLM")
        return text, "llm"
    except Exception:
        return templates.generate_template_narrative(node_id, node_result, config), "template"
