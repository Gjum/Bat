import importlib
import logging
import pprint
import random
import sys
import types

from spockbot.mcdata import blocks, constants
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
    def __init__(self, name, chat=None):
        self.name = name
        self.chat = chat

    def on_success(self, data):
        if data:
            data = ': %s' % str(data)
        else:
            data = ''
        printer = self.chat.chat or logger.info
        printer('Task "%s" finished successfully%s' % (self.name, data))

    def on_error(self, error):
        printer = self.chat.chat or logger.warn
        printer('Task "%s" failed: %s' % (self.name, error.args[0]))


def slot_from_item(item):
    if 2 != getattr(item, 'obj_type', None):
        return None
    meta = getattr(item, 'metadata', None)
    if meta and 10 in meta:  # has its "slot" value set
        typ, slot_data = meta[10]
        if typ == 5:
            return Slot(None, -1, **slot_data)
    return None


def by(key, data_list):
    if len(data_list) <= 0:
        return []
    if isinstance(data_list, dict):
        data_list = list(data_list.values())
    first = data_list[0]
    if isinstance(first, dict):
        return [e[key] for e in data_list]
    if hasattr(first, key):
        return [getattr(e, key) for e in data_list]

pp = pprint.PrettyPrinter(indent=4)


# noinspection PyUnresolvedReferences
class BatPlugin(PluginBase):#, Reloadable):
    _persistent_attributes = ('path_queue', 'event')

    requires = ('Event', 'Net', 'TaskManager', 'Timers',
                'Chat', 'ClientInfo', 'Entities', 'Interact', 'World',
                'Craft', 'Commands', 'Inventory')
    events = {
        'chat': 'handle_chat',
        'event_tick': 'on_event_tick',
        'inventory_open_window': 'show_inventory',
        'inventory_click_response': 'show_inventory',  # xxx log clicked slot
        'PLAY<Entity Metadata': 'on_entity_meta',  # xxx item foo
    }
    # movement updates
    events.update({e: 'on_entity_move' for e in (
        'PLAY<Entity Relative Move',
        'PLAY<Entity Look And Relative Move',
        'PLAY<Entity Teleport',
    )})
    # logged events TODO remove
    events.update({e: 'debug_event' for e in (
        'LOGIN<Login Success',
        # TODO find out what /clear does
        'PLAY<Window Property', 'inventory_win_prop', 'inventory_close_window',
    )})

    def __init__(self, ploader, settings):
        # self.capture_args(locals())
        super(BatPlugin, self).__init__(ploader, settings)

        self.clinfo = self.clientinfo
        self.inv = self.inventory
        self.commands.register_handlers(self)
        # self.interact.auto_swing = False

        self.path_queue = deque()
        self.pos_update_counter = 0
        self.checked_entities_this_tick = False
        self.nearest_player = None
        self.aggro = False

        self.items_to_look_at = [] # xxx item type recognition

        self.taskmanager.run_task(self.eat_task())

    def eat_task(self):

        def timeout(t, other_events):
            timer_event = 'bat_timeout_%s' % random.random
            def cb(*_):
                self.event.emit(timer_event, {})

            self.timers.reg_event_timer(t, cb, runs=1)
            event, _ = yield timer_event, other_events
            if event == timer_event:
                raise TaskFailed('Timed out after %s' % t)

        while 1:
            yield 'cl_health_update'

            health = self.clientinfo.health.health
            food = self.clientinfo.health.food

            def inv_has(item):
                return self.inv.find_slot(item)

            def eat_item(item):
                yield timeout(2, self.inv.async.hold_item(364))
                self.interact.activate_item()
                yield timeout(2, 'inventory_set_slot')

            can_eat = food < 20
            cannot_regen = food <= 16
            cannot_sprint = food <= 6
            starving = food <= 0
            eat_steak = food <= 10 and inv_has(364)
            eat_chicken = food <= 14 and inv_has(366) and not inv_has(364)
            should_heal = health < 19 and cannot_regen

            if should_heal or eat_chicken or eat_steak:
                try:
                    logger.info('Eating...')
                    try:
                        yield timeout(2, self.inv.async.hold_item(364))
                    except TaskFailed:
                        yield timeout(2, self.inv.async.hold_item(366))

                    self.interact.activate_item()
                    yield timeout(2, 'inventory_set_slot')

                except TaskFailed as e:
                    logger.error('Could not eat fast enough: %s' % e.args[0])
            elif starving:
                logger.warn("I'm starving, bye!")
                self.event.kill()  # disconnect

    def debug_event(self, evt, data):
        data = getattr(data, 'data', data)
        logger.debug('%s: %s', evt, data)

    def handle_chat(self, evt, data):
        text = data.get('text', '[Chat] <%s via %s> %s' %
                        (data['name'], data['type'], data['message']))
        logger.info('[Chat] %s', text)

    def on_entity_move(self, evt, packet):
        eid = packet.data['eid']
        entity = self.entities.entities[eid]
        dist_sq = self.clinfo.position.dist_sq
        if eid in self.entities.players:
            entity_pos = Vec(entity).iadd((0, constants.PLAYER_HEIGHT, 0))
            if id(entity) == id(self.nearest_player):
                self.interact.look_at(entity_pos)
            elif self.nearest_player is None:
                self.nearest_player = entity
                self.interact.look_at(entity_pos)
            else:
                if dist_sq(entity_pos) < dist_sq(Vec(self.nearest_player)):
                    self.nearest_player = entity
                    self.interact.look_at(entity_pos)
        # force field
        if self.aggro and not self.checked_entities_this_tick:
            for entity in self.entities.mobs.values():
                if reach_dist_sq > dist_sq(Vec(entity)):
                    self.interact.attack_entity(entity)
            self.checked_entities_this_tick = True

    def on_event_tick(self, *args):
        self.checked_entities_this_tick = False

        if len(self.entities.entities) > 300:
            logger.info("Too many entities, bye!")
            self.event.kill()  # disconnect

        for item in self.items_to_look_at:
            slot = slot_from_item(item)
            pos = Vec(item)
            logger.debug('ITEM at %s %s', pos, slot)
        self.items_to_look_at.clear()

    def on_entity_meta(self, event, packet):
        eid = packet.data['eid']
        if eid in self.entities.objects:
            entity = self.entities.objects[eid]
            if entity.obj_type == 2:
                self.items_to_look_at.append(entity)

    def find_dropped_items(self, wanted=None, near=None):
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

        # TODO why not use logger.debug()?
        chat = lambda *texts: self.event.emit('chat_any', {
            'name': 'RELOADER', 'sort': 'TEST', 'text': ' '.join(texts)})

        def task():
            chat('before reload 123')
            do_the_reload()
            yield wait(1)
            chat('after reload 234')

        self.taskmanager.run_task(task(), TaskChatter('Reloader', self.chat))

    @register_command('aggro', '1')
    def set_aggro(self, val):
        self.aggro = bool(val)

    @register_command('exec', '*')
    def exec_python(self, *args):
        _results = []
        def res(val):
            _results.append(val)

        try:
            exec(' '.join(args))
        except Exception as e:
            logger.warn('[exec] Error: %s', e)

        if _results:
            if len(_results) == 1:
                _results = _results[0]
            logger.info('[exec] %s', _results)

    @register_command('eval', '*')
    def eval_python(self, *args):
        try:
            logger.info('[eval] %s', eval(' '.join(args)))
        except Exception as e:
            logger.warn('[eval] Error: %s', e)

    @register_command('tpb', '3')
    def tp_block(self, coords):
        self.teleport(Vec(.5, 0, .5).iadd(coords))

    @register_command('tpd', '3')
    def tp_delta(self, deltas):
        self.teleport(Vec(*deltas).iadd(self.clinfo.position))

    @register_command('tp', '3')
    def teleport(self, coords):
        self.clinfo.position.init(*coords)
        # self.chat.chat('/tp %i %i %i' % coords))

    @register_command('come', '?e')
    def tp_to_player(self, player=None):
        if player is None:
            logger.warn('[Come] No player to teleport to')
        else:
            self.teleport(Vec(player))

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

    @register_command('ent', '3')
    def interact_entity(self, pos):
        get_target_dist = Vec(*pos).dist_sq

        nearest_dist = float('inf')
        nearest_ent = None

        for current_entity in self.entities.entities.values():
            try:
                current_pos = Vec(current_entity)
            except AttributeError:
                logger.debug('Entity %s has no position %s',
                             current_entity.__class__.__name__,
                             current_entity.__dict__)
                continue  # has no position

            if self.clinfo.position.dist_sq(current_pos) > reach_dist_sq:
                continue

            current_dist = get_target_dist(current_pos)
            if nearest_dist > current_dist:  # closer to target pos
                nearest_dist = current_dist
                logger.debug('Entity %s is closer than %s',
                             current_entity.__class__.__name__,
                             nearest_ent.__class__.__name__)
                nearest_ent = current_entity
            else:
                logger.debug('Entity %s isnt closer than %s %s',
                             current_entity.__class__.__name__,
                             nearest_ent.__class__.__name__,
                             current_entity.__dict__)

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

    """drop_item
    @register_command('drop', '1?1?1')
    def drop_item(self, item_id, meta=None, amount=1):
        logger.debug('[drop handler] Dropping %ix %i:%i', amount, item_id, meta)
        class Closure:
            def __init__(self, parent, amount):
                self.parent = parent
                self.amount = amount
                self.dropped_slot = None

            def handler(self, evt=None, data={'slot_nr': None}):
                if self.dropped_slot is not None and self.dropped_slot != data['slot_nr']:
                    logger.debug('[drop handler] Not my slot')
                    return  # ignore
                slot = self.parent.inventory.find_slot(item_id, meta)
                if slot is None:
                    logger.debug('[drop handler] All available dropped')
                    return True  # nothing to drop left, cancel
                self.amount -= slot.amount
                self.parent.inventory.drop_slot(slot, drop_stack=True)
                self.dropped_slot = slot
                if self.amount <= 0:
                    logger.debug('[drop handler] All wanted dropped')
                    return True  # done, delete handler

        handler = Closure(self, amount).handler
        if not handler():
            self.event.reg_event_handler('inventory_set_slot', handler)
    """

    @register_command('plan', '?1')
    def print_plan(self, dy=0):
        center = self.clinfo.position
        visible_blocks = set()
        msg = ''
        for dz in range(-5, 6, 1):
            msg += '\n'
            for dx in range(-5, 6, 1):
                block_pos = Vec(dx, dy, dz).iadd(center)
                block_id, meta = self.world.get_block(*block_pos)
                visible_blocks.add((block_id, meta))

                if block_id == 0:
                    msg += '       '
                elif meta == 0:
                    msg += '%3i    ' % block_id
                else:
                    msg += '%3i:%-2i ' % (block_id, meta)

                if dx == dz == 0:  # mark bot position with brackets: [blockID]
                    msg = msg[:-8] + ('[%s]' % msg[-7:-1])

        for block_id, meta in sorted(visible_blocks):
            if block_id != 0:
                display_name = blocks.get_block(block_id, meta).display_name
                logger.info('%3i: %s' % (block_id, display_name))
        logger.info(msg)

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

    @register_command('hotbar', '*')
    def prepare_hotbar(self, *prepare_args):
        """ Puts items into the hotbar for quick access. """
        logger.warn('TODO')

    @register_command('clone', '333')
    def clone_area(self, c_from, c_to, c_target):
        logger.warn('TODO')

    @register_command('preset')
    def path_reset(self):
        self.path_queue = deque()

    @register_command('pgo')
    def path_go(self):
        if len(self.path_queue) > 0:
            self.tp_block(self.path_queue.popleft())
            self.timers.reg_event_timer(1, self.path_go, runs=1)

    @register_command('padd', '3')
    def path_add(self, coords):
        self.path_queue.append(coords)

    @register_command('pade', '3')
    def path_add_delta(self, delta):
        if len(self.path_queue) > 0:
            pos = Vec(self.path_queue[-1])
        else:
            pos = self.clinfo.position
        self.path_queue.append(pos + delta)

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

    @register_command('findblocks', '1?1?1?1?1')
    def find_blocks(self, b_id, b_meta=None, stop_at=10, min_y=0, max_y=256):
        prefix = '[Find Blocks][%s:%s]' % (b_id, b_meta)
        found = 0
        block_gen = self.iter_blocks(b_id, b_meta, min_y, max_y)

        def find_next(*args):
            nonlocal stop_at, found
            chunks_this_tick = 0
            while chunks_this_tick < 100:  # look at 100 chunks per event_tick
                chunks_this_tick += 1
                try:
                    found_block = next(block_gen)
                except StopIteration:
                    logger.info("%s Done, found all %i", prefix, found)
                    return True
                if found_block is None:  # another chunk searched, ...
                    return False  # continue search in next tick
                (x, y, z), (found_id, found_meta) = found_block
                logger.info('%s Found %s:%s at (%i %i %i)',
                            prefix, found_id, found_meta, x, y, z)
                found += 1
                # also continue search if negative stop_at
                if stop_at - found == 0:
                    logger.info('%s Done, found %i of them', prefix, found)
                    return True

        self.event.reg_event_handler('event_tick', find_next)

    def iter_blocks(self, ids, metas=None, min_y=0, max_y=256):
        """
        Generates tuples of found blocks in the loaded world.
        Tuple format: ((x, y, z), (id, meta))
        Also generates None to indicate that another column (16*16*256 blocks)
        has been searched. You can use this for pausing between chunk columns.
        `ids` and `metas` can be single values.
        """
        pos = self.clinfo.position
        # ensure correct types
        if isinstance(ids, int): ids = [ids]
        if metas is None: metas = []
        elif isinstance(metas, int): metas = [metas]

        # approx. squared distance client - column center
        def col_dist_sq(col_item):
            (col_x, col_z), col = col_item
            dist_x = pos.x - (col_x * 16 + 8)
            dist_z = pos.z - (col_z * 16 + 8)
            return dist_x * dist_x + dist_z * dist_z

        logger.debug('[iter_blocks] %i cols to search in',
                     len(self.world.columns))

        for (cx, cz), column in sorted(self.world.columns.items(),
                                       key=col_dist_sq):
            for cy, section in enumerate(column.chunks):
                if section and min_y // 16 <= cy <= max_y // 16:
                    for i, val in enumerate(section.block_data.data):
                        by = i // 256
                        y = by + 16 * cy
                        if min_y <= y <= max_y:
                            bid, bmeta = val >> 4, val & 0x0F
                            if bid in ids and (not metas or bmeta in metas):
                                bx = i % 16
                                bz = (i // 16) % 16
                                x = bx + 16 * cx
                                z = bz + 16 * cz
                                yield ((x, y, z), (bid, bmeta))
            # When the client moves around, it never unloads chunks,
            # so sometimes there are thousands of columns to search in,
            # which takes a while. By yielding None, we allow the caller
            # to do something else after each searched-in column.
            yield None
