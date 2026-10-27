"""Export a NetworkX graph to GEXF for viewing in Gephi."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys

import networkx as nx
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.session import session_scope
from src.graph.build import build_graph
from src.models import Corpus, PaperCorpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the research graph as a Gephi-compatible GEXF file")
    parser.add_argument("--corpus", help="Export only nodes connected to papers in this corpus")
    parser.add_argument("--output", default="data/research_graph.gexf")
    parser.add_argument(
        "--node-types",
        default="paper,topic,method,dataset",
        help="Comma-separated node types to visualize (default: paper,topic,method,dataset)",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=100,
        help="Maximum connected papers to include; use 0 for all papers (default: 100)",
    )
    args = parser.parse_args()
    if args.max_papers < 0:
        parser.error("--max-papers must be zero or a positive integer")
    node_types = {value.strip() for value in args.node_types.split(",") if value.strip()}
    if "paper" not in node_types:
        parser.error("--node-types must include paper")

    with session_scope() as session:
        graph = build_graph(session)
        paper_nodes: set[str] | None = None
        if args.corpus:
            corpus = session.scalar(select(Corpus).where(Corpus.name == args.corpus))
            if corpus is None:
                raise SystemExit(f"Corpus not found: {args.corpus}")
            paper_ids = set(
                session.scalars(
                    select(PaperCorpus.paper_id).where(PaperCorpus.corpus_id == corpus.id)
                ).all()
            )
            paper_nodes = {f"paper:{paper_id}" for paper_id in paper_ids}

        allowed_nodes = {
            node
            for node, attrs in graph.nodes(data=True)
            if attrs.get("type") in node_types
            and (attrs.get("type") != "paper" or paper_nodes is None or node in paper_nodes)
        }
        filtered_graph = graph.subgraph(allowed_nodes)
        paper_nodes = {node for node in filtered_graph if filtered_graph.nodes[node].get("type") == "paper"}
        if args.max_papers and len(paper_nodes) > args.max_papers:
            ranked_papers = sorted(
                paper_nodes,
                key=lambda node: (-filtered_graph.degree(node), node),
            )
            paper_nodes = set(ranked_papers[: args.max_papers])

        included_nodes = set(paper_nodes)
        for paper_node in paper_nodes:
            included_nodes.update(
                neighbor
                for neighbor in filtered_graph.neighbors(paper_node)
                if filtered_graph.nodes[neighbor].get("type") != "paper"
            )
        graph = filtered_graph.subgraph(included_nodes).copy()

    _make_gexf_compatible(graph)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(graph, output)
    print(f"Exported {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges to {output}")


def _make_gexf_compatible(graph: nx.MultiDiGraph) -> None:
    for _, attrs in graph.nodes(data=True):
        _clean_attrs(attrs)
    for _, _, attrs in graph.edges(data=True):
        _clean_attrs(attrs)


def _clean_attrs(attrs: dict) -> None:
    for key, value in list(attrs.items()):
        if value is None:
            del attrs[key]
        elif isinstance(value, (date, datetime)):
            attrs[key] = value.isoformat()
        elif not isinstance(value, (str, int, float, bool)):
            attrs[key] = str(value)


if __name__ == "__main__":
    main()
