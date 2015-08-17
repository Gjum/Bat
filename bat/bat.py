from collections import deque
from math import sqrt, asin, acos, pi
import logging

from spock.mcmap import mapdata
from spock.mcp.mcdata import UE_INTERACT, UE_ATTACK
from spock.plugins.base import PluginBase
from spock.plugins.helpers.entities import MovementEntity, PlayerEntity, ClientPlayerEntity, MobEntity
from spock.vector import Vector3 as Vec

from bat.command import register_command

logger = logging.getLogger('spock')


class BatPlugin(PluginBase):
    requires = ('ClientInfo', 'Entities', 'Inventory', 'World',
                'Event', 'Net', 'Timers',
                'Craft', 'Commands')
    events = {
        'chat_any': 'handle_chat',
        'PLAY>Player Position': 'on_send_position',
        'cl_health_update': 'on_health_change',
        'event_tick': 'on_event_tick',
    }
    # movement updates
    events.update({e: 'on_entity_move' for e in (
        'PLAY<Entity Relative Move',
        'PLAY<Entity Look And Relative Move',
        'PLAY<Entity Teleport',
    )})
    # logged events TODO remove
    events.update({e: 'debug_event' for e in (
        'LOGIN<Login Success', 'PLAY<Window Property', 'PLAY>Click Window',
        'PLAY<Spawn Player', 'PLAY<Player Position and Look',
        'cl_join_game', 'cl_health_update',
        'inv_open_window', 'inv_close_window', 'inv_win_prop',
        'inv_held_item_change', 'inv_set_slot',
    )})

    def __init__(self, ploader, settings):
        super(BatPlugin, self).__init__(ploader, settings)
        self.clinfo = self.clientinfo
        self.commands.register_handlers(self)
        self.path_queue = deque()
        self.pos_update_counter = 0
        self.checked_entities_this_tick = False

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
        if eid in self.entities.players:
            self.look_entity()  # looks at nearest player
        entity = self.entities.entities[eid]
        # force field
        if isinstance(entity, MobEntity):
            self.force_field()

    def force_field(self):
        own_pos = self.clinfo.position
        for entity in self.entities.mobs.values():
            if 5*5 > own_pos.dist_sq(Vec(entity)):
                self.net.push_packet('PLAY>Use Entity',
                                     {'target': entity.eid,
                                      'action': UE_ATTACK})
        self.checked_entities_this_tick = True

    def on_health_change(self, *args):
        health = self.clinfo.health.health
        food = self.clinfo.health.food
        can_regen = food >= 18
        can_sprint = food > 6
        starving = food <= 0

        # what do we want to do now?
        # TODO eating task

    def on_event_tick(self, *args):
        self.checked_entities_this_tick = False

    @register_command('help')
    def help(self):
        logger.info('Some available commands:')
        for cmd in (
                'plan',
                'findblocks id meta=-1 stop_at=10 min_y=0 max_y=256'

                'gravity',
                'tp coords',
                'tpb block_coords',
                'tpd delta_xyz',
                'come',
                'look',

                'dig coords',
                'place coords',
                'use',
                # 'clone c_from c_to c_target',

                'hit near_coords=own_pos'
                'int interact_coords=own_pos',
                'close',

                'showinv',
                'showhot',
                'select slot_index',
                # 'hotbar *prepare_args',
                'craft amount item meta=-1',

                'click slot',
                'hold item_id meta=-1',
                'drop item_id meta=-1 amount=1',
                'drops slot=None drop_stack="n"',
            ):
            logger.info('    %s', cmd)

    @register_command('tpb', '3')
    def tp_block(self, coords):
        self.teleport(Vec(.5, 0, .5).iadd(coords))

    @register_command('tpd', '3')
    def tp_delta(self, deltas):
        self.teleport(Vec(*deltas).iadd(self.clinfo.position))

    @register_command('tp', '3')
    def teleport(self, coords):
        self.clinfo.position.init(*coords)

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
        self.net.push_packet('PLAY>Chat Message', {'message': ' '.join(msgs)})

    def look_rel(self, vec):
        l, _, w = vec
        c = sqrt(l*l + w*w)
        try:
            alpha1 = -asin(l/c) / pi * 180
            alpha2 =  acos(w/c) / pi * 180
        except ZeroDivisionError:
            pass
        else:
            if alpha2 > 90:
                yaw = 180 - alpha1
            else:
                yaw = alpha1
            pitch = 0
            self.net.push_packet('PLAY>Player Look', {
                'yaw': yaw,
                'pitch': pitch,
                'on_ground': self.clinfo.position.on_ground
            })

    def look_pos(self, pos):
        self.look_rel(pos - self.clinfo.position)

    def look_entity(self, eid=None):
        """
        Looks at the entity.
        If no `eid` is given, looks at the nearest player in range.
        """
        look_pos = None
        if eid and eid in self.entities.entities:
            try:
                look_pos = Vec(self.entities.entities[eid])
            except ValueError:
                pass
        else:  # no eid, look at nearest player in range
            test = lambda e: isinstance(e, PlayerEntity)
            player = self.find_nearest_entity(max_dist=8, test=test)
            look_pos = Vec(player) if player else None
        if look_pos:
            self.look_pos(look_pos)

    def find_nearest_entity(self, search_pos=None, max_dist=4, test=None):
        search_pos = search_pos if search_pos else self.clinfo.position
        max_dist_sq = max_dist**2 if max_dist else float('inf')
        nearest_entity = None
        nearest_dist_sq = max_dist_sq
        for entity in self.entities.entities.values():
            # look at all entities that are not the bot and pass the test
            if not isinstance(entity, ClientPlayerEntity) \
                    and (test is None or test(entity)):
                try:
                    entity_pos = Vec(entity)
                except ValueError:  # entity has no position
                    continue
                else:
                    dist_sq = entity_pos.dist_sq(search_pos)
                    if dist_sq < nearest_dist_sq:
                        nearest_dist_sq = dist_sq
                        nearest_entity = entity
        return nearest_entity

    def interact_entity(self, coords=None, attack=False):
        vec = self.clinfo.position if coords is None else Vec(*coords)
        reach_dist = 4
        test = lambda e: isinstance(e, MovementEntity)
        entity = self.find_nearest_entity(vec, reach_dist, test=test)
        if entity:
            action = 1 if attack else 0
            self.net.push_packet('PLAY>Use Entity',
                                 {'target': entity.eid, 'action': action})
        return entity

    @register_command('look', '?e')
    def look_player(self, player):
        self.look_pos(Vec(player))

    @register_command('dig', '3')
    def dig_block(self, coords):
        # xxx use interact plugin
        packet = {
            'status': 0,  # start
            'location': Vec(*coords).get_dict(),
            'face': 1,
        }
        self.net.push_packet('PLAY>Player Digging', packet)
        packet['status'] = 2  # finish
        self.net.push_packet('PLAY>Player Digging', packet)

    @register_command('place', '3')
    def place_block(self, coords=None, vec=None):
        raise NotImplementedError('TODO use Interact plugin')  # xxx
        if vec is None: vec = Vec(*coords).floor()
        self.inventory.interact_with_block(vec)

    @register_command('int', '?3')
    def interact_at(self, coords=None):
        """
        Tries to interact with an entity near the given coordinates
        or near the client itself.
        If none is found, tries to interact with the block there.
        """
        entity = self.interact_entity(coords)
        if entity:
            logger.info('[Interact] Found entity at %s', Vec(entity))
        elif coords:
            block_coords = Vec(*coords).floor()
            block = self.world.get_block(*block_coords)
            logger.info('[Interact] Found no entity at %s, clicking block %s',
                        block_coords, block)
            raise NotImplementedError('TODO use Interact plugin')  # xxx
            if 0 != block[0]:
                self.inventory.interact_with_block(block_coords)

    @register_command('hit', '?3')
    def attack_entity(self, coords=None):
        entity = self.interact_entity(coords, True)
        if entity:
            logger.info('[Hit] Hit entity at %s', Vec(entity))
        else:
            logger.warn('[Hit] No entity found near %s', coords)

    @register_command('close')
    def close_window(self):
        self.inventory.close_window()

    @register_command('select', '1')
    def select_active_slot(self, slot_index):
        self.inventory.select_active_slot(slot_index)

    @register_command('showinv')
    def show_inventory(self, *args):
        nice_slot = lambda s: '    --    ' if s.amount <= 0 \
            else '%2ix %3i:%-2i' % (s.amount, s.item_id, s.damage)
        nice_slots = lambda slots: ' '.join(nice_slot(s) for s in slots)
        window = self.inventory.window
        inv_start = window.inventory_slots[0].slot_nr
        logger.info('window: %s', nice_slots(window.window_slots))
        for line in range(3):
            i = 9 * line
            logger.info('inv: %2i %s', i + inv_start, nice_slots(window.inventory_slots[i:i+9]))
        logger.info('hotbar: %s', nice_slots(window.hotbar_slots))
        logger.info('cursor: %s', nice_slot(self.inventory.cursor_slot))

    @register_command('showhot')
    def show_hotbar(self):
        self.show_hotbar_slotcounter = 0  # FIXME XXX TODO EVIL HACK
        def cb():
            self.inventory.select_active_slot(self.show_hotbar_slotcounter % 9)
            self.show_hotbar_slotcounter += 1
        self.timers.reg_event_timer(0.5, cb, runs=10)

    @register_command('drops', '?1?s')
    def drop_slot(self, slot=None, drop_stack='n'):
        if type(slot) is str:  # TODO bad argument parsing
            logger.debug('argh')
            drop_stack = slot
            slot = None
        drop_stack = 'n' not in drop_stack
        logger.debug('Dropping: %s %s', slot, drop_stack)
        self.inventory.drop_slot(slot, drop_stack)

    @register_command('drop', '1?1?1')
    def drop_item(self, item_id, meta=-1, amount=1):
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

    @register_command('plan')
    def print_plan(self):
        center = self.clinfo.position
        blocks = set() # will contain all present blocks for convenient lookup
        msg = ''
        for z in range(-5, 6, 1):
            msg += '\n'
            for x in range(-5, 6, 1):
                block_id, meta = self.world.get_block(*Vec(x, -1, z).iadd(center))
                blocks.add((block_id, meta))
                if block_id == 0:
                    msg += '       '
                elif meta == 0:
                    msg += '%3i    ' % block_id
                else:
                    msg += '%3i:%-2i ' % (block_id, meta)
                if x == z == 0:  # mark bot position with [$blockID]
                    msg = msg[:-8] + '[%s]' % msg[-7:-1]
        for block_id, meta in blocks:  # print names of all present blocks for convenient lookup
            if block_id != 0:
                print('%3i: %s' % (block_id, mapdata.get_block(block_id, meta).display_name))
        print(msg)

    @register_command('click', '*')
    def click_slot(self, *slots):
        for slot_nr in slots:
            try:
                slot = self.inventory.window.slots[int(slot_nr)]
                self.inventory.click_slot(slot)
            except:
                raise

    @register_command('use')
    def use_item(self):
        logger.debug('[Use] %s', self.inventory.active_slot)
        packet = {
            'location': {'x':-1, 'y':255, 'z':-1},
            'direction': -1,
            'held_item': self.inventory.active_slot.get_dict(),
            'cur_pos_x': -1,
            'cur_pos_y': -1,
            'cur_pos_z': -1,
        }
        self.net.push_packet('PLAY>Player Block Placement', packet)

    @register_command('hold', '1?1')
    def hold_item(self, item_id, meta=-1):
        logger.debug('hold item %s:%s', item_id, meta)
        raise NotImplementedError('TODO hold item')  # xxx
        found = self.inventory.hold_item(item_id, meta)
        if found:
            logger.info('Found item %i:%i', item_id, meta)
        else:
            logger.warn('Could not find item %i:%i', item_id, meta)

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
    def craft_item(self, amount, item, meta=-1):
        def cb(response):
            self.hold_item(item, meta)
            self.show_inventory()
            logger.info('[Craft][%sx %s:%s] Response: %s', amount, item, meta, response)
        recipe = self.craft.craft(item, meta, amount=amount, callback=cb)
        if recipe:
            logger.info('[Craft][%sx %s:%s] Crafting, recipe: %s', amount, item, meta, recipe.ingredients)
        else:
            logger.info('[Craft][%sx %s:%s] Not crafting, no recipe found', amount, item, meta)

    def swap_slots_task(self, a, b):
        inv = self.inventory
        if bool(inv.cursor_slot) or bool(inv.window.slots[a]):
            yield inv.click_slot(a)
        if bool(inv.cursor_slot) or bool(inv.window.slots[b]):
            yield inv.click_slot(b)
        if bool(inv.cursor_slot) or bool(inv.window.slots[a]):
            yield inv.click_slot(a)

    @register_command('findblocks', '1?1?1?1?1')
    def find_blocks(self, b_id, b_meta=-1, stop_at=10, min_y=0, max_y=256):
        prefix = '[Find Blocks][%s:%s]' % (b_id, b_meta)
        found = 0
        block_gen = self.iter_blocks(b_id, b_meta, min_y, max_y)

        def find_next(*args):
            nonlocal stop_at, found
            chunks_this_tick = 0
            while chunks_this_tick < 100:  # look at 100 chunks every event_tick
                chunks_this_tick += 1
                try:
                    found_block = next(block_gen)
                except StopIteration:
                    logger.info("%s Done, found all %i", prefix, found)
                    return True
                if found_block is None:  # another chunk searched, ...
                    return False  # continue search in next tick
                (x, y, z), (found_id, found_meta) = found_block
                logger.info('%s Found %s:%s at (%i %i %i)', prefix, found_id, found_meta, x, y, z)
                found += 1
                if stop_at - found == 0:  # also continue search if negative stop_at
                    logger.info('%s Done, found %i of them', prefix, found)
                    return True

        self.event.reg_event_handler('event_tick', find_next)

    def iter_blocks(self, ids, metas=-1, min_y=0, max_y=256):
        """
        Generates tuples of found blocks in the loaded world.
        Tuple format: ((x, y, z), (id, meta))
        Also generates None to indicate that another column (16*16*256 blocks)
        has been searched. Ignore these or use them for pausing between chunks.
        `ids` and `metas` can be single values.
        """
        pos = self.clinfo.position
        # ensure correct types
        if isinstance(ids, int): ids = [ids]
        if metas == -1: metas = ()

        # approx. squared distance client - column center
        def col_dist_sq(col_item):
            (col_x, col_z), col = col_item
            dist_x = pos.x - (col_x*16 + 8)
            dist_z = pos.z - (col_z*16 + 8)
            return dist_x * dist_x + dist_z * dist_z

        logger.debug('%i cols to search in', len(self.world.columns))

        for (cx, cz), column in sorted(self.world.columns.items(), key=col_dist_sq):
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
