
from math import floor
from bat.command import CommandRegistry, register_command

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
		self.clinfo = ploader.requires('ClientInfo')
		self.inventory = ploader.requires('Inventory')
		self.world = ploader.requires('World')
		self.command_handler = CommandRegistry(self)

		ploader.reg_event_handler("LOGIN<Login Success", self.debug_event)

		ploader.reg_event_handler("cl_join_game", self.debug_event)
		ploader.reg_event_handler("cl_health_update", self.debug_event)
		ploader.reg_event_handler("w_block_update", self.debug_event)

		for sort in ('pub', 'msg', 'say'):
			ploader.reg_event_handler('chat_%s' % sort, self.on_chat)

	@staticmethod
	def debug_event(evt, data):
		data = getattr(data, 'data', data)
		logger.debug(str(data))

	def on_chat(self, evt, data):
		if not self.command_handler.on_chat(data):
			logger.info('[Chat] <%s via %s> %s', data['name'], data['sort'], data['text'])

	@register_command('tp', '3')
	def tp(self, coords):
		self.clinfo.set_position(coords)

	@register_command('tpb', '3')
	def tp_block(self, coords):
		self.clinfo.set_position(block_coords(coords))

	@register_command('gravity')
	def gravity(self):
		logger.warn('TODO')

	@register_command('dig', '3')
	def dig(self, coords):
		logger.warn('TODO')

	@register_command('place', '3')
	def place(self, coords):
		logger.warn('TODO')

	@register_command('select', '1')
	def select_slot(self, slot_index):
		self.inventory.select_slot(slot_index)

	@register_command('plan')
	def print_plan(self):
		logger.info('plan cmd')
		logger.warn('TODO')

	@register_command('hold', '1?')
	def hold_item(self, id, meta=-1):
		if self.inventory.hold_item(id, meta):
			logger.info('Found item %i:%i')
		else:
			logger.warn('Could not find item %i:%i')

	@register_command('hotbar', '1*')
	def prepare_hotbar(self, *args):
		""" Puts items into the hotbar for quick access. """
		logger.warn('TODO')

	@register_command('path', '3')
	def pathfind(self, coords):
		logger.warn('TODO')

	@register_command('clone', '333')
	def clone_area(self, c_from, c_to, c_target):
		logger.warn('TODO')
