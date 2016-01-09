# TODO this module is a deprecated mess
import logging
import traceback
from spockbot.plugins.base import PluginBase


logger = logging.getLogger('spockbot')


def register_command(cmd, arg_fmt=''):
    def inner(fnc):
        fnc._cmd_handler = (cmd, arg_fmt)
        return fnc
    return inner


class CommandRegistry:

    def __init__(self):
        self.cmd_handlers = {}

    def register_handlers(self, cls, prefix=''):
        for field_name in dir(cls):
            handler = getattr(cls, field_name)
            cmd, arg_fmt = getattr(handler, "_cmd_handler", (None, None))
            if cmd:
                cmd_with_prefix = '%s%s' % (prefix, cmd)
                handler = getattr(cls, field_name)
                self.cmd_handlers[cmd_with_prefix] = (handler, arg_fmt)


class CommandPlugin(PluginBase):
    requires = 'Entities'
    events = {
        'cmd': 'handle_cmd',
        'chat_incoming': 'handle_chat',
        'chat_outgoing': 'handle_chat',
        'chat_text': 'handle_chat',
    }

    def __init__(self, ploader, settings):
        super().__init__(ploader, settings)
        self.registry = CommandRegistry()
        ploader.provides('Commands', self.registry)

    def handle_cmd(self, evt, data):
        self.run_command(data['cmd'], data['args'])

    def handle_chat(self, evt, data):
        # TODO Can /tellraw send empty chat messages? Catch the exception.
        cmd, *args = data['message'].split(' ')
        self.run_command(cmd, args, data['uuid'])

    def run_command(self, cmd, args, uuid=None):
        if cmd not in self.registry.cmd_handlers:
            return
        handler, arg_fmt = self.registry.cmd_handlers[cmd]
        formatted_args = self.format_args(args, arg_fmt, uuid)
        if formatted_args is None:
            logger.warn('[Command] Illegal arguments for %s:'
                        ' expected %s, got %s',
                        cmd, arg_fmt, args)
        else:
            logger.debug('[Command] %s %s', cmd, formatted_args)
            try:
                handler(*formatted_args)
            except:
                logger.warn('[Command] %s %s failed: %s', cmd, formatted_args,
                            traceback.format_exc().strip())

    def format_args(self, args, arg_fmt, uuid):
        if arg_fmt == '*':  # raw args, parsed by handler
            return args

        def try_cast_num(str_arg):
            try:
                return int(str_arg)
            except ValueError:
                return float(str_arg)  # raise ValueError if still not casted

        optional = 0
        pos = 0
        out = []
        for c in arg_fmt:
            if c == 's':  # append single str
                if pos >= len(args):
                    if optional <= 0:
                        return None
                else:
                    out.append(args[pos])
                pos += 1
            elif '0' <= c <= '9':  # append number tuples
                tuple_size = int(c)
                try:
                    tuple_args = list(map(try_cast_num,
                                          args[pos:pos+tuple_size]))
                    out.append(tuple_args if len(tuple_args) > 1
                               else tuple_args[0])
                    pos += tuple_size
                except (ValueError, IndexError):
                    # could not cast int or float
                    if optional > 0:
                        optional -= 1
                        pos += 1
                    else:  # not optional, but wrong type
                        return None
            elif c == '?':  # append next if present
                optional += 1
            elif c == 'e':  # player entity that executed the command
                if uuid:
                    uuid = uuid.replace('-', '')
                    for player_entity in self.entities.players.values():
                        if uuid == '%032x' % player_entity.uuid:
                            out.append(player_entity)
                            break
                    else:
                        if optional <= 0:
                            return None
                else:  # not executed by a player
                    if optional <= 0:
                        logger.warn(
                            '[Command] No sender: not executed by player')
                        return None
            else:
                logger.error('[Command] Unknown format: %s in %s at %i',
                             c, arg_fmt, pos)
        return out
