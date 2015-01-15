import os

from quarry.net.client import ClientFactory, ClientProtocol, register
from quarry.mojang.profile import Profile
from world import World

packet_dict = {
    'play': {
        'send': {
            0x05: 'player look',
            0x06: 'player position and look',
        },
        'recv': {
            0x00: 'keep alive',
            0x02: 'chat message',
            0x03: 'time update',
            0x06: 'player health',
            0x08: 'player position and look',
            0x1f: 'player experience',
            0x21: 'chunk data',
            0x22: 'multi block change',
            0x23: 'block change',
            0x26: 'map chunk bulk',
            0x2f: 'set slot',
            0x30: 'window items',
            0x33: 'update sign',
            0x35: 'update block entity',
            0x37: 'statistics',
            0x38: 'player list entry',
            0x44: 'world border',
        },
    },
}

def dump_chunk_data(buff, sort, chunk_coords, ground_up_continuous, bitmask):
    get_filename = lambda num: 'dump/chunk_%+02d:%+02d_%s_c%5s_%s_%d' % (chunk_coords[0], chunk_coords[1], sort, ground_up_continuous, bin(bitmask), num)
    counter = 0
    while os.path.exists(get_filename(counter)):
        counter += 1
    with open(get_filename(counter), 'wb') as f:
        f.write(buff.buff1)

class GjumBotProtocol(ClientProtocol):
    spawned = False

    def setup(self):
        self.coords = [0, 0, 0]
        self.yaw = 0
        self.pitch = 0
        self.world = World()

    def log_packet(self, prefix, packet_id):
        """ overrides default logging """
        if self.protocol_mode == 'play':
            if packet_id not in [0x00, 0x03, 0x0f, 0x19, 0x1c, 0x20, 0x35, 0x37, 0x38]:
                prefix = prefix[2:]
                info = '' if packet_id not in packet_dict['play'][prefix] else packet_dict['play'][prefix][packet_id]
                print '%s %#02x %s' % (prefix, packet_id, info)

    def rotate_player(self):
        self.yaw = (self.yaw + 5) % 360

        self.send_packet(0x05, self.buff_type.pack('ff?',
            self.yaw,
            self.pitch,
            True))

    @register("play", 0x02)
    def received_chat_message(self, buff):
        text = buff.unpack_chat()
        chat_position = buff.unpack('B') # 0=chat, 1=system-msg, 2=auto-complete

        print 'Chat: %i %s' % (chat_position, text)

    @register("play", 0x08)
    def received_player_position_and_look(self, buff):
        coords = list(buff.unpack('ddd'))
        yaw = buff.unpack('f')
        pitch = buff.unpack('f')
        position_flags = buff.unpack('B')

        if position_flags & (1 << 0): coords[0] += self.coords[0]
        if position_flags & (1 << 1): coords[1] += self.coords[1]
        if position_flags & (1 << 2): coords[2] += self.coords[2]
        if position_flags & (1 << 3): pitch += self.pitch
        if position_flags & (1 << 4): yaw += self.yaw

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

        # start rotating if client just spawned
        if not self.spawned:
            self.tasks.add_loop(1.0/20, self.rotate_player)
            self.spawned = True

    @register("play", 0x40)
    def received_disconnect(self, buff):
        reason = buff.unpack_string()

        print 'Disconnected: %s' % reason
        self.close()

    @register("play", 0x21)
    def received_chunk_data(self, buff):
        """ received single chunk """
        chunk_coords = buff.unpack('ii')
        ground_up_continuous = buff.unpack('?')
        bitmask = buff.unpack('H')
        size = buff.unpack_varint()
        dump_chunk_data(buff, 'data', chunk_coords, ground_up_continuous, bitmask)
        skylight = True # assume not in Nether TODO
        self.world.unpack(buff, chunk_coords, bitmask, ground_up_continuous, skylight)

    @register("play", 0x26)
    def received_map_chunk_bulk(self, buff):
        """ received multiple full chunks """
        packet_size = buff.length()
        dump_chunk_data(buff, 'all', (0, 0), 0, 0)
        skylight = buff.unpack('?')
        column_count = buff.unpack_varint()
        print 'received %d chunks, sky=%s' % (column_count, skylight)
        print '  bytes=%d, header=%d' % (buff.length(), packet_size - buff.length())
        ground_up_continuous = True # according to protocol, full chunks are sent
        chunk_coords = []
        bitmask = []
        # unpack all meta info before data
        for col in range(column_count):
            chunk_coords.append(buff.unpack('ii'))
            bitmask.append(buff.unpack('H'))
        for col in range(column_count):
            print col, 'of', column_count, # last ',' for no line break
            self.world.unpack(buff, chunk_coords[col], bitmask[col], ground_up_continuous, skylight)


class GjumBotFactory(ClientFactory):
    protocol = GjumBotProtocol


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
    factory = GjumBotFactory()
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
