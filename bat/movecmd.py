import logging
from collections import deque

from spockbot.plugins.base import pl_announce, PluginBase
from spockbot.vector import Vector3

from bat.command import register_command


logger = logging.getLogger('spockbot')


@pl_announce('MoveCmd')
class MovementCommandsPlugin(PluginBase):
    requires = ('Timers', 'ClientInfo', 'Entities', 'Commands')

    def __init__(self, ploader, settings):
        super(MovementCommandsPlugin, self).__init__(ploader, settings)
        self.commands.register_handlers(self)
        ploader.provides('MoveCmd', self)

        self.path_queue = deque()
        self.follow_eid = None  # should be uuid, eid can get reused

    def on_entity_move(self, evt, packet):
        eid = packet.data['eid']
        if self.follow_eid and eid == self.follow_eid:
            self.teleport(Vector3(self.entities.entities[eid]))

    @register_command('tpb', '3')
    def tp_block(self, coords):
        self.teleport(Vector3(*coords).ifloor().iadd(.5, 0, .5))

    @register_command('tpd', '3')
    def tp_delta(self, deltas):
        self.teleport(Vector3(*deltas).iadd(self.clientinfo.position))

    @register_command('tp', '3')
    def teleport(self, coords):
        self.clientinfo.position.init(*coords)

    @register_command('come', '?e')
    def tp_to_player(self, player=None):
        if player is None:
            logger.warn('[Come] No player to teleport to')
        else:
            self.teleport(Vector3(player))

    @register_command('follow', 'e')
    def follow_player(self, player):
        self.follow_eid = player.eid

    @register_command('unfollow')
    def unfollow_player(self):
        self.follow_eid = None

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
            pos = Vector3(self.path_queue[-1])
        else:
            pos = self.clientinfo.position
        self.path_queue.append(pos + delta)
