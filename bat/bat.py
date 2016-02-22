import importlib
import logging
import sys
import traceback
import types

from spockbot.mcdata import get_item_or_block
from spockbot.mcdata.windows import Slot
from spockbot.plugins.base import PluginBase
from spockbot.plugins.tools.task import TaskFailed
from spockbot.vector import Vector3 as Vec
from bat.command import register_command

logger = logging.getLogger('spockbot')

reach_dist_sq = 4 * 4


class Reloadable(object):
    """Makes inheriting class instances reloadable."""

    _persistent_attributes = []  # will be kept when reloading

    def capture_args(self, init_args):
        """
        Capture original args for calling init on reload.
        An ancestor should call this in their init with locals() as argument
        before creating any more local variables:

        >>> class Foo(Reloadable):
        >>>     def __init__(self, foo, bar=123):
        >>>         super(self.__class__, self).__init__()
        >>>         self.foo = foo * bar  # just uses `self`, thus not creating a local var
        >>>         self.capture_args(locals())  # captures self, foo, bar
        >>>         tmp = bar ** 2  # creates local var `tmp`
        >>>         # ...
        """
        self._init_args = dict(init_args)
        for k in list(self._init_args.keys()):
            if k == 'self' or k[:2] == '__':
                del self._init_args[k]

    def reload(self, new_module=None):
        """
        Reloads the containing module and replaces all instance attributes
        while keeping the attributes in _persistent_attributes.
        This is called monkey-patching, see
        https://filippo.io/instance-monkey-patching-in-python/
        """
        if not new_module:
            new_module = importlib.reload(sys.modules[self.__module__])
        new_class = getattr(new_module, self.__class__.__name__)
        persistent = {attr_name: getattr(self, attr_name, None)
                      for attr_name in self._persistent_attributes}
        for new_attr_name in dir(new_class):
            if new_attr_name in ('__class__', '__dict__', '__weakref__'):
                # do not copy '__dict__', '__weakref__'
                # but copy '__class__' below
                continue
            new_attr = getattr(new_class, new_attr_name)
            try:  # some attributes are instance methods, bind them to `self`
                new_attr = types.MethodType(new_attr, self)
            except TypeError:
                pass
            setattr(self, new_attr_name, new_attr)
        setattr(self, '__class__', new_class)
        new_class.__init__(self, **getattr(self, '_init_args', {}))
        for k, v in persistent.items():
            setattr(self, k, v)

    def try_reload(self):
        """
        Try to reload the containing module.
        If an exception is thrown in the process, catch and return it.
        Useful to catch syntax errors.

        :return the thrown exception if not successfully reloaded, None otherwise
        """
        try:
            self.reload()
        except Exception as e:
            return e


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
class BatPlugin(PluginBase):#, Reloadable):
    _persistent_attributes = ('path_queue', 'event')

    requires = ('Event', 'Net', 'TaskManager', 'Timers',
                'Chat', 'ClientInfo', 'Entities', 'Interact', 'World',
                'Craft', 'Commands', 'Inventory')
    events = {
        'chat': 'handle_chat',
        'inventory_open_window': 'show_inventory',
        'inventory_click_response': 'show_inventory',  # xxx log clicked slot
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
        self.inv = self.inventory
        self.commands.register_handlers(self)


    def debug_event(self, evt, data):
        data = getattr(data, 'data', data)
        logger.debug('%s: %s', evt, data)

    def handle_chat(self, evt, data):
        text = data.get('text', '[Chat] <%s via %s> %s' %
                        (data['name'], data['type'], data['message']))
        logger.info('[Chat] %s', text)

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

    @register_command('reload')
    def reload_now(self):  # xxx broken do not use

        def unregister_handlers():
            try:
                for event, handler_name in self.events.items():
                    handler = getattr(self, handler_name)
                    if handler in self.event.event_handlers[event]:
                        self.event.event_handlers[event].remove(handler)
            except AttributeError:
                pass

        def do_the_reload():
            unregister_handlers()
            # setattr(self, 'reloaded', True)
            e = self.try_reload()
            if e is None:
                unregister_handlers()
                logger.debug('[Bat] reloaded')
            else:
                logger.debug('[Bat] not reloaded: %s', e)

        def wait(time):
            cb = lambda *_: self.event.emit('sleep_over', {})
            self.timers.reg_event_timer(time, cb, runs=1)
            return 'sleep_over'

        def task():
            logger.debug('before reload 123')
            do_the_reload()
            yield wait(1)
            logger.debug('after reload 234')

        self.taskmanager.run_task(task(), TaskChatter('Reloader', self.chat))

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

    @register_command('select', '1')
    def select_active_slot(self, slot_index):
        self.inv.select_active_slot(slot_index)

    @register_command('showinv')
    def show_inventory(self, *args):
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

    @register_command('use')
    def activate_item(self):
        self.interact.activate_item()

    @register_command('unuse')
    def deactivate_item(self):
        self.interact.deactivate_item()

    @register_command('hold', '1?1')
    def hold_item(self, item_id, meta=None):
        self.taskmanager.run_task(
            self.inv.async.hold_item((int(item_id), meta and int(meta))),
            TaskChatter('Hold item %i:%s' % (item_id, meta), self.chat))

    @register_command('clone', '333')
    def clone_area(self, c_from, c_to, c_target):
        logger.warn('TODO')

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
