import os
import random
from nbt.nbt import TAG_Compound

from quarry.net.client import ClientFactory, ClientProtocol, register
from quarry.mojang.profile import Profile

from entity import EntityHandler
from world import World
from window import WindowHandler
from astar import astar
from info import packet_dict # TODO only used for logging
from info import item_or_block

def center_and_jitter(coords):
    # 0.5: center on block, jitter by 0.2 (player apothem minus a bit)
    coords[0] += 0.5 + 0.2 * (1 - 2*random.random())
    coords[2] += 0.5 + 0.2 * (1 - 2*random.random())
    return coords

def get_yaw_from_movement_delta(delta):
    """ For rectangular delta, return yaw [0..360); otherwise return 0 """
    if delta[0] < 0: return  90
    if delta[2] < 0: return 180
    if delta[0] > 0: return 270
    return 0


class BotProtocol(ClientProtocol):

    def setup(self):
        self.coords = [0, 0, 0]
        self.yaw = 0
        self.pitch = 0
        self.selected_slot = 0
        self.health = 0
        self.food = 0
        self.saturation = 0

        self.world = World()
        self.window_handler = WindowHandler()
        self.entities = EntityHandler()

        self.spawned = False
        self.digging_block = None
        self.pathfind_path = None
        self.is_pathfinding = False

    ##### Helper functions #####

    def log_packet(self, prefix, packet_id):
        """ overrides default logging """
        if self.protocol_mode == 'play':
            prefix = prefix[2:]
            ignored = {
                    'send': [
                        0x00, 0x01,
                        0x04, 0x05, 0x06, 0x07,
                        ],
                    'recv': [
                        0x00, 0x01, 0x02, 0x03,
                        0x06,
                        0x08, 0x09,
                        #0x0a, # receive use bed
                        0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13,
                        0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e,
                        0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
                        #0x27, # receive explosion
                        0x28, 0x29, 0x2a,
                        0x2d, 0x2e, 0x2f, 0x30,
                        0x32,
                        0x37, 0x38,
                        0x40,
                        0x42,
                        ],
            }
            if packet_id not in ignored[prefix]:
                info = '' if packet_id not in packet_dict['play'][prefix] else packet_dict['play'][prefix][packet_id]
                print '%s %#02x %s' % (prefix, packet_id, info)

    def dig_block(self, *args):
        if len(args) < 3:
            print '[dig_block] Not enough args:', args
            return
        x, y, z = coords = map(int, args[:3])
        if self.digging_block is not None:
            print '[dig_block] Already digging at', self.digging_block, '- aborting' # IDEA queue?
            return
        dx, dy, dz = (c - a for c, a in zip(self.coords, coords))
        if 4*4 < dx*dx + dy*dy + dz*dz:
            print '[dig_block] Block too far away - aborting'
            return
        if self.world.get_block(coords) == 0:
            print '[dig_block] Air cannot be dug - aborting'
            return
        # pick a face with an adjacent air block TODO any face seems to work, even if obstructed
        face = 0
        #faces = [(0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0)]
        #for face, (dx, dy, dz) in enumerate(faces):
        #    if self.world.get_block((x+dx, y+dy, z+dz)) == 0:
        #        break
        # remember this block to prevent digging a second one before this one is finished
        self.digging_block = coords
        self.send_player_digging(0, coords, face) # start digging and ...
        self.send_player_digging(2, coords, face) # ... immediately stop, server sends block update when done
        # IDEA look at the block

    def place_block(self, *args):
        """ Places the selected block (in the hotbar) at the specified coordinates """
        if len(args) < 3:
            print 'Not enough args for place_block:', args
            return
        self.send_player_block_placement(args[:3])

    def hold_item(self, *args):
        """Places a stack of the specified wanted_item_id in the hotbar and selects it"""
        if len(args) < 1:
            print '[Hold item] Not enough args:', args
            return
        wanted_item_id = int(args[0])
        if wanted_item_id == self.window_handler.get_hotbar()[self.selected_slot].item_id:
            return # wanted item already selected
        # not selected, search for it
        slot_with_item = -1 # last slot with wanted item
        # hotbar is at the end of the inventory, search there first
        for slot_nr, slot in enumerate(self.window_handler.get_hotbar()):
            if slot.item_id == wanted_item_id:
                self.select_slot(slot_nr)
                return
        for slot_nr, slot in enumerate(self.window_handler[0].slots):
            if slot.item_id == wanted_item_id:
                # num-swap into hotbar
                # window_id = 0, button = selected_slot, mode = 2
                self.send_click_window(0, slot_nr, self.selected_slot,
                        self.window_handler.next_action_id(), 2, slot)
                return
        print '[Hold item]', item_or_block(wanted_item_id)['name'], wanted_item_id, 'not found in inventory'
        return

    def select_slot(self, *args):
        if len(args) < 1:
            print 'Not enough args for select_slot:', args
            return
        self.send_select_slot(int(args[0]))
        self.send_player_position()

    def pickup_item_stack(self, eid):
        if eid not in self.entities:
            print '[Item pickup] Could not pick up', eid, '- already removed'
            return
        print '[Item pickup] Picking up', eid
        self.pathfind(*self.entities[eid].coords)

    def walk_one_block(self, direction):
        direction %= 4
        old_coords = [int(c) for c in self.coords]
        coords = old_coords[:]
        c = 0 if direction in (1, 3) else 2 # coordinate axis to move on
        d = 1 if direction in (1, 2) else -1 # how far to move
        coords[c] += d
        coords = center_and_jitter(coords)
        yaw = get_yaw_from_movement_delta([int(n) - int(o) for n, o in zip(coords, old_coords)])
        self.send_player_position_and_look(coords, yaw, 0)
        self.send_player_look(yaw, 0)

    def pathfind(self, *args):
        """ Creates a path to the specified coordinates.
        By calling pathfind_continue() every 0.05s, the bot follows the path.
        The path gets updated by on_world_changed(). """
        if len(args) < 3:
            print '[Pathfinding] Not enough args:', args
            return
        target = args[:3]
        print '[Pathfinding] Finding path to', target, '...'
        try:
            self.pathfind_path = astar(self.coords, target, self.world)
        except ValueError:
            print '[Pathfinding] Invalid args:', args
            return
        if len(self.pathfind_path) <= 0:
            print '[Pathfinding] No path found'
            self.pathfind_path = [target] # save for later
            self.is_pathfinding = False
        else:
            self.pathfind_path.pop(0) # skip starting position
            print '[Pathfinding] Path found:', len(self.pathfind_path), 'blocks long'
            if len(self.pathfind_path) == 0:
                # pathfind_continue would not move the bot, so send position now
                self.send_player_position()
                return
            if not self.is_pathfinding:
                self.is_pathfinding = True
                self.pathfind_continue()

    def pathfind_continue(self):
        if not self.is_pathfinding: return
        if self.pathfind_path is None: return
        if len(self.pathfind_path) <= 0:
            self.pathfind_path = None
            self.is_pathfinding = False
        else:
            coords = center_and_jitter(list(self.pathfind_path.pop(0)))
            delta = [int(n) - int(o) for o, n in zip(self.coords, coords)] # direction bot is walking in
            yaw = get_yaw_from_movement_delta(delta)
            self.send_player_position_and_look(coords, yaw, 0)
            self.send_player_look(yaw, 0)
            if len(self.pathfind_path) <= 0:
                self.pathfind_path = None
                self.is_pathfinding = False
            else:
                self.tasks.add_delay(0.05, self.pathfind_continue) # IDEA test how fast the bot can go

    def respawn(self):
        print 'Respawning'
        self.send_status(0)

    ##### Events #####

    def on_command(self, cmd, *args):
        print '[Command]', cmd, args
        if cmd == 'path': self.pathfind(*args)
        elif cmd == 'tp': self.send_player_position(list(map(int, args[:3])))
        elif cmd == 'dig': self.dig_block(*args)
        elif cmd == 'place': self.place_block(*args)
        elif cmd == 'hold': self.hold_item(*args)
        elif cmd == 'select': self.select_slot(*args)
        elif cmd == 'n': self.walk_one_block(0)
        elif cmd == 'e': self.walk_one_block(1)
        elif cmd == 's': self.walk_one_block(2)
        elif cmd == 'w': self.walk_one_block(3)
        else:
            if cmd not in 'help': print 'Unknown command', cmd, args
            print 'Available commands:'
            print '    path <coords>'
            print '    tp <coords>'
            print '    dig <coords>'
            print '    place <coords>'
            print '    hold <item ID>'
            print '    select <slot>'
            print '    n e s w'

    def on_update_health(self):
        print 'health:', self.health, 'food:', self.food, 'saturation:', self.saturation
        if self.health <= 0:
            self.respawn()

    def on_player_spawned(self, eid):
        pass # TODO do something

    def on_object_spawned(self, eid):
        #pass # TODO do something
        if self.entities[eid].e_type == 2: # item stack
            # maybe pick up later
            def cont(self, eid):
                dist = sum(map(lambda (e,p): abs(e-p), zip(self.entities[eid].coords, self.coords)))
                if dist < 30:
                    self.pickup_item_stack(eid)
            self.tasks.add_delay(2.05, cont, self, eid) # wait two seconds and a tick

    def on_mob_spawned(self, eid):
        pass # TODO do something

    def on_world_changed(self, how='somehow'):
        #print 'world changed:', how
        if self.digging_block is not None:
            if self.world.get_block(self.digging_block) == 0:
                self.digging_block = None # done digging, block is now air
        if self.pathfind_path is not None and len(self.pathfind_path) > 0:
            # TODO check if changed blocks are on path or otherwise reduce frequency on packet bulk
            for coords in self.pathfind_path:
                if True:
                    break
            else:
                # recalculate, blocks may have changed
                self.pathfind(*self.pathfind_path[-1])

    def on_open_window(self, window_id):
        pass # TODO do something

    def on_close_window(self, window_id):
        pass # TODO do something

    def on_slot_change(self, window_id, slot_nr):
        pass # TODO do something

    def on_confirm_transaction(self, window_id, action_id, accepted):
        pass # TODO do something

    ##### Network: sending #####

    # TODO move pack_slot somewhere else, maybe into util.buffer?
    def pack_slot(self, slot):
        return self.buff_type.pack('h', -1)
        # TODO actually pack the slot
        buff = self.buff_type.pack('h', slot.item_id)
        if slot.item_id >= 0: # slot is not empty
            buff += self.buff_type.pack('b', slot.count)
            buff += self.buff_type.pack('h', slot.damage)
            buff += self.buff_type.pack('b', -1) # TODO pack enchants (NBT)
        return buff

    def send_player_position(self, coords=None, on_ground=True):
        if coords is not None: self.coords = coords
        self.send_packet(0x04, self.buff_type.pack('ddd?',
            self.coords[0],
            self.coords[1],
            self.coords[2],
            on_ground))

    def send_player_look(self, yaw=None, pitch=None, on_ground=True):
        if yaw is not None: self.yaw = self.yaw
        if pitch is not None: self.pitch = self.pitch
        self.send_packet(0x05, self.buff_type.pack('ff?',
            self.yaw,
            self.pitch,
            on_ground))

    def send_player_position_and_look(self, coords=None, yaw=None, pitch=None, on_ground=True):
        if coords is not None: self.coords = coords
        if yaw is not None: self.yaw = yaw
        if pitch is not None: self.pitch = pitch
        self.send_packet(0x06, self.buff_type.pack('dddff?',
            self.coords[0],
            self.coords[1],
            self.coords[2],
            self.yaw,
            self.pitch,
            on_ground))

    def send_player_digging(self, status, coords, face=1):
        x, y, z = map(int, coords)
        location = ((x & 0x3ffffff) << 38) | ((y & 0xFFF) << 26) | (z & 0x3ffffff)
        self.send_packet(0x07, self.buff_type.pack('BQB',
            status,
            location,
            face))

    def send_player_block_placement(self, coords, face=1, cursor=(0, 0, 0)):
        x, y, z = map(int, coords)
        location = ((x & 0x3ffffff) << 38) | ((y & 0xFFF) << 26) | (z & 0x3ffffff)
        self.send_packet(0x08, self.buff_type.pack('QB', location, face)
            + self.pack_slot(self.window_handler.get_hotbar()[self.selected_slot]) # TODO slot to place from is ignored by Notchian server
            + self.buff_type.pack('BBB', *cursor))

    def send_select_slot(self, slot):
        self.selected_slot = slot
        self.send_packet(0x09, self.buff_type.pack('h', slot))

    def send_close_window(self, window_id):
        self.send_packet(0x0d, self.buff_type.pack('b', window_id))

    def send_click_window(self, window_id, slot_nr, button, action_id, mode, slot_item):
        self.send_packet(0x0e, self.buff_type.pack('bhbhb',
            window_id,
            slot_nr,
            button,
            action_id,
            mode)
            + self.pack_slot(slot_item))

    def send_enchant_item(self, window_id, enchantment_nr):
        self.send_packet(0x11, self.buff_type.pack('bb', window_id, enchantment_nr))

    def send_update_sign(self, coords, lines):
        """ Lines are ['first', 'second', '3', '4'] """
        if len(lines) != 4:
            print '[Update sign] Invalid number of lines:', lines
            return
        lines_data = ''
        for line in lines:
            lines_data += pack_chat(line)
        self.send_packet(0x12,
                self.buff_type.pack('bb', window_id, enchantment_nr)
                + lines_data)

    def send_client_settings(self, render_distance):
        self.send_packet(0x15, self.buff_type.pack_string("en_GB") +
            self.buff_type.pack('bb?B',
                render_distance,
                1,
                True,
                0xff))

    def send_status(self, action_id=0):
        """ 0 for respawn """
        self.send_packet(0x16, self.buff_type.pack_varint(action_id))

    ##### Network: receiving #####

    @register("play", 0x01)
    def received_join_game(self, buff):
        eid = buff.unpack('i')
        buff.discard() # TODO join game: parse the rest
        self.entities.add_player(eid)

    @register("play", 0x02)
    def received_chat_message(self, buff):
        text = buff.unpack_chat()
        chat_type = buff.unpack('B')
        chat_type = ('Chat', 'System', 'AutoComplete')[chat_type]
        print '[%s] %s' % (chat_type, text)

        if self.spawned and ', ' in text:
            # get the words/args as a list
            text = str(text[:-1]).split(', ')[1].split(' ')
            self.on_command(*text)

    @register("play", 0x06)
    def received_uptate_health(self, buff):
        self.health = buff.unpack('f')
        self.food = buff.unpack_varint()
        self.saturation = buff.unpack('f')
        self.on_update_health()

    @register("play", 0x08)
    def received_player_position_and_look(self, buff):
        """ Sent on spawning, teleport and motion error """
        coords = list(buff.unpack('ddd'))
        yaw = buff.unpack('f')
        pitch = buff.unpack('f')
        position_flags = buff.unpack('B')

        # bits in position_flags indicate relative values
        if position_flags & (1 << 0): coords[0] += self.coords[0]
        if position_flags & (1 << 1): coords[1] += self.coords[1]
        if position_flags & (1 << 2): coords[2] += self.coords[2]
        if position_flags & (1 << 3): yaw += self.yaw
        if position_flags & (1 << 4): pitch += self.pitch

        # if client just spawned, start sending player_look to prevent timeout
        # once per 30s, TODO might skip when sent some other packet recently
        if not self.spawned:
            self.spawned = True
            self.tasks.add_loop(29, self.send_player_look)

        print 'Position corrected: from', self.coords, 'to', coords

        # send back and set player position and look
        self.send_player_position_and_look(coords, yaw, pitch)

        self.on_world_changed('received_player_position_and_look')

        ### entities ###

    @register("play", 0x0c)
    def received_spawn_player(self, buff):
        eid = buff.unpack_varint()
        uuid = buff.unpack_uuid()
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        item = buff.unpack('h')
        data = {}
        buff.discard() # TODO read metadata
        # e_type=-1 for player (not official, used internally)
        self.entities.add_player(eid, uuid, coords, yaw, pitch, data, item)
        self.on_player_spawned(eid)

    @register("play", 0x0e)
    def received_spawn_object(self, buff):
        eid = buff.unpack_varint()
        obj_type = buff.unpack('b')
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        pitch, yaw = (i * 360 / 256 for i in buff.unpack('BB'))
        data = {}
        buff.discard() # TODO read entity data
        self.entities.add_object(eid, obj_type, coords, yaw, pitch, data)
        self.on_object_spawned(eid)

    @register("play", 0x0f)
    def received_spawn_mob(self, buff):
        eid = buff.unpack_varint()
        mob_type = buff.unpack('b')
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        head_pitch = buff.unpack('B') * 360 / 256
        velocity = [0,0,0]
        data = {}
        buff.discard() # TODO read velocity, metadata
        self.entities.add_mob(eid, mob_type, coords, yaw, pitch, data, velocity, head_pitch)
        self.on_mob_spawned(eid)

    @register("play", 0x12)
    def received_entity_velocity(self, buff):
        eid = buff.unpack_varint()
        velocity = [float(i) / 8000 for i in buff.unpack('hhh')]
        self.entities[eid].velocity = velocity

    @register("play", 0x13)
    def received_destroy_entities(self, buff):
        count = buff.unpack_varint()
        for i in range(count):
            eid = buff.unpack_varint()
            self.entities.remove(eid)

    @register("play", 0x15)
    def received_entity_relative_move(self, buff):
        eid = buff.unpack_varint()
        delta = [float(i) / 32 for i in buff.unpack('bbb')]
        on_ground = buff.unpack('?')
        self.entities[eid].relative_move(delta, on_ground)

    @register("play", 0x16)
    def received_entity_look(self, buff):
        eid = buff.unpack_varint()
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        on_ground = buff.unpack('?')
        self.entities[eid].look(yaw, pitch, on_ground)

    @register("play", 0x17)
    def received_entity_look_and_relative_move(self, buff):
        eid = buff.unpack_varint()
        delta = [float(i) / 32 for i in buff.unpack('bbb')]
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        on_ground = buff.unpack('?')
        self.entities[eid].relative_move(delta, on_ground)
        self.entities[eid].look(yaw, pitch, on_ground)

    @register("play", 0x18)
    def received_entity_teleport(self, buff):
        eid = buff.unpack_varint()
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        on_ground = buff.unpack('?')
        self.entities[eid].move(coords, on_ground)
        self.entities[eid].look(yaw, pitch, on_ground)

    @register("play", 0x19)
    def received_entity_head_look(self, buff):
        eid = buff.unpack_varint()
        yaw = buff.unpack('B') * 360 / 256
        self.entities[eid].head_look(yaw)

    @register("play", 0x1a)
    def received_entity_status(self, buff):
        eid = buff.unpack('i')
        status = buff.unpack('b')
        if status == 2: # Living Entity hurt, sent on health change
            self.tasks.add_delay(0.1, self.send_player_position) # send position update to receive health update

    ### blocks ###

    @register("play", 0x21)
    def received_chunk_data(self, buff):
        chunk_coords = buff.unpack('ii')
        ground_up_continuous = buff.unpack('?')
        bitmask = buff.unpack('H')
        size = buff.unpack_varint()
        skylight = True # assume not in Nether TODO
        self.world.unpack(buff, chunk_coords, bitmask, ground_up_continuous, skylight)
        self.on_world_changed('received_chunk_data for %d:%d' % chunk_coords)

    @register("play", 0x22)
    def received_multi_block_change(self, buff):
        chunk_x, chunk_z = buff.unpack('ii')
        block_count = buff.unpack_varint()
        for i in range(block_count):
            coord_bits = buff.unpack('H')
            y = coord_bits & 0xff
            z = (chunk_z * 16) + (coord_bits >> 8) & 0xf
            x = (chunk_x * 16) + (coord_bits >> 12) & 0xf
            data = buff.unpack_varint()
            self.world.set_block((x, y, z), data)
        self.on_world_changed('received_multi_block_change')

    @register("play", 0x23)
    def received_block_change(self, buff):
        location = buff.unpack('Q') # long long, 64bit
        data = buff.unpack_varint()
        x = location >> 38
        y = (location >> 26) & 0xfff
        z = location & 0x3ffffff
        self.world.set_block((x, y, z), data)
        self.on_world_changed('received_block_change')

    @register("play", 0x26)
    def received_map_chunk_bulk(self, buff):
        skylight = buff.unpack('?')
        column_count = buff.unpack_varint()
        ground_up_continuous = True # according to protocol, full chunks are sent
        chunk_coords = []
        bitmasks = []
        # unpack all meta info before data
        for col in range(column_count):
            chunk_coords.append(buff.unpack('ii'))
            bitmasks.append(buff.unpack('H'))
        for col in range(column_count):
            self.world.unpack(buff, chunk_coords[col], bitmasks[col], ground_up_continuous, skylight)
        self.on_world_changed('received_map_chunk_bulk')

    ### windows ###

    @register("play", 0x2d)
    def received_open_window(self, buff):
        window_id = buff.unpack('B')
        window_type = buff.unpack_string()
        window_title = buff.unpack_chat()
        num_slots = buff.unpack('B')
        horse_entity_id = buff.unpack('i') if window_type == 'EntityHorse' else None
        self.window_handler.open_window(window_id, window_type, window_title, num_slots, horse_entity_id)
        self.on_open_window(window_id)

    @register("play", 0x2e)
    def received_close_window(self, buff):
        window_id = buff.unpack('B')
        self.window_handler.close_window(window_id)
        self.on_close_window(window_id)

    # TODO move unpack_slot somewhere else, maybe into util.buffer?
    def unpack_slot(self, buff):
        item_id = buff.unpack('h')
        if item_id >= 0: # slot is not empty
            count = buff.unpack('b')
            damage = buff.unpack('h')
            nbt_start = buff.unpack('b')
            enchants = {}
            if nbt_start != 0: # stack has NBT data
                # For the NBT structure, see http://wiki.vg/Slot_Data#Format
                buff.unpack('bb') # skip to enchantment list
                nbt = TAG_Compound(buff) # unpacks the NBT data
                for e in nbt.get('ench'):
                    ench_id = e.get('id').value
                    ench_level = e.get('lvl').value
                    enchants[ench_id] =  ench_level
            return item_id, count, damage, enchants
        else: # clear slot
            return item_id, 0, 0, {}

    @register("play", 0x2f)
    def received_set_slot(self, buff):
        window_id = buff.unpack('b')
        slot_nr = buff.unpack('h') # number of the changed slot in the window
        slot = self.unpack_slot(buff) # tuple for slot instantiation
        if window_id != -1:
            self.window_handler[window_id].set_slot(slot_nr, *slot)
            self.on_slot_change(window_id, slot_nr)
        else: # Notchian server apparently sends window_id = slot_nr = -1 on /clear
            print 'received_set_slot suspects /clear: id', window_id, 'slot', slot_nr

    @register("play", 0x30)
    def received_window_items(self, buff):
        window_id = buff.unpack('B')
        num_slots = buff.unpack('h')
        for slot_nr in range(num_slots):
            self.window_handler[window_id].set_slot(slot_nr, *self.unpack_slot(buff))
            self.on_slot_change(window_id, slot_nr)

    @register("play", 0x32)
    def received_confirm_transaction(self, buff):
        window_id = buff.unpack('b')
        action_id = buff.unpack('h')
        accepted = buff.unpack('?')
        self.on_confirm_transaction(window_id, action_id, accepted)

    @register("play", 0x40)
    def received_disconnect(self, buff):
        reason = buff.unpack_string()
        print '[Disconnected] %s' % reason
        self.close()

    @register("play", 0x42)
    def received_combat(self, buff):
        event = buff.unpack_varint()
        combat_type = ('enter combat', 'end combat', 'entity dead')[event]
        print '[Combat]:', combat_type,
        if event == 1: # end combat
            duration = buff.unpack_varint()
            entity_id = buff.unpack('i')
            print 'duration:', duration, 'entity_id:', entity_id,
        if event == 2: # entity dead
            player_id = buff.unpack_varint()
            message = buff.unpack_string()
            entity_id = buff.unpack_varint()
            print 'player_id:', player_id, 'entity_id:', entity_id, 'message:', message,
        print


class BotFactory(ClientFactory):
    protocol = BotProtocol


def main(args):
    # Parse options
    if len(args) < 4:
        print 'usage: %s <connect-host> <connect-port> <username> [password]' % args[0]
        return 0
    host, port, username = args[1:4]
    password = args[4] if len(args) > 4 else None

    # Create profile
    profile = Profile()

    # Create factory
    factory = BotFactory()
    factory.profile = profile
    factory.connect(host, int(port))

    if password is not None:
        def login_ok(data):
            factory.connect(host, int(port))

        def login_failed(err):
            print "login failed:", err.value
            factory.stop()

        deferred = profile.login(username, password)
        deferred.addCallbacks(login_ok, login_failed)

    else:
        profile.login_offline(username)

    factory.run()

if __name__ == '__main__':
    import sys
    main(sys.argv)
