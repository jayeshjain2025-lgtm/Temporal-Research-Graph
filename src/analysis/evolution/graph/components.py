import networkx as nx


def connected_components(graph: nx.MultiDiGraph, limit: int = 20) -> list[dict]:
    simple = nx.Graph(graph)
    components = sorted(nx.connected_components(simple), key=len, reverse=True)
    return [_component_summary(simple, component) for component in components[:limit]]


def _component_summary(graph: nx.Graph, component: set[str]) -> dict:
    type_counts: dict[str, int] = {}
    labels = []
    for node in component:
        data = graph.nodes[node]
        node_type = data.get("type", "unknown")
        type_counts[node_type] = type_counts.get(node_type, 0) + 1
        if data.get("label"):
            labels.append(data["label"])
    return {
        "size": len(component),
        "node_type_counts": type_counts,
        "sample_labels": sorted(labels)[:10],
    }
