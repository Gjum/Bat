import logging
import traceback

from spockbot.plugins.base import pl_announce, PluginBase


logger = logging.getLogger('spockbot')


def by(key, data_list):
    if len(data_list) <= 0:
        return []
    if isinstance(data_list, dict):
        data_list = list(data_list.values())
    first = data_list[0]
    if isinstance(first, dict):
        return [e[key] for e in data_list]
    if hasattr(first, key):
        return [getattr(e, key) for e in data_list]


@pl_announce('PyCmd')
class PyCmdPlugin(PluginBase):
    events = {
        'cmd_exec': 'cmd_exec',
        'cmd_eval': 'cmd_eval',
    }

    def __init__(self, ploader, settings):
        super(PyCmdPlugin, self).__init__(ploader, settings)
        ploader.provides('PyCmd', self)

        self.returned = []
        # persistent across commands
        self.globals = {
            'ploader': ploader,
            'self': self,
            'by': by,
            'ret': self.returned.append,
        }

    def cmd_exec(self, *args):
        try:
            exec(' '.join(args).replace(';', '\n'), globals=self.globals)
        except:
            logger.warn('[exec] %s', traceback.format_exc().strip())

        if self.returned:
            if len(self.returned) == 1:
                self.returned = self.returned[0]
            logger.info('[exec] %s', self.returned)

    def cmd_eval(self, *args):
        try:
            result = eval(' '.join(args), globals=self.globals)
            logger.info('[eval] %s', result)
        except:
            logger.warn('[eval] %s', traceback.format_exc().strip())
