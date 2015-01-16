import os

from quarry.net.client import ClientFactory, ClientProtocol, register
from quarry.mojang.profile import Profile
from world import World
from ai import astar

# 0b 42 1a 12

packet_dict = {
    'play': {
        'send': {
            0x04: 'player position',
            0x05: 'player look',
            0x06: 'player position and look',
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

    ##### Helper functions #####

    def log_packet(self, prefix, packet_id):
        """ overrides default logging """
        if self.protocol_mode == 'play':
            if packet_id not in [0x00, 0x02, 0x03, 0x0f, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1c, 0x20, 0x26, 0x35, 0x37, 0x38, 0x40]:
                prefix = prefix[2:]
                info = '' if packet_id not in packet_dict['play'][prefix] else packet_dict['play'][prefix][packet_id]
                print '%s %#02x %s' % (prefix, packet_id, info)

    def walk_one_block(self, direction=None):
        if direction is not None: self.direction = direction
        self.direction %= 4
        c = 0 if self.direction in (1, 3) else 2 # coordinate axis to move on
        d = 1 if self.direction in (1, 2) else -1 # how far to move
        self.coords[c] += d
        self.yaw = ((self.direction + 2) * 360 / 4) % 360
        self.pitch = 0
        self.send_player_position_and_look(self.coords, self.yaw, self.pitch)

    def pathfind(self, *args):
        print 'Finding path from %s to %s' % (self.coords, args[:3])
        path = astar(self.coords, args[:3], self.world)
        print 'A* path:', path

    def on_command(self, cmd, *args):
        if cmd == '.path': self.pathfind(*args)
        elif cmd == '.n': self.walk_one_block(0)
        elif cmd == '.e': self.walk_one_block(1)
        elif cmd == '.s': self.walk_one_block(2)
        elif cmd == '.w': self.walk_one_block(3)

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

    @register("play", 0x21)
    def received_chunk_data(self, buff):
        """ received single chunk """
        chunk_coords = buff.unpack('ii')
        ground_up_continuous = buff.unpack('?')
        bitmask = buff.unpack('H')
        size = buff.unpack_varint()
        skylight = True # assume not in Nether TODO
        self.world.unpack(buff, chunk_coords, bitmask, ground_up_continuous, skylight)

    @register("play", 0x26)
    def received_map_chunk_bulk(self, buff):
        """ received multiple full chunks """
        skylight = buff.unpack('?')
        column_count = buff.unpack_varint()
        ground_up_continuous = True # according to protocol, full chunks are sent
        chunk_coords = []
        bitmask = []
        # unpack all meta info before data
        for col in range(column_count):
            chunk_coords.append(buff.unpack('ii'))
            bitmask.append(buff.unpack('H'))
        for col in range(column_count):
            self.world.unpack(buff, chunk_coords[col], bitmask[col], ground_up_continuous, skylight)

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
