import logging
import traceback

from spockbot.mcdata.windows import Slot
from spockbot.plugins.base import PluginBase
from spockbot.plugins.tools.task import TaskFailed
from spockbot.vector import Vector3 as Vec
from bat.command import register_command

logger = logging.getLogger('spockbot')

reach_dist_sq = 4 * 4


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

    @register_command('dig', '3')
    def dig_block(self, pos):
        self.interact.dig_block(Vec(*pos).ifloor())

    @register_command('place', '3')
    def place_block(self, pos):
        self.interact.place_block(Vec(*pos).ifloor())

    @register_command('open', '3')
    def open_block(self, pos):
        self.interact.click_block(Vec(*pos).ifloor())

    @register_command('ent', '?3')
    def interact_entity(self, pos=None):
        if pos is None:
            pos = self.clinfo.eye_pos
        target_dist = Vec(*pos).dist_sq

        nearest_dist = float('inf')
        nearest_ent = None
        for current_entity in self.entities.entities.values():
            # TODO check if entity can be interacted with
            try:
                current_pos = Vec(current_entity)
            except AttributeError:  # has no position
                continue

            if self.clinfo.eye_pos.dist_sq(current_pos) > reach_dist_sq:
                continue

            current_dist = target_dist(current_pos)
            if nearest_dist > current_dist:
                nearest_dist = current_dist
                nearest_ent = current_entity

        if nearest_ent:
            self.interact.use_entity(nearest_ent)
            logger.debug('Clicked entity %s at %s',
                         nearest_ent.__class__.__name__, Vec(nearest_ent))
        else:
            logger.warn('No entity near %s', pos)

    @register_command('openinv')
    def open_inventory(self):
        self.interact.open_inventory()

    @register_command('sneak', '?1')
    def sneak(self, on=1):
        self.interact.sneak(bool(on))

    @register_command('action', '1')
    def entity_action(self, nr):
        self.interact._entity_action(nr)

    @register_command('use')
    def activate_item(self):
        self.interact.activate_item()

    @register_command('unuse')
    def deactivate_item(self):
        self.interact.deactivate_item()

    @register_command('clone', '333')
    def clone_area(self, c_from, c_to, c_target):
        logger.warn('TODO')
