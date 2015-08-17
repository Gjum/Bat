from spock import Client
from spock.plugins.core import event, net, auth, timer, ticker
from spock.plugins.helpers import clientinfo, entities, interact, inventory
from spock.plugins.helpers import keepalive, move, respawn, start, world
from bat import bat, chat, command, craft

plugins = [
    ('auth', auth.AuthPlugin),
    ('event', event.EventPlugin),
    ('net', net.NetPlugin),
    ('ticker', ticker.TickerPlugin),
    ('timer', timer.TimerPlugin),

    ('clientinfo', clientinfo.ClientInfoPlugin),
    ('entities', entities.EntityPlugin),
    ('interact', interact.InteractPlugin),
    ('inventory', inventory.InventoryPlugin),
    ('keepalive', keepalive.KeepalivePlugin),
    ('move', move.MovementPlugin),
    ('respawn', respawn.RespawnPlugin),
    ('start', start.StartPlugin),
    ('world', world.WorldPlugin),

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
