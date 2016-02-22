import logging
import random

from spockbot.mcdata.constants import PLAYER_EYE_HEIGHT
from spockbot.plugins.base import pl_announce, PluginBase
from spockbot.plugins.tools.task import TaskFailed
from spockbot.vector import Vector3


logger = logging.getLogger('spockbot')

reach_dist_sq = 4 * 4


@pl_announce('Survival')
class SurvivalPlugin(PluginBase):
    requires = ('Event', 'Timers',
                'ClientInfo', 'Entities', 'Interact', 'Inventory')

    events = {'event_tick': 'on_event_tick'}
    events.update({e: 'on_entity_move' for e in (
        'PLAY<Entity Relative Move',
        'PLAY<Entity Look And Relative Move',
        'PLAY<Entity Teleport',
    )})

    def __init__(self, ploader, settings):
        super(SurvivalPlugin, self).__init__(ploader, settings)
        ploader.provides('Survival', self)

        self.aggro = False
        self.max_entities = 500  # log out if there are more loaded than this

        self.nearest_player = None
        self.checked_entities_this_tick = False

        self.taskmanager.run_task(self.eat_task())

    def on_event_tick(self, *args):
        self.checked_entities_this_tick = False

        if len(self.entities.entities) > self.max_entities:
            logger.warn('Too many entities loaded (%s), bye!',
                        len(self.entities.entities))
            self.event.kill()

    def on_entity_move(self, evt, packet):
        eid = packet.data['eid']
        entity = self.entities.entities[eid]
        dist_sq = self.clientinfo.position.dist_sq

        # look at nearby players
        if eid in self.entities.players:
            entity_head = Vector3(entity).iadd((0, PLAYER_EYE_HEIGHT, 0))
            if id(entity) == id(self.nearest_player):
                self.interact.look_at(entity_head)
            elif self.nearest_player is None:
                self.nearest_player = entity
                self.interact.look_at(entity_head)
            else:
                if dist_sq(entity_head) < dist_sq(Vector3(self.nearest_player)):
                    self.nearest_player = entity
                    self.interact.look_at(entity_head)

        # force field
        # runs max. one per tick, but only when there are moving entities
        if self.aggro and not self.checked_entities_this_tick:
            for entity in self.entities.mobs.values():
                if reach_dist_sq > dist_sq(Vector3(entity)):
                    self.interact.attack_entity(entity)
            self.checked_entities_this_tick = True

        if self.follow_eid and eid == self.follow_eid:
            self.teleport(Vector3(entity))

    def eat_task(self):

        def timeout(t, other_events):
            timer_event = 'eat_timeout_%s' % random.random

            def cb(*_):
                self.event.emit(timer_event, {})

            self.timers.reg_event_timer(t, cb, runs=1)
            event, _ = yield timer_event, other_events
            if event == timer_event:
                raise TaskFailed('Timed out after %s' % t)

        while 1:
            yield 'cl_health_update'

            health = self.clientinfo.health.health
            food = self.clientinfo.health.food

            def inv_has(item):
                return self.inventory.find_slot(item)

            def eat_item(item):
                yield timeout(2, self.inventory.async.hold_item(364))
                self.interact.activate_item()
                yield timeout(2, 'inventory_set_slot')

            can_eat = food < 20
            cannot_regen = food <= 16
            cannot_sprint = food <= 6
            starving = food <= 0
            eat_steak = food <= 10 and inv_has(364)
            eat_chicken = food <= 14 and inv_has(366) and not inv_has(364)
            should_heal = health < 19 and cannot_regen

            if should_heal or eat_chicken or eat_steak:
                try:
                    logger.info('Eating...')
                    try:
                        yield timeout(2, self.inventory.async.hold_item(364))
                    except TaskFailed:
                        yield timeout(2, self.inventory.async.hold_item(366))

                    self.interact.activate_item()
                    yield timeout(2, 'inventory_set_slot')

                except TaskFailed as e:
                    logger.error('Could not eat fast enough: %s' % e.args[0])
            elif starving:
                logger.warn("I'm starving, bye!")
                self.event.kill()  # disconnect
