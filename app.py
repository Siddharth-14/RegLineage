"""RegLineage -- a portfolio-demo data lineage and quality scorecard.

100% synthetic data. See README.md for the full disclaimer and how this
demo works.
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from pyvis.network import Network

from data.generate_synthetic_data import data_exists, generate
from lineage.graph import build_graph
from lineage.scoring import CONFIG, load_dataframes, score_graph
from narrative.llm_narrative import generate_narrative

DATA_DIR = Path(__file__).resolve().parent / "data"

GREEN = "#2ecc71"
YELLOW = "#f1c40f"
RED = "#e74c3c"
GRAY = "#95a5a6"

TYPE_SHAPES = {
    "source_field": "box",
    "transform": "ellipse",
    "report_field": "diamond",
}


def color_for_score(score: float) -> str:
    if score >= CONFIG["completeness_threshold"]:
        return GREEN
    if score >= 0.75:
        return YELLOW
    return RED


@st.cache_data(show_spinner=False)
def ensure_data() -> None:
    if not data_exists(DATA_DIR):
        generate(DATA_DIR)


@st.cache_data(show_spinner=False)
def load_scored_graph():
    graph = build_graph()
    dataframes = load_dataframes(DATA_DIR)
    results = score_graph(graph, dataframes, CONFIG)
    return graph, results


def render_lineage_graph(graph, results) -> str:
    net = Network(
        height="600px",
        width="100%",
        directed=True,
        bgcolor="#111111",
        font_color="white",
        cdn_resources="in_line",
    )
    net.set_options(
        """
        {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "LR",
              "sortMethod": "directed",
              "levelSeparation": 220,
              "nodeSpacing": 140
            }
          },
          "physics": { "enabled": false },
          "edges": { "arrows": { "to": { "enabled": true } }, "color": "#888888" },
          "interaction": { "hover": true }
        }
        """
    )

    for node_id in graph.nodes:
        result = results[node_id]
        node_type = result["type"]
        color = color_for_score(result["worst_score"])

        tooltip_lines = [f"<b>{node_id}</b>", f"type: {node_type}"]
        for metric, score in result["metrics"].items():
            flag = " (FLAGGED)" if metric in result["flagged_metrics"] else ""
            tooltip_lines.append(f"{metric}: {score:.3f}{flag}")
        if not result["metrics"]:
            tooltip_lines.append(f"inherited worst score: {result['worst_score']:.3f}")

        net.add_node(
            node_id,
            label=node_id,
            title="<br>".join(tooltip_lines),
            color=color,
            shape=TYPE_SHAPES.get(node_type, "box"),
        )

    for source, target in graph.edges:
        net.add_edge(source, target)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        html_path = f.name
    net.write_html(html_path, notebook=False, open_browser=False)
    html = Path(html_path).read_text()
    Path(html_path).unlink(missing_ok=True)
    return html


def build_scorecard_df(results: dict) -> pd.DataFrame:
    all_metric_names = ["completeness", "referential_consistency", "freshness", "accuracy"]
    rows = []
    for node_id, result in results.items():
        row = {"node": node_id, "type": result["type"]}
        for metric in all_metric_names:
            row[metric] = result["metrics"].get(metric)
        row["worst_score"] = round(result["worst_score"], 3)
        row["flagged"] = result["flagged"]
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("worst_score")
    return df


def highlight_flagged(row: pd.Series):
    if row["flagged"]:
        return ["background-color: #4a1414"] * len(row)
    return [""] * len(row)


def main():
    st.set_page_config(page_title="RegLineage", layout="wide")

    st.title("RegLineage")
    st.caption("A data lineage and quality scorecard for regulatory-reporting pipelines")

    st.warning(
        "**Synthetic data only. No connection to any real institution.** "
        "Every table, name, and figure in this demo is randomly generated with a "
        "fixed seed. This is a portfolio demo illustrating the kind of lineage and "
        "quality evidence a data governance team might produce for numbers that "
        "land in a regulatory report -- it is not built on, and does not reference, "
        "any real bank's systems or data."
    )

    ensure_data()
    graph, results = load_scored_graph()

    st.header("Lineage graph")
    st.caption(
        "Green = passes all applicable checks. Yellow = below threshold but above 75%. "
        "Red = below 75% on its worst metric. Boxes are source fields, ellipses are "
        "transforms, the diamond is the report field. Hover a node for its metrics."
    )
    graph_html = render_lineage_graph(graph, results)
    st.components.v1.html(graph_html, height=620, scrolling=True)

    st.header("Scorecard")
    scorecard_df = build_scorecard_df(results)
    styled = scorecard_df.style.apply(highlight_flagged, axis=1).format(
        {c: "{:.3f}" for c in ["completeness", "referential_consistency", "freshness", "accuracy"]},
        na_rep="--",
    )
    st.dataframe(styled, width="stretch", height=460)

    flagged_nodes = [n for n, r in results.items() if r["flagged"]]
    st.header(f"Narratives ({len(flagged_nodes)} flagged field{'s' if len(flagged_nodes) != 1 else ''})")

    if not flagged_nodes:
        st.info("No fields are currently flagged below threshold.")
    else:
        for node_id in flagged_nodes:
            result = results[node_id]
            narrative_text, source = generate_narrative(node_id, result, CONFIG)
            source_label = "Generated live by Claude" if source == "llm" else "Deterministic template (no API key set)"
            with st.expander(f"{node_id} -- {', '.join(result['flagged_metrics'])}"):
                st.write(narrative_text)
                st.caption(source_label)

    st.divider()
    st.caption(
        "Lineage in this demo is hand-declared in lineage/manifest.yaml, not "
        "auto-discovered from SQL or ETL code -- see README.md for why "
        "auto-discovery is out of scope here."
    )


if __name__ == "__main__":
    main()
