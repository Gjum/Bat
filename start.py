import cursingspock
from spockbot import Client
from spockbot.plugins import default_plugins
from bat import bat, blockfinder, command, \
    inventorycmd, interactcmd, movecmd, pycmd, survival

plugins = default_plugins.copy()
plugins.extend([
    ('bat', bat.BatPlugin),
    ('commands', command.CommandPlugin),
    ('blockfinder', blockfinder.BlockFinderPlugin),
    ('pycmd', pycmd.PyCmdPlugin),
    ('interactcmd', interactcmd.InteractCommandsPlugin),
    ('inventorycmd', inventorycmd.InventoryCommandsPlugin),
    ('movecmd', movecmd.MovementCommandsPlugin),
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
