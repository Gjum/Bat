Bat - a Minecraft bot
=====================

This projects aims to create a Minecraft client that can interact with its environment.

Based on [a modified version](https://github.com/Gjum/SpockBot/tree/bat) of [SpockBot](https://github.com/SpockBotMC/SpockBot).

Features
--------

- control via in-game chat commands
- control via command-line interface (`curses`)
- dig and place blocks, interact
- pick up, hold, use items
- move along pre-defined paths
- show inventory and nearby blocks in terminal output

### Roadmap

See the [GitHub issues](https://github.com/Gjum/Bat/issues) for what I am working on.

- craft items
- drop items (WIP, can drop single/stack)
- move to any position or player
- build after a construction plan
  - copy existent buildings
  - build from schematic
- gather resources
  - explicit (mine that block, get that dropped item)
  - implicit (gather materials for diamond sword)
- fight
  - attack
  - retreat
  - potion usage
- passive background tasks
  - eat
  - collect statistical player/world data
  - protect other players

Usage
-----

1. Install [the modified SpockBot](https://github.com/Gjum/SpockBot/tree/bat)
2. Clone this repository: `git clone https://github.com/Gjum/Bat.git && cd Bat`
3. Start the bot: `python3 start.py`
