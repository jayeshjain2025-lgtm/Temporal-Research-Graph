from itertools import combinations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Authorship, Method, Paper, Topic, UsesMethod, PaperTopic


def centrality(graph: nx.MultiDiGraph, limit: int = 20) -> list[dict]:
    simple = nx.Graph(graph)
    scores = nx.degree_centrality(simple)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{"node": node, "score": score, **simple.nodes[node]} for node, score in ranked]


def connected_components(graph: nx.MultiDiGraph) -> list[list[str]]:
    simple = nx.Graph(graph)
    return [sorted(component) for component in nx.connected_components(simple)]


def communities(graph: nx.MultiDiGraph) -> list[list[str]]:
    simple = nx.Graph(graph)
    if simple.number_of_nodes() == 0:
        return []
    detected = nx.algorithms.community.greedy_modularity_communities(simple)
    return [sorted(group) for group in detected]


def researcher_collaboration_graph(session: Session) -> nx.Graph:
    graph = nx.Graph()
    paper_authors: dict[int, list[int]] = {}
    for row in session.scalars(select(Authorship)):
        paper_authors.setdefault(row.paper_id, []).append(row.researcher_id)
    for authors in paper_authors.values():
        for left, right in combinations(sorted(authors), 2):
            if graph.has_edge(left, right):
                graph[left][right]["weight"] += 1
            else:
                graph.add_edge(left, right, weight=1)
    return graph


def topic_method_graph(session: Session) -> nx.Graph:
    graph = nx.Graph()
    rows = session.execute(
        select(Topic.name, Method.name, Paper.id)
        .join(PaperTopic, PaperTopic.topic_id == Topic.id)
        .join(Paper, Paper.id == PaperTopic.paper_id)
        .join(UsesMethod, UsesMethod.paper_id == Paper.id)
        .join(Method, Method.id == UsesMethod.method_id)
    )
    for topic_name, method_name, _ in rows:
        topic_node = f"topic:{topic_name}"
        method_node = f"method:{method_name}"
        if graph.has_edge(topic_node, method_node):
            graph[topic_node][method_node]["weight"] += 1
        else:
            graph.add_edge(topic_node, method_node, weight=1)
    return graph
