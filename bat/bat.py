import logging

from collections import deque
from spock.mcdata import constants
from spock.mcmap import mapdata
from spock.plugins.base import PluginBase
from spock.task import TaskCallback, TaskFailed, RunTask, accept
from spock.vector import Vector3 as Vec

from bat.command import register_command


logger = logging.getLogger('spock')


import importlib, sys, types


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
    def __init__(self, name, interact=None):
        self.name = name
        self.interact = interact

    def on_success(self, data):
        printer = self.interact.chat if self.interact else logger.info
        printer('Task "%s" finished successfully: %s' % (self.name, data))

    def on_error(self, error):
        printer = self.interact.chat if self.interact else logger.warn
        printer('Task "%s" failed: %s' % (self.name, error.args))


# noinspection PyUnresolvedReferences
class BatPlugin(PluginBase):#, Reloadable):
    _persistent_attributes = ('path_queue', 'event')

    requires = ('Event', 'Net', 'Timers',
                'ClientInfo', 'Entities', 'Interact', 'World',
                'Craft', 'Commands', 'Inventory')
    events = {
        'chat_any': 'handle_chat',
        'PLAY>Player Position': 'on_send_position',
        'cl_health_update': 'on_health_change',
        'event_tick': 'on_event_tick',
        'inv_click_response': 'show_inventory',  # xxx remove
    }
    # movement updates
    events.update({e: 'on_entity_move' for e in (
        'PLAY<Entity Relative Move',
        'PLAY<Entity Look And Relative Move',
        'PLAY<Entity Teleport',
    )})
    # logged events TODO remove
    events.update({e: 'debug_event' for e in (
        'LOGIN<Login Success', 'PLAY<Player Position and Look',
        'PLAY<Window Property', 'PLAY>Click Window', 'PLAY<Open Window',
        'cl_join_game', 'cl_health_update',
        'inv_open_window', 'inv_close_window', 'inv_win_prop',
        'inv_held_item_change', 'inv_click_response',
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

    def debug_event(self, evt, data):
        data = getattr(data, 'data', data)
        logger.debug('%s: %s', evt, data)

    def handle_chat(self, evt, packet):
        logger.info('[Chat] <%s via %s> %s',
                    packet['name'], packet['sort'], packet['text'])

    def on_send_position(self, evt, packet):
        self.pos_update_counter += 1
        if self.pos_update_counter > 20:
            self.apply_gravity()
            self.pos_update_counter = 0

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
        if False and not self.checked_entities_this_tick:  # xxx reactivate
            for entity in self.entities.mobs.values():
                if 5 * 5 > dist_sq(Vec(entity)):
                    self.interact.attack_entity(entity)
            self.checked_entities_this_tick = True

    def on_health_change(self, *args):
        health = self.clinfo.health.health
        food = self.clinfo.health.food
        can_regen = food >= 18
        can_sprint = food > 6
        starving = food <= 0

        # TODO eating task
        if food < 14:  # chicken restores full hunger bar
            logger.info('Eating...')
            self.hold_item(366)
            self.activate_item()
        elif starving:
            logger.info("I'm starving, bye!")
            self.event.kill()  # disconnect

    def on_event_tick(self, *args):
        self.checked_entities_this_tick = False

        if len(self.entities.entities) > 300:
            logger.info("Too many entities, bye!")
            self.event.kill()  # disconnect

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
            return 'sleep_over', accept

        chat = lambda *texts: self.event.emit('chat_any', {
            'name': 'RELOADER', 'sort': 'TEST', 'text': ' '.join(texts)})

        def task():
            chat('before reload 123')
            do_the_reload()
            yield wait(1)
            chat('after reload 234')

        RunTask(task(), self.event.reg_event_handler,
                TaskChatter('Reloader', self.interact))

    @register_command('tpb', '3')
    def tp_block(self, coords):
        self.teleport(Vec(.5, 0, .5).iadd(coords))

    @register_command('tpd', '3')
    def tp_delta(self, deltas):
        self.teleport(Vec(*deltas).iadd(self.clinfo.position))

    @register_command('tp', '3')
    def teleport(self, coords):
        self.clinfo.position.init(*coords)
        # self.interact.chat('/tp %i %i %i' % coords))

    @register_command('come', '?e')
    def tp_to_player(self, player=None):
        if player is None:
            logger.warn('[Come] No player to teleport to')
        else:
            self.teleport(Vec(player))

    @register_command('gravity')
    def apply_gravity(self):
        def can_stand_on(vec):
            block_id, meta = self.world.get_block(*vec)
            return 0 != block_id  # TODO do a proper collision test
        pos = self.clinfo.position
        below = Vec(0, -1, 0).iadd(pos).ifloor()
        if can_stand_on(below):
            return  # already on ground
        for dy in range(int(below.y)):
            block_pos = Vec(0, -dy, 0).iadd(below)
            if can_stand_on(block_pos):
                pos.init(.5, 1., .5).iadd(block_pos)
                logger.debug('[Gravity] Corrected to y=%.2f', pos.y)
                break

    @register_command('say', '*')
    def chat_say(self, *msgs):
        self.interact.chat(' '.join(msgs))

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

        unreachable = lambda pos: self.clinfo.position.dist_sq(pos) > 4 * 4

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

            if unreachable(current_pos):
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
        show_hotbar_slotcounter = 0
        def cb():
            nonlocal show_hotbar_slotcounter
            self.inv.select_active_slot(show_hotbar_slotcounter % 9)
            show_hotbar_slotcounter += 1
        self.timers.reg_event_timer(0.5, cb, runs=10)

    """drop{slot|item}
    @register_command('drops', '?1?s')
    def drop_slot(self, slot=None, drop_stack='n'):
        if type(slot) is str:  # TODO bad argument parsing
            logger.debug('argh')
            drop_stack = slot
            slot = None
        drop_stack = 'n' not in drop_stack
        logger.debug('Dropping: %s %s', slot, drop_stack)
        self.inv.drop_slot(slot, drop_stack)

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
            self.event.reg_event_handler('inv_set_slot', handler)
    """

    @register_command('plan')
    def print_plan(self):
        center = self.clinfo.position
        visible_blocks = set()
        msg = ''
        for z in range(-5, 6, 1):
            msg += '\n'
            for x in range(-5, 6, 1):
                block_pos = Vec(x, -1, z).iadd(center)
                block_id, meta = self.world.get_block(*block_pos)
                visible_blocks.add((block_id, meta))

                if block_id == 0:
                    msg += '       '
                elif meta == 0:
                    msg += '%3i    ' % block_id
                else:
                    msg += '%3i:%-2i ' % (block_id, meta)

                if x == z == 0:  # mark bot position with brackets: [blockID]
                    msg = msg[:-8] + '[%s]' % msg[-7:-1]

        for block_id, meta in sorted(visible_blocks):
            if block_id != 0:
                display_name = mapdata.get_block(block_id, meta).display_name
                print('%3i: %s' % (block_id, display_name))
        print(msg)

    @register_command('click', '*')
    def click_slots(self, *slots):
        RunTask(self.inv.async.click_slots(*(int(nr) for nr in slots)),
                self.event.reg_event_handler,
                TaskChatter('Click %s' % str(slots), self.interact))

    @register_command('use')
    def activate_item(self):
        self.interact.activate_item()

    @register_command('unuse')
    def deactivate_item(self):
        self.interact.deactivate_item()

    @register_command('hold', '1?1')
    def hold_item(self, item_id, meta=None):
        logger.info('[Hold item] %i:%s', item_id, meta)
        RunTask(self.inv.async.hold_item((int(item_id), meta and int(meta))),
                self.event.reg_event_handler,
                TaskChatter('Hold item %i:%s' % (item_id, meta),
                            self.interact))

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
            pos = self.path_queue[-1]
        else:
            pos = self.clinfo.position
            pos = [pos.x, pos.y, pos.z]
        coords = [c+d for c, d in zip(pos, delta)]
        self.path_queue.append(coords)
        logger.debug('appending to path: %s', str(coords))

    @register_command('craft', '11?1')
    def craft_item(self, amount, item, meta=None):
        def cb(result):
            self.show_inventory()
            logger.info('[Craft][%sx %s:%s] Success: %s',
                        amount, item, meta, result)

        def eb(error):
            self.show_inventory()
            logger.info('[Craft][%sx %s:%s] Error: %s',
                        amount, item, meta, error)
            logger.info('inv.window: %s',
                        dir(self.inv.window))

        recipe = self.craft.craft(item, meta, amount,
                                  parent=TaskCallback(cb, eb))
        if recipe:
            logger.info('[Craft][%sx %s:%s] Crafting, recipe: %s',
                        amount, item, meta, recipe.ingredients)
        else:
            logger.info('[Craft][%sx %s:%s] Not crafting, no recipe found',
                        amount, item, meta)

    @register_command('do')
    def do(self):
        self.open_block((44, 3, -1105))
        def cb(): self.craft_item(1, 276)
        self.timers.reg_event_timer(1, cb, runs=1)

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
        has been searched. You can use them for pausing between chunks.
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
            dist_x = pos.x - (col_x*16 + 8)
            dist_z = pos.z - (col_z*16 + 8)
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
            # which takes a while. By yielding None, we enable the caller
            # to do something else after each searched-in column.
            yield None
