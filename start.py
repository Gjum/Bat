from spock import Client
from spock.plugins import DefaultPlugins
from bat.bat import BatPlugin
from bat.chat import ChatPlugin

plugins = DefaultPlugins
plugins.append(('bat', BatPlugin))
plugins.append(('chat', ChatPlugin))

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
#client = Client(plugins = plugins, start = settings)
client = Client(plugins = plugins, settings = {
	'start': { 'username': 'Bat', },
	'auth': { 'authenticated': False, }, })

try:
	client.start('LunarCo.de', 25565)
except:
	client.start('localhost', 25565)

