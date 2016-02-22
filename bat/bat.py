import logging

from bat.command import register_command
from spockbot.mcdata.windows import Slot
from spockbot.plugins.base import PluginBase
from spockbot.vector import Vector3 as Vec


logger = logging.getLogger('spockbot')


# TODO move
def slot_from_item(item):
    if 2 != getattr(item, 'obj_type', None):
        return None
    meta = getattr(item, 'metadata', None)
    if meta and 10 in meta:  # has its "slot" value set
        typ, slot_data = meta[10]
        if typ == 5:
            return Slot(None, -1, **slot_data)
    return None


class BatPlugin(PluginBase):
    requires = ('Chat', 'Entities', 'Commands', 'InventoryCmd')
    events = {
        'chat': 'log_chat',
        'inventory_open_window': 'log_inventory',
        'inventory_click_response': 'log_inventory',  # xxx log clicked slot
    }

    def __init__(self, ploader, settings):
        super(BatPlugin, self).__init__(ploader, settings)
        self.commands.register_handlers(self)

    @register_command('say', '*')
    def chat_say(self, *msgs):
        self.chat.chat(' '.join(msgs))

    def log_chat(self, evt, data):
        text = data.get('text', '[Chat] <%s via %s> %s' %
                        (data['name'], data['type'], data['message']))
        logger.info('[Chat] %s', text)

    def log_inventory(self, *_):
        self.inventorycmd.log_inventory()

    # WIP
    def find_dropped_items(self, wanted=None, near=None):
        """
        If ``near`` is a Vector3, the items are sorted by distance to ``near``.
        """
        items = []
        for item in self.entities.objects:
            slot = slot_from_item(item)
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
