import logging

from bat.taskutils import TaskChatter
from bat.command import register_command
from spockbot.mcdata import get_item_or_block
from spockbot.plugins.base import pl_announce, PluginBase
from spockbot.plugins.tools.task import TaskFailed


logger = logging.getLogger('spockbot')


@pl_announce('InventoryCmd')
class InventoryCommandsPlugin(PluginBase):
    requires = ('TaskManager', 'Timers', 'Commands',
                'Chat', 'Craft', 'Inventory')

    def __init__(self, ploader, settings):
        super(InventoryCommandsPlugin, self).__init__(ploader, settings)
        self.commands.register_handlers(self)
        self.inv = self.inventory
        ploader.provides('InventoryCmd', self)

    @register_command('select', '1')
    def select_active_slot(self, slot_index):
        self.inv.select_active_slot(slot_index)

    @register_command('showinv')
    def log_inventory(self):
        nice_slot = lambda s: '    --    ' if s.amount <= 0 \
            else '%2ix %3i:%-2i' % (s.amount, s.item_id, s.damage)
        nice_slots = lambda slots: ' '.join(nice_slot(s) for s in slots)
        window = self.inv.window
        inv_start = window.inventory_slots[0].slot_nr
        logger.info('window: %s', nice_slots(window.window_slots))
        for line in range(3):
            i = 9 * line
            logger.info('inv: %2i %s', i + inv_start,
                        nice_slots(window.inventory_slots[i:i+9]))
        logger.info('hotbar: %s', nice_slots(window.hotbar_slots))
        logger.info('cursor: %s', nice_slot(self.inv.cursor_slot))

    @register_command('showhot')
    def show_hotbar(self):
        slot_counter = 0
        def cb():
            nonlocal slot_counter
            self.inv.select_active_slot(slot_counter % 9)
            logger.debug('%i: %s', slot_counter, self.inv.active_slot)
            slot_counter += 1
        self.timers.reg_event_timer(0.5, cb, runs=9)

    @register_command('drops', '?1?s')
    def drop_slot(self, slot=None, drop_stack='n'):
        drop_stack = 'n' not in drop_stack.lower()
        logger.debug('Dropping: %s %s', slot, drop_stack)
        self.inv.drop_slot(slot, drop_stack)

    @register_command('drop', '*')
    def drop_items(self, amount, item_id=None, meta=None, *excess_args):
        if excess_args:
            logger.warn('Too many args for drop <amount> [id/name] [meta]')

        amount = int(amount)
        try:
            item_id = int(item_id)
            meta = int(meta)
        except:  # item_id is name string or None, or meta is None
            pass

        if item_id is None and meta is None:
            item = self.inv.active_slot.item
        else:
            item = get_item_or_block(item_id, meta or 0)

        stored = self.inv.total_stored(item)
        if stored < amount:
            logger.warn('Not enough %s stored (%i/%i)'
                        % (item, stored, amount))
            return

        def drop_items_task(amount_left):
            while amount_left > 0:
                found_slot = self.inv.find_slot(item)
                if found_slot is None:
                    raise TaskFailed('No %s stored anymore' % item)

                if amount_left >= found_slot.amount:
                    amount_left -= found_slot.amount
                    yield self.inv.async.drop_slot(found_slot, drop_stack=True)
                else:
                    logger.debug('Dropping %s single', amount_left)
                    for i in range(amount_left):
                        yield self.inv.async.drop_slot(found_slot)
                        amount_left -= 1

        self.taskmanager.run_task(drop_items_task(amount),
                                    TaskChatter(chat=self.chat),
                                    name='Drop %sx %s' % (amount, item))

    @register_command('click', '*')
    def click_slots(self, *slots):
        self.taskmanager.run_task(
            self.inv.async.click_slots(*(int(nr) for nr in slots)),
            TaskChatter('Click %s' % str(slots), self.chat))

    @register_command('hold', '1?1')
    def hold_item(self, item_id, meta=None):
        self.taskmanager.run_task(
            self.inv.async.hold_item((int(item_id), meta and int(meta))),
            TaskChatter('Hold item %i:%s' % (item_id, meta), self.chat))

    @register_command('craft', '11?1')
    def craft_item(self, amount, item, meta=None):
        recipe = self.craft.craft(item, meta, amount,
                                  parent=TaskChatter('Craft', self.chat))
        if recipe:
            logger.info('[Craft][%sx %s:%s] Crafting, recipe: %s',
                        amount, item, meta, recipe.ingredients)
        else:
            logger.info('[Craft][%sx %s:%s] Not crafting, no recipe found',
                        amount, item, meta)
