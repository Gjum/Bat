import logging

from spockbot.mcdata import blocks
from spockbot.plugins.base import pl_announce, PluginBase
from spockbot.plugins.tools.event import EVENT_UNREGISTER
from spockbot.vector import Vector3


logger = logging.getLogger('spockbot')


@pl_announce('BlockFinder')
class BlockFinderPlugin(PluginBase):
    requires = ('Event', 'ClientInfo', 'World')

    def __init__(self, ploader, settings):
        super(BlockFinderPlugin, self).__init__(ploader, settings)
        ploader.provides('BlockFinder', self)
        # TODO store results and running searches

    def print_plan(self, dy=0):
        center = self.clientinfo.position.floor()
        visible_blocks = set()
        msg = ''
        for dz in range(-5, 6, 1):
            msg += '\n'
            for dx in range(-5, 6, 1):
                block_pos = Vector3(dx, dy, dz).iadd(center)
                block_id, meta = self.world.get_block(*block_pos)
                visible_blocks.add((block_id, meta))

                if block_id == 0:
                    msg += '       '
                elif meta == 0:
                    msg += '%3i    ' % block_id
                else:
                    msg += '%3i:%-2i ' % (block_id, meta)

                if dx == dz == 0:  # mark bot position with brackets: [123:45]
                    msg = msg[:-8] + ('[%s]' % msg[-7:-1])

        for block_id, meta in sorted(visible_blocks):
            if block_id != 0:
                display_name = blocks.get_block(block_id, meta).display_name
                logger.info('%3i:%-2i %s', block_id, meta, display_name)
        logger.info(msg)

    def find_blocks(self, b_id, b_meta=None, stop_at=10, min_y=0, max_y=256):
        # TODO make this a task or emit events

        prefix = '[Find Blocks][%s:%s]' % (b_id, b_meta)
        found = 0
        block_gen = self.iter_blocks(b_id, b_meta, min_y, max_y)

        def find_next(*args):
            nonlocal found
            chunks_this_tick = 0
            while chunks_this_tick < 100:  # look at 100 chunks per event_tick
                chunks_this_tick += 1
                try:
                    found_block = next(block_gen)
                except StopIteration:
                    logger.info('%s Done, found all %i', prefix, found)
                    return EVENT_UNREGISTER
                if found_block is None:  # another chunk searched, ...
                    return  # continue search in next tick
                (x, y, z), (found_id, found_meta) = found_block
                logger.info('%s Found %s:%s at (%i %i %i)',
                            prefix, found_id, found_meta, x, y, z)
                found += 1
                # also continue search if negative stop_at
                if stop_at - found == 0:
                    logger.info('%s Done, found %i of them', prefix, found)
                    return EVENT_UNREGISTER

        self.event.reg_event_handler('event_tick', find_next)

    def iter_blocks(self, ids, metas=None, min_y=0, max_y=256):
        """
        Generates tuples of found blocks in the loaded world.
        Tuple format: ((x, y, z), (id, meta))
        Also generates None to indicate that another column (16*16*256 blocks)
        has been searched. You can use this for pausing between chunk columns.
        `ids` and `metas` can be single values.
        """
        pos = self.clientinfo.position
        # ensure correct types
        if isinstance(ids, int):
            ids = [ids]

        if metas is None:
            metas = []
        elif isinstance(metas, int):
            metas = [metas]

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
                        block_y = i // 256
                        y = block_y + 16 * cy
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
