from spock import Client
from spock.plugins.core import event, net, auth, timer, ticker
from spock.plugins.helpers import start, keepalive, clientinfo, entities, world, move, respawn, physics, inventory
from bat.bat import BatPlugin
from bat.chat import ChatPlugin
from bat.command import CommandPlugin
from bat.craft import CraftPlugin

plugins = [
	('event', event.EventPlugin),
	('net', net.NetPlugin),
	('auth', auth.AuthPlugin),
	('ticker', ticker.TickerPlugin),
	('timer', timer.TimerPlugin),
	('start', start.StartPlugin),
	('keepalive', keepalive.KeepalivePlugin),
	('respawn', respawn.RespawnPlugin),
	('move', move.MovementPlugin),
	('world', world.WorldPlugin),
	('clientinfo', clientinfo.ClientInfoPlugin),
	('entities', entities.EntityPlugin),
	# ('physics', physics.PhysicsPlugin),
	('inventory', inventory.InventoryPlugin),
	('bat', BatPlugin),
	('chat', ChatPlugin),
	('commands', CommandPlugin),
	('craft', CraftPlugin),
]

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
#client = Client(plugins = plugins, start = settings)
client = Client(plugins = plugins, settings = {
	'start': { 'username': 'Bat', },
	'auth': { 'authenticated': False, },
})

client.start('LunarCo.de', 25565)
