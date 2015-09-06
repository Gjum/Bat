from spock import Client
from spock.plugins.core import auth, event, net, taskmanager, timer, ticker
from spock.plugins.helpers import (
    chat, clientinfo, craft, entities, interact, inventory,
    keepalive, movement, physics, respawn, start, world)
from bat import bat, command, curses

plugins = [
    ('auth', auth.AuthPlugin),
    ('event', event.EventPlugin),
    ('net', net.NetPlugin),
    ('taskmanager', taskmanager.TaskManager),
    ('ticker', ticker.TickerPlugin),
    ('timer', timer.TimerPlugin),

    ('chat', chat.ChatPlugin),
    ('clientinfo', clientinfo.ClientInfoPlugin),
    ('craft', craft.CraftPlugin),
    ('entities', entities.EntitiesPlugin),
    ('interact', interact.InteractPlugin),
    ('inventory', inventory.InventoryPlugin),
    ('keepalive', keepalive.KeepalivePlugin),
    ('movement', movement.MovementPlugin),
    ('physics', physics.PhysicsPlugin),
    ('respawn', respawn.RespawnPlugin),
    ('start', start.StartPlugin),
    ('world', world.WorldPlugin),

    ('bat', bat.BatPlugin),
    ('commands', command.CommandPlugin),
    ('curses', curses.CursesPlugin),
]

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
settings = {
    'start': { 'username': 'Bat', },
    'auth': { 'authenticated': False, },
}
client = Client(plugins = plugins, start = settings)

client.start('localhost', 25565)
