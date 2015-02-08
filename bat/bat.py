
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
		self.client_info = ploader.requires('ClientInfo')
		self.world = ploader.requires('World')
		self.command_handler = CommandRegistry(self)

		ploader.reg_event_handler("LOGIN<Login Success", self.debug_event)

		ploader.reg_event_handler("cl_join_game", self.debug_event)
		ploader.reg_event_handler("cl_health_update", self.debug_event)
		ploader.reg_event_handler("w_block_update", self.debug_event)

		for sort in ('pub', 'msg', 'say'):
			ploader.reg_event_handler('chat_%s' % sort, self.on_chat)

	def debug_event(self, evt, data):
		logger.debug(str(data))

	def on_chat(self, evt, data):
		if not self.command_handler.on_chat(data):
			logger.info('[Chat] <%s via %s> %s', data['name'], data['sort'], data['text'])

	@register_command('tp', '3')
	def tp(self, coords):
		logger.info('tp cmd %s', coords)
		pass

	@register_command('gravity')
	def gravity(self):
		pass

	@register_command('dig', '3')
	def dig(self, coords):
		pass

	@register_command('place', '3')
	def place(self, coords):
		pass

	@register_command('select', '1')
	def select(self, slot_index):
		pass

	@register_command('plan')
	def plan(self):
		logger.info('plan cmd')
		pass

	@register_command('hotbar', '1*')
	def hotbar(self, *args):
		""" Puts items into the hotbar for quick access. """
		pass

	@register_command('hold', '1?')
	def hold(self, id, meta=0):
		pass

	@register_command('path', '3')
	def path(self, coords):
		pass

	@register_command('clone', '333')
	def clone(self, c_from, c_to, c_target):
		pass

