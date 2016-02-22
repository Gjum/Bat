import logging

from bat.command import register_command
from spockbot.plugins.base import pl_announce, PluginBase
from spockbot.vector import Vector3


logger = logging.getLogger('spockbot')

reach_dist_sq = 4 * 4


@pl_announce('InteractCmd')
class InteractCommandsPlugin(PluginBase):
    requires = ('Commands', 'ClientInfo', 'Entities', 'Interact')

    def __init__(self, ploader, settings):
        super(InteractCommandsPlugin, self).__init__(ploader, settings)
        self.commands.register_handlers(self)
        ploader.provides('InteractCmd', self)

    @register_command('dig', '3')
    def dig_block(self, pos):
        self.interact.dig_block(Vector3(*pos).ifloor())

    @register_command('place', '3')
    def place_block(self, pos):
        self.interact.place_block(Vector3(*pos).ifloor())

    @register_command('use')
    def activate_item(self):
        self.interact.activate_item()

    @register_command('unuse')
    def deactivate_item(self):
        self.interact.deactivate_item()

    @register_command('open', '3')
    def open_block(self, pos):
        self.interact.click_block(Vector3(*pos).ifloor())

    @register_command('openinv')
    def open_inventory(self):
        self.interact.open_inventory()

    @register_command('action', '1')
    def entity_action(self, nr):
        self.interact._entity_action(nr)

    @register_command('ent', '?3')
    def interact_entity(self, pos=None):
        if pos is None:
            pos = self.clientinfo.eye_pos
        target_dist = Vector3(*pos).dist_sq

        nearest_dist = float('inf')
        nearest_ent = None
        for current_entity in self.entities.entities.values():
            # TODO check if entity can be interacted with
            try:
                current_pos = Vector3(current_entity)
            except AttributeError:  # has no position
                continue

            current_dist = target_dist(current_pos)
            if current_dist > reach_dist_sq:
                continue

            if nearest_dist > current_dist:
                nearest_dist = current_dist
                nearest_ent = current_entity

        if nearest_ent:
            self.interact.use_entity(nearest_ent)
            logger.debug('Clicked entity %s at %s',
                         nearest_ent.__class__.__name__, Vector3(nearest_ent))
        else:
            logger.warn('No entity near %s', pos)

    @register_command('sneak', '?1')
    def sneak(self, on=1):
        self.interact.sneak(bool(on))
