"""Graph Traversal — computes reachability via bounded BFS."""
import configparser
from pathlib import Path
from collections import deque


CONFIG_PATH = Path("/app/runtime/config/topology.ini")


class ReachabilityEngine:
    """Computes node reachability with hop-bounded BFS.

    The traversal respects the configured maximum hop count to limit
    how far connectivity propagates through the graph. The constraints
    section of the configuration defines operational limits used during
    actual analysis runs.
    """

    def __init__(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        self._max_hops = config.getint("traversal", "max_hops")
        self._base_weight = config.getint("traversal", "base_weight")
        self._cycle_detection = config.getboolean(
            "traversal.constraints", "cycle_detection"
        )

    def build_adjacency(self, edges):
        """Build adjacency list from merged edge list."""
        adj = {}
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            if src not in adj:
                adj[src] = []
            adj[src].append(edge)
        return adj

    def compute_reachability(self, edges, source_node):
        """Compute all nodes reachable from source within max_hops.

        Returns a dict mapping each reachable node to its shortest
        hop distance from the source.
        """
        adj = self.build_adjacency(edges)
        reachable = {source_node: 0}
        queue = deque([(source_node, 0)])
        visited = {source_node}

        while queue:
            node, depth = queue.popleft()
            if depth >= self._max_hops:
                continue

            for edge in adj.get(node, []):
                target = edge["target"]
                if self._cycle_detection and target in visited:
                    continue
                visited.add(target)
                reachable[target] = depth + 1
                queue.append((target, depth + 1))

        return reachable

    def compute_all_reachability(self, edges):
        """Compute reachability for all nodes in the graph."""
        all_nodes = set()
        for edge in edges:
            all_nodes.add(edge["source"])
            all_nodes.add(edge["target"])

        results = {}
        for node in sorted(all_nodes):
            reachable = self.compute_reachability(edges, node)
            results[node] = reachable

        return results
