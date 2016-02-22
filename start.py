import cursingspock
from spockbot import Client
from spockbot.plugins import default_plugins
from bat import bat, command, pycmd, survival

plugins = default_plugins.copy()
plugins.extend([
    ('bat', bat.BatPlugin),
    ('commands', command.CommandPlugin),
    ('pycmd', pycmd.PyCmdPlugin),
    ('survival', survival.SurvivalPlugin),
    ('curses', cursingspock.CursesPlugin),
])

# login_credentials should contain a dict with 'username' and 'password'
#from login_credentials import settings
settings = {
    'start': {'username': 'Bat'},
    'auth': {'online_mode': False},
}
client = Client(plugins=plugins, settings=settings)

client.start('localhost', 25565)
