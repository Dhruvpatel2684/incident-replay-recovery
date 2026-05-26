"""Path Scorer — computes weighted reachability scores."""
import configparser
from pathlib import Path


CONFIG_PATH = Path("/app/runtime/config/topology.ini")


class PathScorer:
    """Computes path scores based on edge weights and hop decay.

    For each reachable node, the score represents the quality of
    connectivity from the source. Scores are computed per BFS level
    and the final score for a node reflects only its level's
    contribution (the value at its discovered depth).
    """

    def __init__(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        self._base_weight = config.getint("traversal", "base_weight")
        self._normalize = config.getboolean(
            "traversal.constraints", "normalize_weights"
        )
        self._precision = config.getint(
            "traversal.constraints", "weight_precision"
        )

    def compute_path_scores(self, edges, reachability, source_node):
        """Compute path scores from source to each reachable node.

        For each hop level, computes the score as:
            score = base_weight * product_of_edge_weights_on_best_path

        The score at each level represents that level's contribution.
        When processing edges level by level, each level's score value
        replaces the previous (reflecting the path quality at that depth).
        """
        adj = {}
        for edge in edges:
            src = edge["source"]
            if src not in adj:
                adj[src] = []
            adj[src].append(edge)

        scores = {}
        if source_node not in reachability:
            return scores

        # Process level by level
        level_nodes = {}
        for node, depth in reachability.items():
            if node == source_node:
                continue
            if depth not in level_nodes:
                level_nodes[depth] = []
            level_nodes[depth].append(node)

        # Compute scores per level
        level_scores = {}
        running_total = 0.0
        for depth in sorted(level_nodes.keys()):
            nodes_at_level = level_nodes[depth]
            level_total = 0.0

            for node in nodes_at_level:
                best_weight = 0.0
                # Find best incoming edge from previous level
                for edge in edges:
                    if edge["target"] == node:
                        src_depth = reachability.get(edge["source"])
                        if src_depth is not None and src_depth == depth - 1:
                            if edge["weight"] > best_weight:
                                best_weight = edge["weight"]

                node_score = self._base_weight * best_weight
                if self._normalize and depth > 1:
                    # Apply hop decay normalization
                    node_score = node_score / depth

                scores[node] = round(node_score, self._precision)
                level_total += node_score

            running_total += level_total
            level_scores[depth] = round(running_total, self._precision)

        return scores, level_scores
