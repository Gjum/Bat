"""
TODO convenience functions/tasks:
- low-level: dig_block, place_block, select_slot, respawn, gravity
- high-level: hold_item, prepare_hotbar, pathfind, pickup_item_stack, clone
"""

from math import floor

import logging
logging.basicConfig(format='%(asctime)s %(levelname)-9s %(message)s', level=logging.DEBUG, datefmt='%H:%M:%S')
logger = logging.getLogger('spock')

def block_coords(*args):
	if len(args) == 1:
		coords = args[0] # argument is coords triple
	elif len(args) == 3:
		coords = args[:3] # arguments are x, y, z
	else: raise ValueError('Invalid args for block_coords: %s', args)
	return [int(floor(c)) for c in coords]

def reg_cmd(cmd):
	def inner(fnc):
		fnc._cmd_handler = cmd
		return fnc
	return inner


class BatPlugin:

	def __init__(self, ploader, settings):
		self.client_info = ploader.requires('ClientInfo')
		self.world = ploader.requires('World')

		ploader.reg_event_handler("LOGIN<Login Success", self.debug_event)

		ploader.reg_event_handler("cl_join_game", self.debug_event)
		ploader.reg_event_handler("cl_health_update", self.debug_event)
		ploader.reg_event_handler("w_block_update", self.debug_event)

		ploader.reg_event_handler("chat_pub", self.on_chat)
		ploader.reg_event_handler("chat_msg", self.on_chat)
		ploader.reg_event_handler("chat_say", self.on_chat)

		self.register_cmd_handlers()

	def register_cmd_handlers(self):
		self._cmd_handlers = {}
		for field_name in dir(self):
			handler = getattr(self, field_name)
			handled_cmd = getattr(handler, "_cmd_handler", None)
			if handled_cmd:
				self._cmd_handlers[handled_cmd] = getattr(self, field_name)
				logger.debug('Adding cmd handler %s for %s', field_name, handled_cmd)

	def debug_event(self, evt, data):
		logger.debug(str(data))

	def on_chat(self, evt, data):
		try:
			cmd, *args = data['text'].split(' ')
			cmd_handler = self._cmd_handlers[cmd]
			logger.info('[Command] <%s via %s> %s %s', data['name'], data['sort'], cmd, args)
			cmd_handler(*args)
		except (KeyError):
			#logger.warn('[Command] Unknown command %s', cmd)
			logger.info('[Chat] <%s via %s> %s', data['name'], data['sort'], data['text'])

	@reg_cmd('tp')
	def cmd_tp(self, *args):
		logger.info('tp cmd %s', args)
		pass

	@reg_cmd('gravity')
	def cmd_gravity(self, *args):
		pass

	@reg_cmd('dig')
	def cmd_dig(self, *args):
		pass

	@reg_cmd('place')
	def cmd_place(self, *args):
		pass

	@reg_cmd('select')
	def cmd_select(self, *args):
		pass

	@reg_cmd('plan')
	def cmd_plan(self, *args):
		pass

	@reg_cmd('hotbar')
	def cmd_hotbar(self, *args):
		pass

	@reg_cmd('hold')
	def cmd_hold(self, *args):
		pass

	@reg_cmd('path')
	def cmd_path(self, *args):
		pass

	@reg_cmd('clone')
	def cmd_clone(self, *args):
		pass


