from collections import deque
from math import floor, sqrt, asin, acos, pi
from spock.mcmap import mapdata
from spock.plugins.helpers.entities import MovementEntity, PlayerEntity, ClientPlayerEntity
from bat.command import register_command
import logging
logger = logging.getLogger('spock')

class Vec:
	def __init__(self, *args):
		self.set(*args)

	def __repr__(self):
		return 'Vec(%s)' % str(self.c)

	def get_dict(self):
		return {'x': self.c[0], 'y': self.c[1], 'z': self.c[2]}

	def set(self, *args):
		if len(args) == 0:
			args = [(0,0,0)]
		first_arg = args[0]
		if isinstance(first_arg, Vec):
			self.c = first_arg.c[:]
		elif hasattr(first_arg, 'x') and hasattr(first_arg, 'y') and hasattr(first_arg, 'z'):
			self.c = [first_arg.x, first_arg.y, first_arg.z]
		elif isinstance(first_arg, list) or isinstance(first_arg, tuple):
			self.c = first_arg[:3]  # argument is coords triple
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

	def dist_sq(self, other=None):
		v = Vec(other).sub(self) if other else self
		x, y, z = v.c
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
				'PLAY<Entity Relative Move',
				'PLAY<Entity Look And Relative Move',
				'PLAY<Entity Teleport',
				):
			ploader.reg_event_handler(packet_name, self.on_entity_move)

		for packet_name in (
				'cl_join_game', 'cl_health_update', #'w_block_update',
				'inv_open_window', 'inv_close_window', 'inv_win_prop',
				'inv_held_item_change',
				'inv_set_slot',
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

	def on_entity_move(self, evt, data):
		eid = data.data['eid']
		if eid in self.entities.players:
			self.look_entity()  # looks at nearest player

	@register_command('help')
	def help(self):
		logger.info('Some available commands:')
		for cmd in (
				'plan',
				'gravity',
				'tp coords',
				'tpb block_coords',
				'tpd delta_xyz',
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

	@register_command('tpb', '3')
	def tp_block(self, coords):
		self.teleport(Vec(coords).center())

	@register_command('tpd', '3')
	def tp_delta(self, deltas):
		self.teleport(Vec(self.clinfo.position).add(deltas))

	@register_command('tp', '3')
	def teleport(self, coords):
		pos = Vec(coords)
		Vec(self.clinfo.position).add(0, 300, 0).override_vec3(self.clinfo.position)
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())
		Vec(pos).add(0, 300, 0).override_vec3(self.clinfo.position)
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())
		pos.override_vec3(self.clinfo.position)
		self.net.push_packet('PLAY>Player Position', self.clinfo.position.get_dict())

	@register_command('come', '?e')
	def tp_to_player(self, player=None):
		if player is None:
			logger.warn('[Come] No player to teleport to')
		else:
			self.teleport(Vec(player).c)

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

	def look_rel(self, vec):
		l, _, w = vec.c
		c = sqrt(l*l + w*w)
		try:
			alpha1 = -asin(l/c) / pi * 180
			alpha2 =  acos(w/c) / pi * 180
		except ZeroDivisionError:
			pass
		else:
			if alpha2 > 90:
				yaw = 180 - alpha1
			else:
				yaw = alpha1
			pitch = 0
			self.net.push_packet('PLAY>Player Look', {
				'yaw': yaw,
				'pitch': pitch,
				'on_ground': self.clinfo.position.on_ground
			})

	def look_pos(self, pos):
		self.look_rel(Vec(pos).sub(self.clinfo.position))

	def look_entity(self, eid=None):
		"""
		Looks at the entity.
		If no `eid` is given, looks at the nearest player in range.
		"""
		look_pos = None
		if eid and eid in self.entities.entities:
			try:
				look_pos = Vec(self.entities.entities[eid])
			except ValueError:
				pass
		else:  # no eid, look at nearest player in range
			player = self.find_nearest_entity(max_dist=8, test=lambda e: isinstance(e, PlayerEntity))
			look_pos = Vec(player) if player else None
		if look_pos:
			self.look_pos(look_pos)

	def find_nearest_entity(self, search_pos=None, max_dist=4, test=None):
		search_pos = Vec(search_pos if search_pos else self.clinfo.position)
		max_dist_sq = max_dist**2 if max_dist else float('inf')
		nearest_entity = None
		nearest_dist_sq = max_dist_sq
		for entity in self.entities.entities.values():
			# look at all entities that are not the bot itself and pass the test
			if not isinstance(entity, ClientPlayerEntity) \
					and (test is None or test(entity)):
				try:
					entity_pos = Vec(entity)
				except ValueError:  # entity has no position
					continue
				else:
					dist_sq = entity_pos.dist_sq(search_pos)
					if dist_sq < nearest_dist_sq:
						nearest_dist_sq = dist_sq
						nearest_entity = entity
		return nearest_entity

	def interact_entity(self, coords=None, attack=False):
		vec = Vec(self.clinfo.position) if coords is None else Vec(coords)
		reach_dist = 4
		entity = self.find_nearest_entity(vec, reach_dist, test=lambda e: isinstance(e, MovementEntity))
		if entity:
			action = 1 if attack else 0
			self.net.push_packet('PLAY>Use Entity', {'target': entity.eid, 'action': action})
		return entity

	@register_command('look', '?e')
	def look_player(self, player):
		self.look_pos(Vec(player).c)

	@register_command('dig', '3')
	def dig_block(self, coords):
		packet = {
			'status': 0,  # start
			'location': Vec(*coords).get_dict(),
			'face': 1,
		}
		self.net.push_packet('PLAY>Player Digging', packet)
		packet['status'] = 2  # finish
		self.net.push_packet('PLAY>Player Digging', packet)

	@register_command('place', '3')
	def place_block(self, coords=None, vec=None):
		if vec is None: vec = Vec(coords).round()
		self.inventory.interact_with_block(vec)

	@register_command('int', '?3')
	def interact_at(self, coords=None):
		"""
		Tries to interact with an entity near the given coordinates
		or near the client itself.
		If none is found, tries to interact with the block there.
		"""
		entity = self.interact_entity(coords)
		if entity:
			logger.info('[Interact] Found entity at %s', Vec(entity).c)
		elif coords:
			block_coords = Vec(coords).round().c
			logger.info('[Interact] Found no entity at %s, clicking block', block_coords)
			if 0 != self.world.get_block(*block_coords)[0]:
				self.inventory.interact_with_block(*block_coords)

	@register_command('hit', '?3')
	def attack_entity(self, coords=None):
		entity = self.interact_entity(coords, True)
		if entity:
			logger.info('[Hit] Hit entity at %s', Vec(entity).c)
		else:
			logger.warn('[Hit] No entity found near %s', coords)

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
				if slot is None:
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
		center = Vec(self.clinfo.position)
		blocks = set() # will contain all present blocks for convenient lookup
		msg = ''
		for z in range(-5, 6, 1):
			msg += '\n'
			for x in range(-5, 6, 1):
				block_id, meta = self.world.get_block(*Vec(x, -1, z).add(center).c)
				blocks.add((block_id, meta))
				if block_id == 0:
					msg += '       '
				elif meta == 0:
					msg += '%3i    ' % block_id
				else:
					msg += '%3i:%-2i ' % (block_id, meta)
				if x == z == 0:  # mark bot position with [$blockID]
					msg = msg[:-8] + '[%s]' % msg[-7:-1]
		for block_id, meta in blocks:  # print names of all present blocks for convenient lookup
			if block_id != 0:
				print('%3i: %s' % (block_id, mapdata.get_block(block_id, meta).display_name))
		print(msg)

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

	@register_command('clone', '333')
	def clone_area(self, c_from, c_to, c_target):
		logger.warn('TODO')

	@register_command('preset')
	def path_reset(self):
		self.path_queue = deque()

	@register_command('pgo')
	def path_go(self):
		if len(self.path_queue) > 0:
			self.tp_block(self.path_queue.popleft())
			self.timer.reg_event_timer(1, self.path_go, runs=1)

	@register_command('padd', '3')
	def path_add(self, coords):
		self.path_queue.append(coords)

	@register_command('pade', '3')
	def path_add_delta(self, delta):
		if len(self.path_queue) > 0:
			pos = self.path_queue[-1]
		else:
			pos = self.clinfo.position
			pos = [pos.x, pos.y, pos.z]
		coords = [c+d for c, d in zip(pos, delta)]
		self.path_queue.append(coords)
		logger.debug('appending to path: %s', str(coords))
