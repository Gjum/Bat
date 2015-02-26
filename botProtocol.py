from nbt.nbt import TAG_Compound

from quarry.net.client import ClientProtocol, register

from world import World
from entity import EntityHandler
from window import WindowHandler
from info import packet_dict # TODO only used for logging


class BotProtocol(ClientProtocol):

    def setup(self):
        self.eid = -1
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

    ##### Utils #####

    def log_packet(self, prefix, packet_id):
        """ overrides default logging """
        if self.protocol_mode == 'play':
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
                self.logger.debug('%s %#02x %s', prefix, packet_id, info)

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

    ##### Callbacks, should be overridden by childs #####

    def on_chat(self, chat_type, msg):
        chat_type_str = ('Chat', 'SystemMsg', 'AutoComplete')[chat_type]
        self.logger.info('[%s] %s', chat_type_str, text)

    def on_update_health(self):
        self.logger.info('health: %i, food: %i, saturation: %i', self.health, self.food, self.saturation)
        if self.health <= 0:
            self.respawn()

    def on_position_changed(self, old):
        self.logger.debug('Position corrected: from %s to %s', old, self.coords)

    def on_spawn_player(self, eid):
        pass # TODO do something

    def on_spawn_object(self, eid):
        pass # TODO do something

    def on_spawn_mob(self, eid):
        pass # TODO do something

    def on_entity_moved(self, eid):
        pass # TODO do something

    def on_entity_destroyed(self, eid):
        pass # TODO do something

    def on_entity_status(self, eid, status):
        entity_status_dict = {
                 0: "unknown: Something related to living entities?",
                 1: "unknown: Something related to the player entity?",
                 2: "Living Entity hurt",
                 3: "Living Entity dead",
                 4: "Iron Golem throwing up arms",
                 6: "Wolf/Ocelot/Horse taming - Spawn heart particles",
                 7: "Wolf/Ocelot/Horse tamed - Spawn smoke particles",
                 8: "Wolf shaking water - Trigger the shaking animation",
                 9: "(of self) Eating accepted by server",
                10: "Sheep eating grass",
                10: "Play TNT ignite sound",
                11: "Iron Golem handing over a rose",
                12: "Villager mating - Spawn heart particles",
                13: "Spawn particles indicating that a villager is angry and seeking revenge",
                14: "Spawn happy particles near a villager",
                15: "Witch animation - Spawn magic particles",
                16: "Play zombie converting into a villager sound",
                17: "Firework exploding",
                18: "Animal in love (ready to mate) - Spawn heart particles",
                19: "Reset squid rotation",
                20: "Spawn explosion particle - works for some living entities",
                21: "Play guardian sound - works for every entity",
                22: "Enables reduced debug for players",
                23: "Disables reduced debug for players",
        }
        self.logger.debug('[entity status] eid %i: %s', eid, entity_status_dict[status])

    def on_world_changed(self, how='somehow'):
        # TODO think of useful callbacks
        pass #self.logger.debug('[world changed] %s', how)

    def on_open_window(self, window_id):
        pass # TODO do something

    def on_close_window(self, window_id):
        pass # TODO do something

    def on_slot_change(self, window_id, slot_nr):
        pass # TODO do something

    def on_confirm_transaction(self, window_id, action_id, accepted):
        pass # TODO do something

    def on_combat(self, event, duration=0, player_id=0, entity_id=0, message=''):
        combat_type = ('enter combat', 'end combat', 'entity dead')[event]
        msg = '[Combat]:' + combat_type
        if event == 1: # end combat
            msg += 'duration: %i, entity_id: %i' % (duration, entity_id)
        if event == 2: # entity dead
            msg += 'player_id: %i, entity_id: %i, message: "%s"' % (player_id, entity_id, message)
        self.logger.info(msg)

    ##### Network: sending #####

    def send_chat(self, msg):
        self.send_packet(0x01, self.buff_type.pack_string(msg))

    def send_player_position(self, coords=None, on_ground=True):
        if coords is not None: self.coords = list(map(float, coords))
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
            self.logger.debug('[Update sign] Invalid number of lines: %i', lines)
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
        self.eid = eid
        self.entities.add_player(eid)

    @register("play", 0x02)
    def received_chat_message(self, buff):
        text = buff.unpack_chat()
        chat_type = buff.unpack('B')
        self.on_chat(chat_type, text)

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

        # send back and set player position and look
        old = self.coords # keep for callback
        self.send_player_position_and_look(coords, yaw, pitch)

        # client just spawned
        if not self.spawned:
            self.spawned = True
            # send position update every tick to receive health updates and update held item
            self.tasks.add_loop(1.0/20, self.send_player_position)

        self.on_position_changed(old)

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
        #self.entities.add_player(eid, uuid, coords, yaw, pitch, data, item)
        self.on_spawn_player(eid)

    @register("play", 0x0e)
    def received_spawn_object(self, buff):
        eid = buff.unpack_varint()
        obj_type = buff.unpack('b')
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        pitch, yaw = (i * 360 / 256 for i in buff.unpack('BB'))
        data = {}
        buff.discard() # TODO read entity data
        self.entities.add_object(eid, obj_type, coords, yaw, pitch, data)
        self.on_spawn_object(eid)

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
        self.on_spawn_mob(eid)

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
            self.on_entity_destroyed(eid)

    @register("play", 0x15)
    def received_entity_relative_move(self, buff):
        eid = buff.unpack_varint()
        delta = [float(i) / 32 for i in buff.unpack('bbb')]
        on_ground = buff.unpack('?')
        self.entities[eid].relative_move(delta, on_ground)
        self.on_entity_moved(eid)

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
        self.on_entity_moved(eid)

    @register("play", 0x18)
    def received_entity_teleport(self, buff):
        eid = buff.unpack_varint()
        coords = [float(i) / 32 for i in buff.unpack('iii')]
        yaw, pitch = (i * 360 / 256 for i in buff.unpack('BB'))
        on_ground = buff.unpack('?')
        self.entities[eid].move(coords, on_ground)
        self.entities[eid].look(yaw, pitch, on_ground)
        self.on_entity_moved(eid)

    @register("play", 0x19)
    def received_entity_head_look(self, buff):
        eid = buff.unpack_varint()
        yaw = buff.unpack('B') * 360 / 256
        self.entities[eid].head_look(yaw)

    @register("play", 0x1a)
    def received_entity_status(self, buff):
        eid = buff.unpack('i')
        status = buff.unpack('b')
        self.on_entity_status(eid, status)

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
            data = buff.unpack_varint()
            y = coord_bits & 0xff
            z = (chunk_z * 16) + (coord_bits >> 8) & 0xf
            x = (chunk_x * 16) + (coord_bits >> 12) & 0xf
            self.world.set_block((x, y, z), data)
        self.on_world_changed('received_multi_block_change')

    @register("play", 0x23)
    def received_block_change(self, buff):
        location = buff.unpack('q') # long long, 64bit
        data = buff.unpack_varint()
        x = location >> 38
        y = (location >> 26) & 0xfff
        z = location & 0x3ffffff
        if z & (1 << 25): z -= (1 << 26) # fix & not taking into account negative numbers
        print 'block_change', x, y, z, data
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

    @register("play", 0x2f)
    def received_set_slot(self, buff):
        window_id = buff.unpack('b')
        slot_nr = buff.unpack('h') # number of the changed slot in the window
        slot = self.unpack_slot(buff) # tuple for slot instantiation
        if window_id != -1: # Notchian server apparently sends window_id = slot_nr = -1 on /clear, ignore
            self.window_handler[window_id].set_slot(slot_nr, *slot)
            self.on_slot_change(window_id, slot_nr)

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
        self.logger.warn('[Disconnected] %s', reason)
        self.close()

    @register("play", 0x42)
    def received_combat(self, buff):
        event = buff.unpack_varint()
        duration, player_id, entity_id, message = 0, 0, 0, ''
        if event == 1: # end combat
            duration = buff.unpack_varint()
            entity_id = buff.unpack('i')
        if event == 2: # entity dead
            player_id = buff.unpack_varint()
            message = buff.unpack_string()
            entity_id = buff.unpack_varint()
        self.on_combat(event, duration, player_id, entity_id, message)

