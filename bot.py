from quarry.net.client import ClientFactory
from quarry.mojang.profile import Profile
from botProtocol import BotProtocol
from astar import astar
from coordinates import block_coords, add_coords, sub_coords, center_and_jitter
from info import item_or_block, block_dict


class Bot(BotProtocol):

    def setup(self):
        super(Bot, self).setup()
        self.digging_block = None
        self.pathfind_path = None
        self.is_pathfinding = False

    ##### Helper functions #####

    def dig_block(self, *args):
        if len(args) < 3:
            self.logger.warn('[dig_block] Not enough args: %s', args)
            return
        x, y, z = coords = block_coords(args[:3])
        if self.digging_block is not None:
            self.logger.warn('[dig_block] Already digging at %s - aborting', self.digging_block) # IDEA queue?
            return
        dx, dy, dz = (c - a for c, a in zip(self.coords, coords))
        if 4*4 < dx*dx + dy*dy + dz*dz:
            self.logger.warn('[dig_block] Block too far away - aborting')
            return
        if self.world.get_block(coords)[0] == 0:
            self.logger.warn('[dig_block] Air cannot be dug - aborting')
            return
        # pick a face with an adjacent air block TODO any face seems to work, even if obstructed
        face = 0
        #faces = [(0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0)]
        #for face, (dx, dy, dz) in enumerate(faces):
        #    if not self.world.has_collision((x+dx, y+dy, z+dz)):
        #        break
        # remember this block to prevent digging a second one before this one is finished
        self.digging_block = coords
        self.send_player_digging(0, coords, face) # start digging and ...
        self.send_player_digging(2, coords, face) # ... immediately stop, server sends block update when done
        # IDEA look at the block

    def place_block(self, *args):
        """ Places the selected block (in the hotbar) at the specified coordinates """
        if len(args) < 3:
            self.logger.warn('Not enough args for place_block: %s', args)
            return
        self.send_player_block_placement(args[:3])

    def hold_item(self, *args):
        """Places a stack of the specified wanted_item_id in the hotbar and selects it"""
        if len(args) < 1:
            self.logger.warn('[Hold item] Not enough args: %s', args)
            return
        wanted_item_id = int(args[0])
        wanted_item_meta = int(args[1]) if len(args) > 1 else None

        def matchs(id, meta):
            if wanted_item_meta is not None and meta != wanted_item_meta:
                return False
            return id == wanted_item_id

        slot = self.window_handler.get_hotbar()[self.selected_slot]
        if matchs(slot.item_id, slot.damage):
            return # wanted item already selected

        # not selected, search for it
        slot_with_item = -1 # last slot with wanted item
        # hotbar is at the end of the inventory, search there first
        for slot_nr, slot in enumerate(self.window_handler.get_hotbar()):
            if matchs(slot.item_id, slot.damage):
                self.logger.info('[Hold item] %s (%s) found, selecting', item_or_block(wanted_item_id)['name'], wanted_item_id)
                self.select_slot(slot_nr)
                return

        for slot_nr, slot in enumerate(self.window_handler[0].slots):
            if matchs(slot.item_id, slot.damage):
                # num-swap into hotbar
                # window_id = 0, button = selected_slot, mode = 2
                self.logger.info('[Hold item] %s (%s) found, swapping', item_or_block(wanted_item_id)['name'], wanted_item_id)
                self.send_click_window(0, slot_nr, self.selected_slot,
                        self.window_handler.next_action_id(), 2, slot)
                return

        self.logger.warn('[Hold item] %s (%s) not found in inventory', item_or_block(wanted_item_id)['name'], wanted_item_id)
        return

    def select_slot(self, *args):
        if len(args) < 1:
            self.logger.warn('Not enough args for select_slot: %s', args)
            return
        self.send_select_slot(int(args[0]))

    def pickup_item_stack(self, eid):
        if eid not in self.entities:
            self.logger.warn('[Item pickup] Could not pick up %i - already removed', eid)
            return
        self.logger.info('[Item pickup] Picking up %i', eid)
        self.pathfind(block_coords(self.entities[eid].coords))

    @staticmethod
    def get_yaw_from_movement_delta(delta):
        """ For rectangular delta, return yaw [0..360); otherwise return 0 """
        if delta[0] < 0: return  90
        if delta[2] < 0: return 180
        if delta[0] > 0: return 270
        return 0

    def walk_one_block(self, direction):
        direction %= 4
        old_coords = block_coords(self.coords)
        coords = old_coords[:]
        c = 0 if direction in (1, 3) else 2 # coordinate axis to move on
        d = 1 if direction in (1, 2) else -1 # how far to move
        coords[c] += d
        yaw = self.get_yaw_from_movement_delta(sub_coords(coords, old_coords))
        self.send_player_position_and_look(self.center_and_jitter(coords), yaw, 0)
        self.send_player_look(yaw, 0)

    def pathfind(self, target):
        """ Creates a path to the specified coordinates.
        By calling pathfind_continue() every 0.05s, the bot follows the path.
        The path gets updated by on_world_changed(). """
        self.logger.info('[Pathfinding] Finding path to %s...', target)
        self.pathfind_path = astar(block_coords(self.coords), target, self.world)
        if len(self.pathfind_path) <= 0:
            self.logger.warn('[Pathfinding] No path found')
            self.pathfind_path = [target] # save for later
            self.is_pathfinding = False
        else:
            self.pathfind_path.pop(0) # skip starting position
            self.logger.info('[Pathfinding] Path found: %i blocks long', len(self.pathfind_path))
            if len(self.pathfind_path) == 0:
                return # already there
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
            coords = self.pathfind_path.pop(0)
            yaw = self.get_yaw_from_movement_delta(sub_coords(coords, block_coords(self.coords)))
            self.send_player_position_and_look(center_and_jitter(coords), yaw, 0)
            self.send_player_look(yaw, 0)
            if len(self.pathfind_path) <= 0:
                self.pathfind_path = None
                self.is_pathfinding = False
            else:
                self.tasks.add_delay(0.05, self.pathfind_continue) # IDEA test how fast the bot can go

    def respawn(self):
        self.logger.warn('Respawning')
        self.send_status(0)

    def gravity(self):
        x, y, z = block_coords(self.coords)
        for y in reversed(range(int(y))):
            if self.world.has_collision([x, y, z]):
                self.send_player_position([x, y+1, z])
                return

    def clone(self, froma, fromb, to):
        froma, fromb, to = map(block_coords, (froma, fromb, to))
        print 'cloning', froma, fromb, to
        for y in range(froma[1], fromb[1]+1):
            for z in range(froma[2], fromb[2]+1):
                for x in range(froma[0], fromb[0]+1):
                    id, meta = self.world.get_block((x, y, z))
                    if id == 0: continue
                    new_coords = add_coords(sub_coords((x, y, z), froma), to)
                    if self.world.get_block(new_coords)[0] != 0:
                        continue
                    self.hold_item(id, meta)
                    self.place_block(*new_coords)

    ##### Events #####

    def on_chat(self, chat_type, text):
        if 'Ulexos' in text: # TODO REMOVE
            return
        if self.spawned and ', ' in text:
            # get the words/args as a list
            try:
                text = str(text[:-1].split(', ')[-1]).split(' ')
            except:
                self.logger.debug('[Chat %s] %s', chat_type, text)
                return # no command
            cmd, args = text[0], text[1:]
            self.logger.debug('[Command] %s %s', cmd, args)
            if cmd == 'path': self.pathfind(block_coords(args[:3]))
            elif cmd == 'tp': self.send_player_position(args[:3])
            elif cmd == 'dig': self.dig_block(*args)
            elif cmd == 'place': self.place_block(*args)
            elif cmd == 'hold': self.hold_item(*args)
            elif cmd == 'select': self.select_slot(*args)
            elif cmd == 'gravity': self.gravity()
            elif cmd == 'clone': self.clone(args[:3], args[3:6], args[6:9])
            elif cmd == 'plan':
                blocks = set() # will contain all present blocks for convenient lookup
                msg = 'Plan _______________________________________'
                for z in range(-5, 6, 1):
                    msg += '\n'
                    for x in range(-5, 6, 1):
                        block = self.world.get_block(add_coords([x, -1, z], block_coords(self.coords)))[0]
                        blocks.add(block)
                        msg += ('%3i ' % block) if block != 0 else '    '
                        if x == z == 0: # mark bot position with [$blockID]
                            msg = msg[:-5] + '[%s]' % msg[-4:-1]
                for block in blocks: # print names of all present blocks for convenient lookup
                    if block != 0:
                        print '%3i: %s' % (block, block_dict[block]['name'])
                print msg
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
                print '    gravity'
                print '    plan'
                print '    n e s w'
        else:
            chat_type = ('Chat', 'System', 'AutoComplete')[chat_type]
            self.logger.info('[%s] %s', chat_type, text)

    def on_update_health(self):
        self.logger.info('health: %i, food: %i, saturation: %i', self.health, self.food, self.saturation)
        if self.health <= 6 or self.food <= 6:
            print 'Low health/food, exiting'
            sys.exit(0)

    def on_spawn_object(self, eid):
        #pass # TODO do something
        if self.entities[eid].e_type == 2: # item stack
            # maybe pick up later
            def cont(self, eid):
                if not eid in self.entities: return # item already removed
                dist = sum(map(lambda (e,p): abs(e-p), zip(self.entities[eid].coords, self.coords)))
                if dist < 30:
                    self.pickup_item_stack(eid)
            self.tasks.add_delay(2.05, cont, self, eid) # wait two seconds and a tick

    def on_position_changed(self, old):
        class Chatter: # quick-and-dirty way to log to the chat
            old = self.logger
            def chat(_, *msg):
                if len(msg) == 1:
                    self.send_chat(msg[0])
                else:
                    self.send_chat(msg[0] % msg[1:])
            def debug(self, *msg):
                self.old.debug(*msg)
            info = chat
            warn = chat

        self.logger = Chatter()
        self.logger.warn('Pos corrected from %s to %s', ['%.2f' % c for c in old], ['%.2f' % c for c in self.coords])
        self.on_world_changed('position') # TODO affects pathfinding and digging

    def on_world_changed(self, how='somehow'):
        #self.logger.debug('[world changed] %s', how)
        if self.digging_block is not None:
            if self.world.get_block(self.digging_block)[0] == 0:
                self.digging_block = None # done digging, block is now air
        if self.pathfind_path is not None and len(self.pathfind_path) > 0:
            # TODO check if changed blocks are on path or otherwise reduce frequency on packet bulk
            for coords in self.pathfind_path:
                if True:
                    break
            else:
                # recalculate, blocks may have changed
                self.pathfind(self.pathfind_path[-1])


def main(args):
    # Parse options
    if len(args) < 4:
        print 'usage: %s <connect-host> <connect-port> <username> [password]' % args[0]
        return 0
    host, port, username = args[1:4]
    password = args[4] if len(args) > 4 else None

    # Create profile
    profile = Profile()

    class BotFactory(ClientFactory):
        protocol = Bot

    # Create factory
    factory = BotFactory()
    factory.profile = profile
    factory.connect(host, int(port))

    # login
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
