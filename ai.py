"""
This file provides useful functions to interacht with the world.
"""

class AStarNode:
    def __init__(self, coords, parent, finish_coords):
        self.coords = coords
        self.parent = parent
        if parent is None:
            if coords == finish_coords:
                self.prev_dist = float('inf') # finish
            else:
                self.prev_dist = 0 # start
        else:
            self.prev_dist = parent.prev_dist + 1
        # rectangular distance to finish
        self.estim_dist = sum([abs(coords[i] - finish_coords[i]) for i in range(len(coords))])

    def __repr__(self):
        if self.parent is None:
            return 'Source%s' % str(self.coords)
        return 'Node(c=%s p=%s pd=%f ed=%f td=%f)' % (self.coords, (self.parent.coords if self.parent is not None else 'None'), self.prev_dist, self.estim_dist, self.prev_dist + self.estim_dist)

    def c_add(self, *coords):
        """ Returns the vector sum of coords and self.coords. """
        assert len(coords) == len(self.coords)
        return tuple([coords[i] + self.coords[i] for i in range(len(coords))])

    def is_valid(self, world):
        """ Should the node be checked later? """
        # Can the bot walk here?
        get = lambda c: world.get(c[0], c[1], c[2], 'block_data')
        if get(self.c_add(0, -1, 0)) == 0: return False
        if get(self.c_add(0,  0, 0)) != 0: return False
        if get(self.c_add(0,  1, 0)) != 0: return False
        # TODO 3 blocks to stand in when jumping
        return True

    def is_unvisited(self, n_visited):
        """ Should the node be checked later? """
        for node in n_visited:
            if self.coords == node.coords:
                # this node must be worse than the old one,
                # because main loop checks node with shortest path first
                return False
        return True

    def try_add_neighbors(self, world, n_visited, n_open, finish_coords):
        """ Tries to add all adjacent blocks. """
        for y in range(-1, 1): # TODO add larger numbers for dropping from low heights
            for x, z in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                new_node = AStarNode(self.c_add(x, y, z), self, finish_coords)
                if new_node.is_valid(world) and new_node.is_unvisited(n_visited):
                    for node in n_open:
                        if new_node.coords == node.coords:
                            # node exists, do not create new one
                            if new_node.prev_dist < node.prev_dist:
                                # this node is better, replace old one
                                node.prev_dist = new_node.prev_dist
                                node.parent = new_node.parent
                                # coords and estim_dist are the same
                            break
                    else: # this node is not already being checked
                        n_open.append(new_node)

    def better_than(self, other):
        """ Returns True if this node has the smallest total distance when travelling via it. """
        if self.prev_dist + self.estim_dist == other.prev_dist + other.estim_dist:
            return self.prev_dist < other.prev_dist # better in foresight, usually estimation is too low
        return self.prev_dist + self.estim_dist < other.prev_dist + other.estim_dist

def astar(c_from, c_to, world):
    """ Finds a shortest path between two coordinates in a world.
    If there is a path, returns a list of all coordinates that lie on the path.
    Otherwise, returns an empty list."""
    # swap from/to for backtrace at the end, see below
    start_coords, finish_coords = map(tuple, (map(int, c_to), map(int, c_from)))
    start = AStarNode(start_coords, None, finish_coords)
    finish = AStarNode(finish_coords, None, finish_coords)
    n_open = [start]
    n_visited = []

    while True:
        # find node with shortest path
        best_i = len(n_open)-1
        best_n = n_open[-1]
        for i, iter_n in enumerate(n_open[:-1]):
            if iter_n.better_than(best_n):
                best_i = i
                best_n = iter_n
        node = n_open.pop(best_i)
        n_visited.append(node)
        # Are we done?
        if node.coords == finish.coords:
            break
        # not done, check neighbors
        node.try_add_neighbors(world, n_visited, n_open, finish_coords)
        if len(n_open) <= 0:
            # no path found, all accessible nodes checked
            return []

    path = []
    # build path by backtracing from finish to start, i.e. from -> to
    path.append(node.coords)
    while node.parent is not None: # TODO test for zero-length paths (from == to)
        node = node.parent
        path.append(node.coords)
    return path


if __name__ == '__main__':
    class WorldTest:
        def get(self, x, y, z, what):
            if x == 0 and y == 0:
                return 1
            return 0
    world = WorldTest()
    print astar((0, 1, 0), (0, 1, 2), world)
