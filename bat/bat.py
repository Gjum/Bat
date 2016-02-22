import logging
import traceback

from spockbot.mcdata.windows import Slot
from spockbot.plugins.base import PluginBase
from spockbot.plugins.tools.task import TaskFailed
from spockbot.vector import Vector3 as Vec
from bat.command import register_command

logger = logging.getLogger('spockbot')


class TaskEnder(object):
    def __init__(self, name):
        self.name = name

    def on_success(self, data):
        logger.info('Task "%s" finished successfully: %s', self.name, data)

    def on_error(self, error):
        logger.warn('Task "%s" failed: %s', self.name, error.args)


class TaskChatter(object):
    def __init__(self, name=None, chat=None):
        self.name = name
        self.chat = chat
        self.last_child = None  # set by TaskManager

    def on_success(self, data):
        if not self.name:
            self.name = self.last_child.name
        if data:
            data = ': %s' % str(data)
        else:
            data = ''
        msg = 'Task "%s" finished successfully%s' % (self.name, data)
        if self.chat:
            self.chat.chat(msg)
        logger.info(msg)

    def on_error(self, error):
        if not self.name:
            self.name = self.last_child.name
        if self.chat:
            self.chat.chat('Task "%s" failed: %s' % (self.name, error))

        if isinstance(error, TaskFailed):
            trace = str(error)
        else:
            trace = traceback.format_exc().strip()
        logger.warn('Task "%s" failed: %s', self.name, trace)


def slot_from_item(item):
    if 2 != getattr(item, 'obj_type', None):
        return None
    meta = getattr(item, 'metadata', None)
    if meta and 10 in meta:  # has its "slot" value set
        typ, slot_data = meta[10]
        if typ == 5:
            return Slot(None, -1, **slot_data)
    return None


# noinspection PyUnresolvedReferences
class BatPlugin(PluginBase):
    requires = ('Event', 'Net', 'TaskManager', 'Timers',
                'Chat', 'ClientInfo', 'Entities', 'Interact', 'World',
                'Craft', 'Commands', 'Inventory')
    events = {
        'chat': 'log_chat',
        'inventory_open_window': 'log_inventory',
        'inventory_click_response': 'log_inventory',  # xxx log clicked slot
    }
    # logged events TODO remove
    events.update({e: 'debug_event' for e in (
        'LOGIN<Login Success',
        'PLAY<Sign Editor Open',  # xxx sign placement and writing
        # TODO find out what /clear does, also when a win is open
        'PLAY<Window Property', 'inventory_win_prop', 'inventory_close_window',
    )})

    def __init__(self, ploader, settings):
        # self.capture_args(locals())
        super(BatPlugin, self).__init__(ploader, settings)

        self.clinfo = self.clientinfo
        self.commands.register_handlers(self)


    def debug_event(self, evt, data):
        data = getattr(data, 'data', data)
        logger.debug('%s: %s', evt, data)

    def log_chat(self, evt, data):
        text = data.get('text', '[Chat] <%s via %s> %s' %
                        (data['name'], data['type'], data['message']))
        logger.info('[Chat] %s', text)

    def log_inventory(self, *_):
        self.inventorycmd.log_inventory()

    def find_dropped_items(self, wanted=None, near=None):
        """
        If ``near`` is a Vector3, the items are sorted by distance to ``near``.
        """
        items = []
        for item in self.entities.objects:
            slot = self.slot_from_item(item)
            if not slot:
                continue
            if near:
                items.append((item, slot))
            else:
                yield (item, slot)
        if near:  # not yielded yet, sort by distance
            dist = near.dist_sq
            for d, item, slot in sorted((dist(Vec(i)), i, s) for i, s in items):
                yield (item, slot)

    @register_command('say', '*')
    def chat_say(self, *msgs):
        self.chat.chat(' '.join(msgs))

    @register_command('clone', '333')
    def clone_area(self, c_from, c_to, c_target):
        logger.warn('TODO')
