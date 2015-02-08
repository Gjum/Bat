from spock.plugins.pluginloader import PluginLoader

import logging
logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s', level=logging.DEBUG, datefmt='%H:%M:%S')
logger = logging.getLogger('spock')
Client = PluginLoader
