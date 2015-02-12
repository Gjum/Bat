
import logging
logger = logging.getLogger('spock')

def register_command(cmd, arg_fmt=''):
	def inner(fnc):
		fnc._cmd_handler = (cmd, arg_fmt)
		return fnc
	return inner

def _format_args(args, arg_fmt):
	def try_cast_num(str_arg):
		try:
			return int(str_arg)
		except ValueError:
			return float(str_arg)  # raise ValueError if still not casted
	optional = 0
	pos = 0
	out = []
	try:
		for c in arg_fmt:
			if c == 's':  # append single str
				out.append(args[pos])
				pos += 1
			elif '0' <= c <= '9':  # append numbers
				tuple_size = int(c)
				try:
					tuple_args = list(map(try_cast_num, args[pos:pos+tuple_size]))
				except ValueError:  # could not cast int or float
					if optional > 0:
						optional -= 1
					else:  # not optional, but wrong type
						return None
				else:  # args successfully casted
					out.append(tuple_args if len(tuple_args) > 1 else tuple_args[0])
					pos += tuple_size
			elif c == '?':  # append next if present
				optional += 1
			elif c == '*':  # append any args of same type left
				optional = len(args)
			else:
				logger.error('[Command] Unknown format: %s in %s', c, arg_fmt)
		return out
	except IndexError:  # arguments do not match format
		return None

class CommandRegistry:
	""" Class to register commands.
	Call on_chat() on chat events to check for a command. """

	def __init__(self, cls, prefix=''):
		self.prefix = prefix
		self._cmd_handlers = {}
		for field_name in dir(cls):
			handler = getattr(cls, field_name)
			cmd, arg_fmt = getattr(handler, "_cmd_handler", (None, None))
			if cmd:
				cmd_with_prefix = '%s%s' % (prefix, cmd)
				handler = getattr(cls, field_name)
				self._cmd_handlers[cmd_with_prefix] = (handler, arg_fmt)

	def on_chat(self, data):
		""" Check for commands in the chat message.
		Returns True if a command was handled (successful or not), False otherwise. """
		cmd, *args = data['text'].split(' ') # TODO Can /tellraw send empty chat messages? Catch the exception.
		if cmd not in self._cmd_handlers:
			return False
		handler, arg_fmt = self._cmd_handlers[cmd]
		formatted_args = _format_args(args, arg_fmt)
		if formatted_args is None:
			logger.warn('[Command] <%s via %s> Illegal arguments for %s: expected %s, got %s', data['name'], data['sort'], cmd, arg_fmt, args)
		else:
			logger.info('[Command] <%s via %s> %s %s', data['name'], data['sort'], cmd, formatted_args)
			handler(*formatted_args)
		return True
