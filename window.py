from info import item_dict, block_dict, window_dict, enchant_dict

class Slot:
    def __init__(self, item_id=-1, count=0, damage=0, enchants={}):
        # ID == -1 means empty
        self.item_id = item_id
        self.count = count
        self.damage = damage
        # dict of ench_id -> ench_level
        self.enchants = enchants


class Window:
    def __init__(self, window_id, window_type, window_title, num_slots, horse_entity_id=None):
        self.window_id = window_id
        self.window_type = window_type
        self.window_title = window_title
        self.horse_entity_id = horse_entity_id
        self.slots = [Slot()] * num_slots


class WindowHandler:
    """ Handles all open windows and their slots """

    def __init__(self):
        # dict of window_id -> slots of that window
        # 0 is always player inventory, which has 45 unique slots
        self.windows = { 0: Window(0, -1, "", 45) }

    def open_window(self, window_id, window_type, window_title, num_slots, horse_entity_id=None):
        self.windows[window_id] = Window(window_id, window_type, window_title, num_slots)

    def close_window(self, window_id):
        self.windows.pop(window_id)

    def set_slot(self, window_id, slot_nr, item_id, count, damage=0, enchants={}):
        self.windows[window_id].slots[slot_nr] = Slot(item_id, count, damage, enchants)
        slot_content_type = 'item' if item_id in item_dict else 'block'
        info = item_dict[item_id] if item_id in item_dict else block_dict[item_id]
        name = info['name']
        window_name = window_dict[self.windows[window_id].window_type]['name']
        ench_str = 'not enchanted'
        if len(enchants) > 0:
            ench_str = 'enchanted with ' + ', '.join(map(lambda (e_id, lvl): '%s %d' % (enchant_dict[e_id]['name'], lvl), enchants.items()))
        print window_name, '- got', count, name, slot_content_type, 'into slot', slot_nr, ench_str

    def clear_slot(self, window_id, slot_nr):
        if slot_nr < 0: # Notchian server apparently sends these on clearing (part of) the inventory
            return
        self.windows[window_id].slots[slot_nr] = Slot()
        window_name = window_dict[self.windows[window_id].window_type]['name']
        print window_name, '- cleared slot', slot_nr

