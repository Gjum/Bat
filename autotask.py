
item_tasks = {}
block_tasks = {}

def map_task():
    def inner(cl):
        tasks[cl.get] = cl
        cl.block_id = block_id
        return cl
    return inner

unobtainable = -1


class Task:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.name)

    def required_for_item(self, id, meta=None):
        return [unobtainable]

    def required_for_block(self, id, meta=None):
        return [unobtainable]

    def produce_item(self, bot, id, meta=None):
        pass

    def produce_block(self, bot, id, meta=None):
        pass


class TaskDig(Task):
    def __init__(self, name):
        self.name = name

    def required_for_item(self, bot, id, meta=None):
        return False


class TaskCraft(Task):
    def __init__(self, name):
        self.name = name

    def required_for_item(self, id, meta=None):
        return False

    def produce_item(self, bot, id, meta=None):
        pass


class TaskPlace(Task):
    def __init__(self, name):
        self.name = name

    def required_for_block(self, id, meta=None):
        return False

    def produce_block(self, bot, id, meta=None):
        pass


if __name__ == '__main__':
    print 'draw a graph of all tasks'
    import pygraphviz as pgv
    g = pgv.AGraph(directed=True)
    edges = []
    for p in tasks.products:
        for c in p.consumers:
            for n in c.:
                g.add_edge(p, n)
    g = g.reverse()
    g.node_attr['shape']='box'
    g.draw('graph_tasks.png', prog='dot')

    print 'craft sticks'
    tasker = Tasker()
    tasker.acquire('stick', 5)

