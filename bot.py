import random

from quarry.net.client import ClientFactory
from quarry.mojang.profile import Profile
from botProtocol import BotProtocol
from astar import astar
from info import item_or_block


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
        x, y, z = coords = map(int, args[:3])
        if self.digging_block is not None:
            self.logger.warn('[dig_block] Already digging at %s - aborting', self.digging_block) # IDEA queue?
            return
        dx, dy, dz = (c - a for c, a in zip(self.coords, coords))
        if 4*4 < dx*dx + dy*dy + dz*dz:
            self.logger.warn('[dig_block] Block too far away - aborting')
            return
        if self.world.get_block(coords) == 0:
            self.logger.warn('[dig_block] Air cannot be dug - aborting')
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
            self.logger.warn('Not enough args for place_block: %s', args)
            return
        self.send_player_block_placement(args[:3])

    def hold_item(self, *args):
        """Places a stack of the specified wanted_item_id in the hotbar and selects it"""
        if len(args) < 1:
            self.logger.warn('[Hold item] Not enough args: %s', args)
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
        self.logger.warn('[Hold item] %s (%s) not found in inventory', item_or_block(wanted_item_id)['name'], wanted_item_id)
        return

    def select_slot(self, *args):
        if len(args) < 1:
            self.logger.warn('Not enough args for select_slot: %s', args)
            return
        self.send_select_slot(int(args[0]))
        self.send_player_position()

    def pickup_item_stack(self, eid):
        if eid not in self.entities:
            self.logger.warn('[Item pickup] Could not pick up %i - already removed', eid)
            return
        self.logger.info('[Item pickup] Picking up %i', eid)
        self.pathfind(*self.entities[eid].coords)

    @staticmethod
    def center_and_jitter(coords):
        # 0.5: center on block, jitter by 0.2 (player apothem minus a bit)
        coords[0] += 0.5 + 0.2 * (1 - 2*random.random())
        coords[2] += 0.5 + 0.2 * (1 - 2*random.random())
        return coords

    @staticmethod
    def get_yaw_from_movement_delta(delta):
        """ For rectangular delta, return yaw [0..360); otherwise return 0 """
        if delta[0] < 0: return  90
        if delta[2] < 0: return 180
        if delta[0] > 0: return 270
        return 0

    def walk_one_block(self, direction):
        direction %= 4
        old_coords = [int(c) for c in self.coords]
        coords = old_coords[:]
        c = 0 if direction in (1, 3) else 2 # coordinate axis to move on
        d = 1 if direction in (1, 2) else -1 # how far to move
        coords[c] += d
        coords = self.center_and_jitter(coords)
        yaw = self.get_yaw_from_movement_delta([int(n) - int(o) for n, o in zip(coords, old_coords)])
        self.send_player_position_and_look(coords, yaw, 0)
        self.send_player_look(yaw, 0)

    def pathfind(self, *args):
        """ Creates a path to the specified coordinates.
        By calling pathfind_continue() every 0.05s, the bot follows the path.
        The path gets updated by on_world_changed(). """
        if len(args) < 3:
            self.logger.warn('[Pathfinding] Not enough args: %s', args)
            return
        target = args[:3]
        self.logger.info('[Pathfinding] Finding path to %s...', target)
        try:
            self.pathfind_path = astar(self.coords, target, self.world)
        except ValueError:
            self.logger.warn('[Pathfinding] Invalid args: %s', args)
            return
        if len(self.pathfind_path) <= 0:
            self.logger.warn('[Pathfinding] No path found')
            self.pathfind_path = [target] # save for later
            self.is_pathfinding = False
        else:
            self.pathfind_path.pop(0) # skip starting position
            self.logger.info('[Pathfinding] Path found: %i blocks long', len(self.pathfind_path))
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
            coords = self.center_and_jitter(list(self.pathfind_path.pop(0)))
            delta = [int(n) - int(o) for o, n in zip(self.coords, coords)] # direction bot is walking in
            yaw = self.get_yaw_from_movement_delta(delta)
            self.send_player_position_and_look(coords, yaw, 0)
            self.send_player_look(yaw, 0)
            if len(self.pathfind_path) <= 0:
                self.pathfind_path = None
                self.is_pathfinding = False
            else:
                self.tasks.add_delay(0.05, self.pathfind_continue) # IDEA test how fast the bot can go

    def respawn(self):
        self.logger.warn('Respawning')
        self.send_status(0)

    ##### Events #####

    def on_chat(self, chat_type, text):
        if self.spawned and ', ' in text:
            # get the words/args as a list
            text = str(text[:-1]).split(', ')[1].split(' ')
            cmd, args = text[0], text[1:]
            self.logger.debug('[Command] %s %s', cmd, args)
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
        else:
            chat_type = ('Chat', 'System', 'AutoComplete')[chat_type]
            self.logger.info('[%s] %s', chat_type, text)

    def on_spawn_object(self, eid):
        #pass # TODO do something
        if self.entities[eid].e_type == 2: # item stack
            # maybe pick up later
            def cont(self, eid):
                dist = sum(map(lambda (e,p): abs(e-p), zip(self.entities[eid].coords, self.coords)))
                if dist < 30:
                    self.pickup_item_stack(eid)
            self.tasks.add_delay(2.05, cont, self, eid) # wait two seconds and a tick

    def on_position_changed(self, old):
        self.on_world_changed() # TODO affects pathfinding and digging

    def on_world_changed(self, how='somehow'):
        #self.logger.debug('[world changed] %s', how)
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
