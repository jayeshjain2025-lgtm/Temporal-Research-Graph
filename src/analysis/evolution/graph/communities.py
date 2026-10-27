from collections import Counter

import networkx as nx


def structural_communities(graph: nx.MultiDiGraph, limit: int = 10) -> list[dict]:
    simple = nx.Graph(graph)
    if simple.number_of_nodes() == 0:
        return []
    communities = nx.algorithms.community.greedy_modularity_communities(simple)
    summaries = [_community_summary(simple, community, index + 1) for index, community in enumerate(communities)]
    return sorted(summaries, key=lambda item: item["size"], reverse=True)[:limit]


def _community_summary(graph: nx.Graph, community, index: int) -> dict:
    labels = []
    type_counts: Counter[str] = Counter()
    topic_labels = []
    method_labels = []
    for node in community:
        data = graph.nodes[node]
        label = data.get("label")
        node_type = data.get("type", "unknown")
        type_counts[node_type] += 1
        if label:
            labels.append(label)
            if node_type == "topic":
                topic_labels.append(label)
            if node_type == "method":
                method_labels.append(label)
    return {
        "community_id": index,
        "size": len(community),
        "node_type_counts": dict(type_counts),
        "structural_label": _structural_label(topic_labels, method_labels),
        "sample_labels": sorted(labels)[:12],
        "note": "Structural community detected from graph connectivity; not automatically a scientific subfield.",
    }


def _structural_label(topic_labels: list[str], method_labels: list[str]) -> str:
    parts = []
    if topic_labels:
        parts.append("Topics: " + ", ".join(sorted(topic_labels)[:3]))
    if method_labels:
        parts.append("Methods: " + ", ".join(sorted(method_labels)[:3]))
    return " | ".join(parts) if parts else "Mixed research cluster"
