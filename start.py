from spock import Client
from spock.plugins.core import event, net, auth, timer, ticker
from spock.plugins.helpers import start, keepalive, clientinfo, entities, world, move, respawn, physics, inventory
from bat import bat, chat, command, craft

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

    ('bat', bat.BatPlugin),
    ('chat', chat.ChatPlugin),
    ('commands', command.CommandPlugin),
    ('craft', craft.CraftPlugin),
]

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
#client = Client(plugins = plugins, start = settings)
client = Client(plugins = plugins, settings = {
    'start': { 'username': 'Bat', },
    'auth': { 'authenticated': False, },
})

client.start('localhost', 25565)
