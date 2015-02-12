
import logging
logger = logging.getLogger('spock')

def register_command(cmd, arg_fmt=''):
	def inner(fnc):
		fnc._cmd_handler = (cmd, arg_fmt)
		return fnc
	return inner

def _format_args(args, arg_fmt):
	pos = 0
	out = []
	try:
		for c in arg_fmt:
			if c == '1': # append single
				out.append(args[pos])
				pos += 1
			elif c == '3': # append triple
				out.append(args[pos:pos+3])
				pos += 3
			elif c == '?': # append one if present
				if pos < len(args):
					out.append(args[pos])
					pos += 1
			elif c == '*': # append any args left
				out.extend(args[pos:])
				pos = len(args)
			if pos > len(args):
				logger.error('too many args: %s, %i of %i', arg_fmt, pos, len(args))
				return None
		return out
	except IndexError: # arguments do not match format
		logger.error('index error: %s, %i of %i', arg_fmt, pos, len(args))
		return None

class CommandRegistry:
	""" Class to register commands.
	Call on_chat() on chat events to check for a command. """

	def __init__(self, cls):
		self._cmd_handlers = {}
		for field_name in dir(cls):
			handler = getattr(cls, field_name)
			cmd, arg_fmt = getattr(handler, "_cmd_handler", (None, None))
			if cmd:
				handler = getattr(cls, field_name)
				self._cmd_handlers[cmd] = (handler, arg_fmt)

	def on_chat(self, data):
		""" Check for commands in the chat message.
		Returns True if a command was handled (successful or not), False otherwise. """
		cmd, *args = data['text'].split(' ') # TODO Can /tellraw send empty chat messages? Catch the exception.
		if cmd not in self._cmd_handlers:
			return False
		handler, arg_fmt = self._cmd_handlers[cmd]
		formatted_args = _format_args(args, arg_fmt)
		if formatted_args is None:
			logger.warn('[Command] <%s via %s> Illegal arguments for %s: %s', data['name'], data['sort'], cmd, args)
		else:
			logger.debug('[Command] <%s via %s> %s %s', data['name'], data['sort'], cmd, formatted_args)
			handler(*formatted_args)
		return True
