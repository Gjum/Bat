import cursingspock
from spockbot import Client
from spockbot.plugins import default_plugins as plugins
from bat import bat, command

plugins.extend([
    ('bat', bat.BatPlugin),
    ('commands', command.CommandPlugin),
    ('curses', cursingspock.CursesPlugin),
])

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
settings = {
    'start': { 'username': 'Bat', },
    'auth': { 'authenticated': False, },
}
client = Client(plugins=plugins, start=settings)

client.start('localhost', 25565)
