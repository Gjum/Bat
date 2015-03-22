Bat - a Minecraft bot
=====================

This projects aims to create a Minecraft client that can interact with its environment.

Based on [a modified version](https://github.com/Gjum/SpockBot) of [SpockBot](https://github.com/SpockBotMC/SpockBot).

Features
--------

- control via in-game chat commands
- instant movement to any position (*warp*) or player (*come*)
- move along pre-defined paths
- dig and place blocks, interact
- pick up, hold, use items
- show inventory and surrounding blocks in terminal output
- drop items (WIP, can drop single/stack)

### Roadmap

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

1. Install [SpockBot](https://github.com/Gjum/SpockBot)
2. Clone this repository: `git clone https://github.com/Gjum/Bat.git && cd Bat`
3. Start the bot: `python3 start.py`

