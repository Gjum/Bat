from math import floor
from bat.command import CommandRegistry, register_command
from spock.utils import Vec3
import logging
logger = logging.getLogger('spock')

def block_coords(*args):
	if len(args) == 1:
		coords = args[0] # argument is coords triple
	elif len(args) == 3:
		coords = args[:3] # arguments are x, y, z
	else: raise ValueError('Invalid args for block_coords: %s', args)
	return [int(floor(c)) for c in coords]

class BatPlugin:

	def __init__(self, ploader, settings):
		for packet_name in (
				"LOGIN<Login Success", "PLAY<Spawn Player",
				# 'PLAY<Open Window', 'PLAY<Close Window', 'PLAY<Window Property',
				'PLAY<Held Item Change', 'PLAY<Confirm Transaction',
				# 'PLAY<Window Items', 'PLAY<Set Slot',
				'PLAY>Click Window',
				):
			ploader.reg_event_handler(packet_name, self.debug_event)

		self.clinfo = ploader.requires('ClientInfo')
		self.inventory = ploader.requires('Inventory')
		self.net = ploader.requires('Net')
		self.timer = ploader.requires('Timers')
		self.world = ploader.requires('World')
		self.command_handler = CommandRegistry(self)

		for event_name in ('pub', 'msg', 'say'):
			ploader.reg_event_handler('chat_%s' % event_name, self.on_chat)

		for packet_name in (
				"cl_join_game", "cl_health_update", "w_block_update",
				'inv_open_window', 'inv_close_window', 'inv_win_prop',
				'inv_held_item_change',
				'inv_set_slot',
				'inv_click_accepted', 'inv_click_not_accepted', 'inv_click_queue_cleared',
				):
			ploader.reg_event_handler(packet_name, self.debug_event)

		self.ploader = ploader

	@staticmethod
	def debug_event(evt, data):
		data = getattr(data, 'data', data)
		logger.debug('%s: %s', evt, data)

	def on_chat(self, evt, data):
		if not self.command_handler.on_chat(data):
			logger.info('[Chat] <%s via %s> %s', data['name'], data['sort'], data['text'])

	@register_command('help')
	def help(self):
		logger.info('Available commands:')
		for cmd in (
				'plan',
				'gravity',
				'tp coords',
				'tpb block_coords',
				'path pathfind_coords',

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
	def tp_block(self, block_coords):
		pos = self.clinfo.position
		pos.x, pos.y, pos.z = map(lambda c: c + 0.5, block_coords(block_coords))
		pos.y -= 0.5

	@register_command('gravity')
	def gravity(self):
		logger.warn('TODO')

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
	def place_block(self, coords):
		packet = {
			'location': Vec3(*coords).get_dict(),
			'direction': 1,
			'held_item': self.inventory.get_held_item().get_dict(),
			'cur_pos_x': 8,
			'cur_pos_y': 8,
			'cur_pos_z': 8,
		}
		self.net.push_packet('PLAY>Player Block Placement', packet)

	@register_command('int', '3')
	def interact(self, coords):
		self.inventory.interact_with_block(Vec3(*coords))

	@register_command('close')
	def close_window(self):
		self.inventory.close_window()

	@register_command('select', '1')
	def select_slot(self, slot_index):
		self.inventory.select_slot(slot_index)

	@register_command('showinv')
	def show_inventory(self):
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

	@register_command('drops', '1?s')
	def drop_slot(self, slot=None, drop_stack='n'):
		if type(slot) is str:  # bad argument parsing
			logger.debug('argh')
			drop_stack = slot
			slot = None
		self.inventory.drop_item(slot, 'n' not in drop_stack)

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
