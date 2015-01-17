import os

from quarry.net.client import ClientFactory, ClientProtocol, register
from quarry.mojang.profile import Profile
from world import World
from ai import astar

packet_dict = {
    'play': {
        'send': {
            0x04: 'player position',
            0x05: 'player look',
            0x06: 'player position and look',
            0x07: 'player digging',
        },
        'recv': {
            0x00: 'keep alive',
            0x02: 'chat message',
            0x03: 'time update',
            0x06: 'player health',
            0x08: 'player position and look',
            0x0b: 'animation',
            0x0c: 'spawn player',

            0x12: 'entity velocity',
            0x14: 'entity init',
            0x15: 'entity relative move',
            0x16: 'entity look',
            0x17: 'entity rel move and look',
            0x18: 'entity teleport',
            0x19: 'entity head look',
            0x1a: 'entity status',

            0x1f: 'player experience',

            0x21: 'chunk data',
            0x22: 'multi block change',
            0x23: 'block change',
            0x26: 'map chunk bulk',

            0x29: 'sound effect',
            0x2c: 'global entity (thunderbolt)',
            0x2f: 'set slot',
            0x30: 'window items',
            0x33: 'update sign',
            0x35: 'update block entity',

            0x37: 'statistics',
            0x38: 'player list entry',
            0x42: 'combat',
            0x44: 'world border',
        },
    },
}

class BotProtocol(ClientProtocol):

    def setup(self):
        self.spawned = False
        self.coords = [0, 0, 0]
        self.yaw = 0
        self.pitch = 0
        self.world = World()
        self.digging_block = None
        self.pathfind_path = None
        self.is_pathfinding = False

    ##### Helper functions #####

    def log_packet(self, prefix, packet_id):
        """ overrides default logging """
        if self.protocol_mode == 'play':
            prefix = prefix[2:]
            ignored = {
                    'send': [0x00, 0x01,
                        0x04, 0x05, 0x06, 0x07],
                    'recv': [0x00, 0x01, 0x02, 0x03, 0x04,
                        0x08, 0x09, 0x0a, 0x0b,
                        0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20,
                        0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
                        0x28, 0x29, 0x2a,
                        0x35, 0x37, 0x38,
                        0x40],
                    # [0x00, 0x02, 0x03, 0x0b, 0x0f, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1c, 0x20, 0x26, 0x29, 0x35, 0x37, 0x38, 0x40]
            }
            if packet_id not in ignored[prefix]:
                info = '' if packet_id not in packet_dict['play'][prefix] else packet_dict['play'][prefix][packet_id]
                print '%s %#02x %s' % (prefix, packet_id, info)

    def dig_block(self, *args):
        if len(args) < 3:
            print 'Not enough args for dig_block:', args
            return
        x, y, z = coords = map(int, args[:3])
        if self.digging_block is not None:
            print 'Already digging a block, aborting' # TODO queue?
            return
        if self.world.get(x, y, z, 'block_data') == 0:
            print 'Air cannot be dug, aborting'
            return
        # pick a face with an adjacent air block TODO any face seems to work, even if obstructed...
        faces = [(0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0)]
        for face, (dx, dy, dz) in enumerate(faces):
            if self.world.get(x+dx, y+dy, z+dz, 'block_data') == 0:
                break
        # remember this block to prevent digging a second one before this one is finished
        self.digging_block = coords
        self.send_player_digging(0, coords, face)
        self.send_player_digging(2, coords, face)

    def walk_one_block(self, direction):
        direction %= 4
        c = 0 if direction in (1, 3) else 2 # coordinate axis to move on
        d = 1 if direction in (1, 2) else -1 # how far to move
        self.coords[c] += d
        self.yaw = ((direction + 2) * 360 / 4) % 360
        self.pitch = 0
        self.send_player_position_and_look(self.coords, self.yaw, self.pitch)

    def pathfind(self, *args):
        """ Creates a path to the specified coordinates.
        By calling pathfind_continue() every 0.05s, the bot follows the path.
        The path gets updated in on_world_changed(). """
        if len(args) < 3:
            print 'Not enough args for pathfind:', args
            return
        target = args[:3]
        self.pathfind_path = astar(self.coords, target, self.world)
        if len(self.pathfind_path) <= 0:
            print 'No path found'
            self.pathfind_path = [target] # save for later
            self.is_pathfinding = False
        else:
            self.pathfind_path.pop(0) # skip starting position
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
            coord = self.pathfind_path.pop(0)
            self.send_player_position((coord[0]+0.5, coord[1], coord[2]+0.5)) # +0.5: center bot on block
            if len(self.pathfind_path) <= 0:
                self.pathfind_path = None
                self.is_pathfinding = False
            else:
                self.tasks.add_delay(0.05, self.pathfind_continue) # TODO test how fast the bot can go

    def on_command(self, cmd, *args):
        if cmd == '.path': self.pathfind(*args)
        if cmd == '.dig': self.dig_block(*args)
        elif cmd == '.n': self.walk_one_block(0)
        elif cmd == '.e': self.walk_one_block(1)
        elif cmd == '.s': self.walk_one_block(2)
        elif cmd == '.w': self.walk_one_block(3)

    def on_world_changed(self):
        if self.digging_block is not None:
            x, y, z = self.digging_block
            if self.world.get(x, y, z, 'block_data') == 0:
                self.digging_block = None
        if self.pathfind_path is not None and len(self.pathfind_path) > 0:
            # recalculate, blocks may have changed
            # TODO check if changed blocks are on path
            self.pathfind(*self.pathfind_path[-1])

    ##### Network: sending #####

    def send_player_position(self, coords = None, on_ground = True):
        if coords is not None: self.coords = coords
        self.send_packet(0x04, self.buff_type.pack('ddd?',
            self.coords[0],
            self.coords[1],
            self.coords[2],
            on_ground))

    def send_player_look(self, yaw = None, pitch = None, on_ground = True):
        if yaw is not None: self.yaw = self.yaw
        if pitch is not None: self.pitch = self.pitch
        self.send_packet(0x05, self.buff_type.pack('ff?',
            self.yaw,
            self.pitch,
            on_ground))

    def send_player_position_and_look(self, coords = None, yaw = None, pitch = None, on_ground = True):
        if coords is not None: self.coords = self.coords
        if yaw is not None: self.yaw = self.yaw
        if pitch is not None: self.pitch = self.pitch
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

    ##### Network: receiving #####

    @register("play", 0x02)
    def received_chat_message(self, buff):
        text = buff.unpack_chat()
        chat_type = buff.unpack('B')
        chat_type = ('Chat', 'System', 'AutoComplete')[chat_type]
        print '[%s] %s' % (chat_type, text)

        if self.spawned and chat_type == 'Chat':
            # get the words as a list
            text = str(text[:-1]).split(', ')[1].split(' ')
            self.on_command(*text)

    @register("play", 0x08)
    def received_player_position_and_look(self, buff):
        """ should only be sent on spawning and on motion error """
        coords = list(buff.unpack('ddd'))
        yaw = buff.unpack('f')
        pitch = buff.unpack('f')
        position_flags = buff.unpack('B')

        if position_flags & (1 << 0): coords[0] += self.coords[0]
        if position_flags & (1 << 1): coords[1] += self.coords[1]
        if position_flags & (1 << 2): coords[2] += self.coords[2]
        if position_flags & (1 << 3): pitch += self.pitch
        if position_flags & (1 << 4): yaw += self.yaw

        print 'position corrected:', coords

        self.coords = coords
        self.yaw = yaw
        self.pitch = pitch

        # send back player position and look
        self.send_packet(0x06, self.buff_type.pack('dddff?',
            self.coords[0],
            self.coords[1],
            self.coords[2],
            self.yaw,
            self.pitch,
            True))

        # if client just spawned, start sending position data to prevent timeout
        # TODO once per 30s, might skip when sent some other packet recently
        if not self.spawned:
            self.spawned = True
            self.tasks.add_loop(29, self.send_player_look)
            print 'spawned!'

        self.on_world_changed()

    @register("play", 0x21)
    def received_chunk_data(self, buff):
        chunk_coords = buff.unpack('ii')
        ground_up_continuous = buff.unpack('?')
        bitmask = buff.unpack('H')
        size = buff.unpack_varint()
        skylight = True # assume not in Nether TODO
        self.world.unpack(buff, chunk_coords, bitmask, ground_up_continuous, skylight)
        self.on_world_changed()

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
            self.world.put(x, y, z, 'block_data', data)
        self.on_world_changed()

    @register("play", 0x23)
    def received_block_change(self, buff):
        location = buff.unpack('Q') # long long, 64bit
        data = buff.unpack_varint()
        x = location >> 38
        y = (location >> 26) & 0xfff
        z = location & 0x3ffffff
        self.world.put(x, y, z, 'block_data', data)
        self.on_world_changed()

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
        self.on_world_changed()

    @register("play", 0x40)
    def received_disconnect(self, buff):
        reason = buff.unpack_string()

        print 'Disconnected: %s' % reason
        self.close()


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
