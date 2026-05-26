"""Temporal Correlation — computes event correlation scores within time windows."""
import configparser
from pathlib import Path


CONFIG_PATH = Path("/app/runtime/config/cluster.ini")


class EventCorrelator:
    """Correlates events using spatial proximity and temporal windows."""

    def __init__(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        self._time_window = config.getint("correlation", "time_window_sec")
        self._proximity_radius = config.getint("correlation", "proximity_radius")
        self._min_cluster_size = config.getint("correlation", "min_cluster_size")
        self._decay_factor = config.getfloat("correlation.scoring", "decay_factor")

    def compute_window_scores(self, events, grid):
        """Compute correlation scores per time window.

        For each window, compute the average reading of events that
        fall within the same spatial neighborhood. The score for a
        window represents the mean reading intensity of correlated events
        in that window period.
        """
        if not events:
            return {}

        start_time = events[0]["timestamp"]
        end_time = events[-1]["timestamp"]

        window_scores = {}
        window_idx = 0

        current_start = start_time

        while current_start <= end_time:
            window_end = current_start + self._time_window
            window_events = [
                e for e in events
                if current_start <= e["timestamp"] < window_end
            ]

            cell_readings = {}
            for event in window_events:
                cell = grid.cell_for_point(event["x"], event["y"])
                neighbors = grid.get_neighbors(cell, self._proximity_radius)

                neighbor_in_window = [
                    n for n in neighbors
                    if current_start <= n["timestamp"] < window_end
                ]

                if len(neighbor_in_window) >= self._min_cluster_size:
                    if cell not in cell_readings:
                        cell_readings[cell] = 0.0
                    cell_readings[cell] += event["reading"]

            if cell_readings:
                total_score = sum(cell_readings.values())
                window_scores[window_idx] = round(total_score, 2)

            window_idx += 1
            current_start = window_end

        return window_scores

    def build_clusters(self, events, grid):
        """Build event clusters based on spatial and temporal proximity.

        A cluster is a group of events in the same spatial neighborhood
        that occur within the configured time window. Each cluster gets
        a correlation score based on the sum of readings from
        constituent events.
        """
        clusters = []
        processed = set()

        for i, event in enumerate(events):
            if i in processed:
                continue

            cell = grid.cell_for_point(event["x"], event["y"])
            neighbors = grid.get_neighbors(cell, self._proximity_radius)

            cluster_events = []
            for j, other in enumerate(events):
                if j in processed:
                    continue
                if other in neighbors:
                    time_diff = abs(other["timestamp"] - event["timestamp"])
                    if time_diff <= self._time_window:
                        cluster_events.append(j)

            if len(cluster_events) >= self._min_cluster_size:
                score = sum(events[idx]["reading"] for idx in cluster_events)
                decay = self._decay_factor ** (len(cluster_events) - self._min_cluster_size)
                adjusted_score = round(score * decay, 2)

                cluster = {
                    "anchor_zone": event["zone_id"],
                    "anchor_timestamp": event["timestamp"],
                    "cell": list(cell),
                    "event_count": len(cluster_events),
                    "raw_score": round(score, 2),
                    "adjusted_score": adjusted_score,
                }
                clusters.append(cluster)
                processed.update(cluster_events)

        return clusters
