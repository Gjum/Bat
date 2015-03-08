from collections import deque
from math import floor, sqrt
from spock.plugins.helpers.entities import MovementEntity
from bat.command import CommandRegistry, register_command
from spock.utils import Vec3
import logging
logger = logging.getLogger('spock')

class Vec:
	def __init__(self, *args):
		self.set(*args)

	def __repr__(self):
		return 'Vec(%s)' % str(self.c)

	def set(self, *args):
		first_arg = args[0]
		if isinstance(first_arg, Vec):
			self.c = first_arg.c
		elif hasattr(first_arg, 'x') and hasattr(first_arg, 'y') and hasattr(first_arg, 'z'):
			self.c = [first_arg.x, first_arg.y, first_arg.z]
		elif isinstance(first_arg, list) or isinstance(first_arg, tuple):
			self.c = first_arg  # argument is coords triple
		elif len(args) == 3:
			self.c = args[:3]  # arguments are x, y, z
		else:
			raise ValueError('Invalid args for block_coords: %s', args)
		return self

	def add(self, *args):
		d = Vec(*args)
		self.c = [c + d for c, d in zip(self.c, d.c)]
		return self

	def sub(self, *args):
		d = Vec(*args)
		self.c = [c-d for c,d in zip(self.c, d.c)]
		return self

	def round(self):
		self.c = [int(floor(c)) for c in self.c]
		return self

	def center(self):
		return self.round().add(.5, .0, .5)

	def dist_sq(self):
		x, y, z = self.c
		return x*x + y*y + z*z

	def x(self):
		return self.c[0]

	def y(self):
		return self.c[1]

	def z(self):
		return self.c[2]

	def override_vec3(self, v3):
		v3.x, v3.y, v3.z = self.c
		return v3

class BatPlugin:

	def __init__(self, ploader, settings):
		for packet_name in (
				'LOGIN<Login Success', 'PLAY<Spawn Player', 'PLAY<Player Position and Look',
				'PLAY<Window Property', 'PLAY>Click Window',
				):
			ploader.reg_event_handler(packet_name, self.debug_event)

		self.ploader = ploader
		self.path_queue = deque()

		self.clinfo = ploader.requires('ClientInfo')
		self.entities = ploader.requires('Entities')
		self.inventory = ploader.requires('Inventory')
		self.net = ploader.requires('Net')
		self.timer = ploader.requires('Timers')
		self.world = ploader.requires('World')
		self.commands = ploader.requires('Commands')
		self.commands.register_handlers(self)

		ploader.reg_event_handler('chat_any', self.handle_chat)

		ploader.reg_event_handler('PLAY>Player Position', self.on_send_position)
		self.pos_update_counter = 0

		for packet_name in (
				'cl_join_game', 'cl_health_update', #'w_block_update',
				'inv_open_window', 'inv_close_window', 'inv_win_prop',
				'inv_held_item_change',
				'inv_set_slot',
				'inv_click_accepted', 'inv_click_not_accepted', 'inv_click_queue_cleared',
				):
			ploader.reg_event_handler(packet_name, self.debug_event)

	def debug_event(self, evt, data):
		data = getattr(data, 'data', data)
		logger.debug('%s: %s', evt, data)

	def handle_chat(self, evt, data):
		logger.info('[Chat] <%s via %s> %s', data['name'], data['sort'], data['text'])

	def on_send_position(self, evt, data):
		self.pos_update_counter += 1
		if self.pos_update_counter > 20:
			self.apply_gravity()
			self.pos_update_counter = 0

	@register_command('help')
	def help(self):
		logger.info('Available commands:')
		for cmd in (
				'plan',
				'gravity',
				'tp coords',
				'tpb block_coords',
				'path pathfind_coords',
				'tpd delta_xyz',
				'warp coords',
				'come',

				'dig coords',
				'place coords',
				'clone c_from c_to c_target',

				'int interact_coords',
				'close',

				'showinv',
				'showhot',
				'select slot_index',
				'hotbar *prepare_args',

				'click slot',
				'hold item_id meta=-1',
				'drop item_id meta=-1 amount=1',
				'drops slot=None drop_stack="n"',
			):
			logger.info('    %s', cmd)

	@register_command('tp', '3')
	def tp(self, coords):
		pos = self.clinfo.position
		pos.x, pos.y, pos.z = map(float, coords)

	@register_command('tpb', '3')
	def tp_block(self, coords):
		Vec(coords).center().override_vec3(self.clinfo.position)

	@register_command('tpd', '3')
	def tp_delta(self, deltas):
		self.clinfo.position.add_vector(*deltas)

	@register_command('warp', '3')
	def warp_to(self, coords):
		self.tp_delta((0, 100, 0))
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())
		self.tp_block((coords[0], 200, coords[2]))
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())
		self.tp_block(coords)
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())

	@register_command('come', 'e')
	def tp_to_player(self, player):
		self.warp_to(Vec(player).c)

	@register_command('gravity')
	def apply_gravity(self):
		def can_stand_on(vec):
			block_id, meta = self.world.get_block(*vec.c)
			return 0 != block_id  # TODO do a proper collision test
		pos = self.clinfo.position
		below = Vec(pos).round().add(0, -1, 0)
		if can_stand_on(below):
			return  # already on ground
		for dy in range(below.y()):
			block_pos = Vec(below).add(0, -dy, 0)
			if can_stand_on(block_pos):
				block_pos.add(0, 1, 0).center().override_vec3(pos)
				logger.debug('[Gravity] Corrected to y=%.2f', pos.y)
				break

	@register_command('dig', '3')
	def dig_block(self, coords):
		packet = {
			'status': 0,  # start
			'location': Vec3(*coords).get_dict(),
			'face': 1,
		}
		self.net.push_packet('PLAY>Player Digging', packet)
		packet['status'] = 2  # finish
		self.net.push_packet('PLAY>Player Digging', packet)

	@register_command('place', '3')
	def place_block(self, coords=None, vec=None):
		if vec is None: vec = Vec3(*Vec(coords).round().c)
		self.inventory.interact_with_block(vec)

	@register_command('int', '?3')
	def interact_at(self, coords=None):
		vec = Vec(self.clinfo.position) if coords is None else Vec(coords)
		entity = None
		e_dist = float('inf')
		for e in self.entities.entities.values():
			if not isinstance(e, MovementEntity): continue
			dist = vec.sub(e).dist_sq()
			if dist < e_dist:
				entity = e
				e_dist = dist
		if entity is None:
			logger.warn('[Interact] Could not find any entity to interact, placing block')
			block_coords = vec.round().c
			if 0 != self.world.get_block(*block_coords)[0]:
				self.inventory.interact_with_block(*block_coords)
		else:
			dist_from_client_sq = Vec(entity).sub(self.clinfo.position).dist_sq()
			if dist_from_client_sq > 4*4:
				logger.warn('[Interact] Out of reach: %i units away', sqrt(dist_from_client_sq))
			self.inventory.interact_with_entity(entity.eid)

	@register_command('close')
	def close_window(self):
		self.inventory.close_window()

	@register_command('select', '1')
	def select_slot(self, slot_index):
		self.inventory.select_slot(slot_index)

	@register_command('showinv')
	def show_inventory(self, *args):
		nice_slot = lambda s: '    --    ' if s.amount <= 0 else '%2ix %3i:%-2i' % (s.amount, s.item_id, s.damage)
		nice_slots = lambda slots: ' '.join(nice_slot(s) for s in slots)
		window = self.inventory.window
		logger.info('window: %s', nice_slots(window.window_slots()))
		for line in range(3):
			i = 9 * line
			logger.info('inv: %2i %s', i+window.inventory_index(), nice_slots(window.inventory_slots()[i:i+9]))
		logger.info('hotbar: %s', nice_slots(window.hotbar_slots()))
		logger.info('cursor: %s', nice_slot(self.inventory.cursor_slot))

	@register_command('showhot')
	def show_hotbar(self):
		self.show_hotbar_slotcounter = 0  # FIXME XXX TODO EVIL HACK
		def cb():
			self.inventory.select_slot(self.show_hotbar_slotcounter % 9)
			self.show_hotbar_slotcounter += 1
		self.timer.reg_event_timer(0.5, cb, runs=10)

	@register_command('drops', '?1?s')
	def drop_slot(self, slot=None, drop_stack='n'):
		if type(slot) is str:  # bad argument parsing
			logger.debug('argh')
			drop_stack = slot
			slot = None
		drop_stack = 'n' not in drop_stack
		logger.debug('Dropping: %s %s', slot, drop_stack)
		self.inventory.drop_item(slot, drop_stack)

	@register_command('drop', '1?1?1')
	def drop_item(self, item_id, meta=-1, amount=1):
		logger.debug('[drop handler] Dropping %ix %i:%i', amount, item_id, meta)
		class Closure:
			def __init__(self, parent, amount):
				self.parent = parent
				self.amount = amount
				self.dropped_slot = None

			def handler(self, evt=None, data={'slot_nr': None}):
				if self.dropped_slot is not None and self.dropped_slot != data['slot_nr']:
					logger.debug('[drop handler] Not my slot')
					return  # ignore
				slot = self.parent.inventory.find_item(item_id, meta)
				if slot is False:
					logger.debug('[drop handler] All available dropped')
					return True  # nothing to drop left, cancel
				self.amount -= self.parent.inventory.window.slots[slot].amount
				self.parent.inventory.drop_item(slot, True)
				self.dropped_slot = slot
				if self.amount <= 0:
					logger.debug('[drop handler] All wanted dropped')
					return True  # done, delete handler

		handler = Closure(self, amount).handler
		if not handler():
			self.ploader.reg_event_handler('inv_set_slot', handler)

	@register_command('plan')
	def print_plan(self):
		logger.warn('TODO')

	@register_command('click', '1')
	def click_slot(self, slot):
		self.inventory.click_slot(slot)

	@register_command('use')
	def use_item(self):
		packet = {
			'location': {'x':-1, 'y':255, 'z':-1},
			'direction': -1,
			'held_item': self.inventory.get_held_item().get_dict(),
			'cur_pos_x': -1,
			'cur_pos_y': -1,
			'cur_pos_z': -1,
		}
		self.net.push_packet('PLAY>Player Block Placement', packet)

	@register_command('hold', '1?1')
	def hold_item(self, item_id, meta=-1):
		logger.debug('hold: %s %s', type(item_id), type(meta))
		logger.debug('hold item %s:%s', item_id, meta)
		found = self.inventory.hold_item(item_id, meta)
		if found:
			logger.info('Found item %i:%i', item_id, meta)
		else:
			logger.warn('Could not find item %i:%i', item_id, meta)

	@register_command('hotbar', '*')
	def prepare_hotbar(self, *prepare_args):
		""" Puts items into the hotbar for quick access. """
		logger.warn('TODO')

	@register_command('path', '3')
	def pathfind(self, coords):
		logger.warn('TODO')

	@register_command('clone', '333')
	def clone_area(self, c_from, c_to, c_target):
		logger.warn('TODO')
