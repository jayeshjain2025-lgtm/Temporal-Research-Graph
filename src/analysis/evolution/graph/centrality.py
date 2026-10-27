import networkx as nx


def degree_centrality(graph: nx.MultiDiGraph, limit: int = 20, node_types: set[str] | None = None) -> list[dict]:
    simple = nx.Graph(graph)
    scores = nx.degree_centrality(simple)
    return _rank_scores(simple, scores, limit, node_types)


def betweenness_centrality(graph: nx.MultiDiGraph, limit: int = 20, node_types: set[str] | None = None) -> list[dict]:
    simple = nx.Graph(graph)
    scores = nx.betweenness_centrality(simple) if simple.number_of_nodes() else {}
    return _rank_scores(simple, scores, limit, node_types)


def central_entities_by_type(graph: nx.MultiDiGraph, limit_per_type: int = 10) -> dict[str, list[dict]]:
    types = {"researcher", "topic", "method", "dataset"}
    return {
        node_type: degree_centrality(graph, limit=limit_per_type, node_types={node_type})
        for node_type in sorted(types)
    }


def _rank_scores(graph: nx.Graph, scores: dict[str, float], limit: int, node_types: set[str] | None) -> list[dict]:
    items = []
    for node, score in scores.items():
        data = graph.nodes[node]
        if node_types and data.get("type") not in node_types:
            continue
        items.append(
            {
                "node": node,
                "label": data.get("label"),
                "type": data.get("type"),
                "score": score,
            }
        )
    return sorted(items, key=lambda item: item["score"], reverse=True)[:limit]
