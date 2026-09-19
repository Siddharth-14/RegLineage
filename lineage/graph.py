"""Builds a networkx DiGraph from the hand-declared manifest.yaml."""

from pathlib import Path

import networkx as nx
import yaml

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.yaml"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_graph(path: Path = MANIFEST_PATH) -> nx.DiGraph:
    manifest = load_manifest(path)

    graph = nx.DiGraph()
    for node in manifest["nodes"]:
        attrs = {k: v for k, v in node.items() if k != "id"}
        graph.add_node(node["id"], **attrs)

    for source, target in manifest["edges"]:
        graph.add_edge(source, target)

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("lineage manifest describes a cyclic graph")

    return graph
