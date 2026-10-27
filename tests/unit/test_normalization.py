from src.normalization.text import normalize_text


def test_normalizes_case_plural_and_punctuation():
    assert normalize_text("Graph Neural Networks") == normalize_text("graph neural network")
    assert normalize_text("Temporal-Knowledge   Graphs!") == "temporal knowledge graph"
