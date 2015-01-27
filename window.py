from info import item_or_block, item_dict, window_dict, enchant_dict

class Slot:
    def __init__(self, item_id=-1, count=0, damage=0, enchants={}):
        # ID == -1 means empty
        self.item_id = item_id
        self.count = count
        self.damage = damage
        # dict of ench_id -> ench_level
        self.enchants = enchants

    def __str__(self):
        if self.item_id < 0:
            return 'empty slot'
        slot_content_type = 'item' if self.item_id in item_dict else 'block'
        info = item_or_block(self.item_id)
        name = info['name']
        damage_str = 'not damaged' if self.damage == 0 else 'damage: %i' % self.damage
        ench_str = 'not enchanted'
        if len(self.enchants) > 0:
            # { ench_id: level, ench_id: level, ... } -> "enchanted with Sharpness 3, Silk Touch 1"
            ench_str = 'enchanted with ' + ', '.join(map(lambda (ench, lvl): '%s %d' % (enchant_dict[ench]['name'], lvl), self.enchants.items()))
        return 'slot with %2i %s (%s) %s, %s' % (self.count, name, slot_content_type, damage_str, ench_str)


class Window:
    def __init__(self, window_id, window_type, window_title, num_slots, horse_entity_id=None):
        self.window_id = window_id
        self.window_type = window_type
        self.window_title = window_title
        self.horse_entity_id = horse_entity_id
        self.slots = [Slot()] * num_slots

    def set_slot(self, slot_nr, item_id=-1, count=0, damage=0, enchants={}):
        self.slots[slot_nr] = Slot(item_id, count, damage, enchants)
        window_name = window_dict[self.window_type]['name'] # TODO use window_title
        print window_name, '- set slot nr', slot_nr, 'to', self.slots[slot_nr]


class WindowHandler(dict):
    """Handles all open windows and their slots
    Instance is a dict of window ID -> Window instance"""

    def __init__(self, **kwargs):
        super(WindowHandler, self).__init__(**kwargs)
        self.action_id_counter = 0
        # 0 is always player inventory, which has 45 unique slots
        self[0] = Window(0, -1, "Inventory", 45)

    def open_window(self, window_id, window_type, window_title, num_slots, horse_entity_id=None):
        self[window_id] = Window(window_id, window_type, window_title, num_slots)

    def close_window(self, window_id):
        if window_id not in self:
            print '[WindowHandler] Could not close', window_id
            return
        del self[window_id]

    def get_hotbar(self):
        return self[0].slots[-9:]

    def next_action_id(self):
        self.action_id_counter += 1
        return self.action_id_counter

