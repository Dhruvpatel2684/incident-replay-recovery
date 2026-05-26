"""Spatial Grid Index — assigns events to grid cells for proximity queries."""


class SpatialGrid:
    """Grid-based spatial index for fast neighbor lookups."""

    def __init__(self, cell_size, origin_x=0.0, origin_y=0.0):
        self._cell_size = cell_size
        self._origin_x = origin_x
        self._origin_y = origin_y
        self._cells = {}

    def cell_for_point(self, x, y):
        """Compute the grid cell coordinates for a given point.

        Cells are numbered from the origin. The cell coordinate is
        determined by dividing the offset from origin by cell size
        and taking the integer part.
        """
        cx = int((x - self._origin_x) / self._cell_size)
        cy = int((y - self._origin_y) / self._cell_size)
        return (cx, cy)

    def insert(self, event):
        """Insert an event into the spatial grid."""
        cell = self.cell_for_point(event["x"], event["y"])
        if cell not in self._cells:
            self._cells[cell] = []
        self._cells[cell].append(event)
        return cell

    def get_neighbors(self, cell, radius=1):
        """Get all events in cells within radius of the given cell."""
        cx, cy = cell
        neighbors = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                neighbor_cell = (cx + dx, cy + dy)
                if neighbor_cell in self._cells:
                    neighbors.extend(self._cells[neighbor_cell])
        return neighbors

    def get_all_cells(self):
        """Return all occupied cells and their events."""
        return dict(self._cells)

    def cell_count(self):
        """Return number of occupied cells."""
        return len(self._cells)
