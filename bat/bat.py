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
				'PLAY<Open Window', 'PLAY<Close Window', 'PLAY<Window Items', 'PLAY<Window Property',
				'PLAY<Held Item Change', 'PLAY<Set Slot', 'PLAY<Confirm Transaction',
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
				'inv_open_window', 'inv_close_window', 'inv_win_prop', 'inv_clear_window',
				'inv_held_item_change', 'inv_set_slot',
				'inv_click_accepted', 'inv_click_not_accepted', 'inv_click_queue_cleared',
				):
			ploader.reg_event_handler(packet_name, self.debug_event)

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
				'tp coords',
				'tpb block_coords',
				'gravity',
				'dig coords',
				'place coords',
				'int interact_coords',
				'close',
				'select slot_index',
				'showhot',
				'drop slot=None, drop_stack=""',
				'plan',
				'hold item_id meta=-1',
				'hotbar *prepare_args',
				'path pathfind_coords',
				'clone c_from c_to c_target',
			):
			logger.info('    %s', cmd)

	@register_command('tp', '3')
	def tp(self, coords):
		pos = self.clinfo.position
		pos.x, pos.y, pos.z = map(float, coords)

	@register_command('tpb', '3')
	def tp_block(self, coords):
		pos = self.clinfo.position
		pos.x, pos.y, pos.z = map(lambda c: c + 0.5, block_coords(coords))
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
			'held_item': self.inventory.get_held_item().get_packet_data(),
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

	@register_command('showhot')
	def show_hotbar(self):
		self.show_hotbar_slotcounter = 0  # FIXME XXX TODO EVIL HACK
		def cb():
			self.inventory.select_slot(self.show_hotbar_slotcounter)
			self.show_hotbar_slotcounter += 1
		self.timer.reg_event_timer(0.5, cb, runs=8)

	@register_command('drop', '?1?s')
	def drop_item(self, slot=None, drop_stack=''):
		self.inventory.drop_item(slot, len(drop_stack) > 0)

	@register_command('plan')
	def print_plan(self):
		logger.info('plan cmd')
		logger.warn('TODO')

	@register_command('hold', '1?1')
	def hold_item(self, item_id, meta=-1):
		logger.debug('hold item %s:%s', item_id, meta)
		found_in = self.inventory.hold_item(item_id, meta)
		if found_in != '':
			logger.info('Found item %i:%i in %s', item_id, meta, found_in)
		else:
			logger.warn('Could not find item %i:%i', item_id, meta)

	@register_command('hotbar', '*1')
	def prepare_hotbar(self, *args):
		""" Puts items into the hotbar for quick access. """
		logger.warn('TODO')

	@register_command('path', '3')
	def pathfind(self, coords):
		logger.warn('TODO')

	@register_command('clone', '333')
	def clone_area(self, c_from, c_to, c_target):
		logger.warn('TODO')
