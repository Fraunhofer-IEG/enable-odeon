import networkx as nx


def get_nodes_with_degree(graph: nx.Graph, degree: int = 1):
    return [n for (n, d) in graph.degree() if d == degree]
