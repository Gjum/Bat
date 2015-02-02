"""

This module provides a simple world manager that makes use of the Minecraft SMP packet format internally.

Originally written by Barney Gale, see
https://github.com/barneygale/smpmap/blob/fe62cd8bb7adf15501956b68534c228c8e5b2847/smpmap.py

"""

import array
import struct
import zlib

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class BiomeData:
    """ A 16x16 byte array stored in each ChunkColumn """

    def __init__(self):
        self.length = 16 * 16
        self.data = None

    def fill(self):
        if not self.data:
            self.data = array.array('B', [0] * self.length)

    def unpack(self, buff):
        self.data = array.array('B', buff.unpack_raw(self.length))

    def pack(self):
        return self.data.tobytes()

    def get(self, x, z):
        self.fill()
        return self.data[x + z * 16]

    def put(self, x, z, data):
        self.fill()
        self.data[x + z * 16] = data


class ChunkData:
    """ A 16x16x16 unsigned short array for storing block IDs """

    def __init__(self):
        self.length = 16 * 16 * 16
        self.data = None

    def fill(self):
        if not self.data:
            self.data = array.array('H', [0] * self.length)

    def unpack(self, buff):
        self.data = array.array('H', buff.unpack_raw(self.length * 2)) # H = short, *2 byte per short

    def pack(self):
        self.fill()
        return self.data.tobytes()

    def get(self, x, y, z):
        self.fill()
        return self.data[x + ((y * 16) + z) * 16]

    def put(self, x, y, z, data):
        self.fill()
        self.data[x + ((y * 16) + z) * 16] = data


class ChunkDataNibble:
    """ A 16x16x8 unsigned char array for storing metadata, light or additional data
    Each array element contains two 4-bit elements. """

    def __init__(self):
        self.length = 16 * 16 * 8
        self.data = None

    def fill(self):
        if not self.data:
            self.data = array.array('B', [0] * self.length)

    def unpack(self, buff):
        self.data = array.array('B', buff.unpack_raw(self.length))

    def pack(self):
        self.fill()
        return self.data.tobytes()

    def get(self, x, y, z):
        self.fill()
        x, r = divmod(x, 2)
        i = x + ((y * 16) + z) * 16

        if r == 0:
            return self.data[i] >> 4
        else:
            return self.data[i] & 0x0F

    def put(self, x, y, z, data):
        self.fill()
        x, r = divmod(x, 2)
        i = x + ((y * 16) + z) * 16

        if r == 0:
            self.data[i] = (self.data[i] & 0x0F) | ((data & 0x0F) << 4)
        else:
            self.data[i] = (self.data[i] & 0xF0) | (data & 0x0F)


class ChunkSection(dict):
    """ Collates the various data arrays """

    def __init__(self, **kwargs):
        super(ChunkSection, self).__init__(**kwargs)
        self['block_data'] = ChunkData()
        self['light_block'] = ChunkDataNibble()
        self['light_sky'] = ChunkDataNibble()


class ChunkColumn:
    """ Initialised chunk sections are a ChunkSection, otherwise None """

    def __init__(self):
        self.sections = [None]*16
        self.biome  = BiomeData()

    def unpack(self, buff, bitmask, has_biome, has_skylight):
        # in the protocol, all arrays of the same data are packed sequentially
        # (i.e. attributes pertaining to the same chunk are *not* grouped)
        self.unpack_data_array(buff, 'block_data',  bitmask)
        self.unpack_data_array(buff, 'light_block', bitmask)
        if has_skylight:
            self.unpack_data_array(buff, 'light_sky', bitmask)
        if has_biome:
            self.biome.unpack(buff)

    def unpack_data_array(self, buff, section, bitmask):
        # iterate over the bitmask
        for i in range(16):
            if bitmask & (1 << i):
                if self.sections[i] is None:
                    self.sections[i] = ChunkSection()
                self.sections[i][section].unpack(buff)


class World:
    """ A bunch of ChunkColumns """

    def __init__(self):
        self.columns = {} # chunk columns are addressed by a tuple (x, z)

    def get_block(self, coords):
        """ Get the block's ID and meta """
        data = self.get_block_raw(coords)
        id = data >> 4
        meta = data & 0xf
        return id, meta

    def has_collision(self, coords):
        """ Does the block have a collision box? """
        id_below = self.get_block((coords[0], coords[1]-1, coords[2]))[0]
        # fence/gate below?
        if id_below in (85, 107, 113): return True
        if id_below in range(183, 193): return True
        # no air?
        return self.get_block(coords)[0] != 0

    def unpack(self, buff, coords, bitmask, ground_up_continuous, has_skylight=True):
        """ Unpack one column from the buffer """
        # grab/create relevant chunk column
        if coords in self.columns:
            column = self.columns[coords]
        else:
            column = self.columns[coords] = ChunkColumn()

        # unpack chunk column data
        column.unpack(buff, bitmask, ground_up_continuous, has_skylight)

    def get_block_raw(self, coords):
        """ Returns the block ID and meta in one value, should get split by get_block """
        if coords[1] < 0 or coords[1] > 255: # outside the world, vertically
            return 0

        x, rx = divmod(int(coords[0]), 16)
        y, ry = divmod(int(coords[1]), 16)
        z, rz = divmod(int(coords[2]), 16)

        if not (x, z) in self.columns:
            return 0

        chunk = self.columns[(x, z)].sections[y]
        if chunk is None:
            return 0

        return chunk['block_data'].get(rx, ry, rz)

    def set_block(self, coords, data):
        """ Updates the block ID and meta in one value """
        if coords[1] < 0 or coords[1] > 255: # outside the world, vertically
            return

        x, rx = divmod(int(coords[0]), 16)
        y, ry = divmod(int(coords[1]), 16)
        z, rz = divmod(int(coords[2]), 16)

        if (x, z) in self.columns:
            column = self.columns[(x, z)]
        else:
            column = self.columns[(x, z)] = ChunkColumn()

        chunk = column.sections[y]
        if chunk is None:
            chunk = column.sections[y] = ChunkSection()

        chunk['block_data'].put(rx, ry, rz, data)

    def get_biome(self, chunk_coords):
        x, rx = divmod(int(chunk_coords[0]), 16)
        z, rz = divmod(int(chunk_coords[1]), 16)

        if (x, z) not in self.columns:
            return 0

        return self.columns[(x, z)].biome.get(rx, rz)

    def set_biome(self, chunk_coords, data):
        x, rx = divmod(int(chunk_coords[0]), 16)
        z, rz = divmod(int(chunk_coords[1]), 16)

        if (x, z) in self.columns:
            column = self.columns[(x, z)]
        else:
            column = self.columns[(x, z)] = ChunkColumn()

        return column.biome.put(rx, rz, data)


if __name__ == '__main__':
    world = World()
    with open('packet0x38.bin', 'rb') as f:
        #Strip off the packet ID
        assert f.read(1) == '\x38'

        #Unpack the rest of the packet
        world.unpack(f)
    print "Got %d columns" % len(world.columns)
