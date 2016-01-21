Bat - a Minecraft bot
=====================

This projects aims to create a Minecraft client that can interact with its environment.

Based on [SpockBot](https://github.com/SpockBotMC/SpockBot).

![Bat's Curses interface](http://lunarco.de/minecraft/bat-curses.png)

Features
--------

- control via in-game chat or command line interface (`curses`)
- dig and place blocks, interact with blocks and entities
- pick up, drop, craft, use items
- show inventory and nearby blocks in terminal output
- eat when hungry/injured

### Roadmap

See the [issue tracker](https://github.com/Gjum/Bat/issues) for what I am working on.

- move to any directly accessible position (WIP, no digging/scaffolding)
- build after a construction plan
  - copy existent buildings
  - build from schematic
- gather resources
  - explicit (mine *that* block, get *that* dropped item, hunt *that* animal)
  - implicit (gather materials for diamond sword and its requirements)
- fight (WIP, has optional auto-spam-click)
  - attack
  - retreat
  - potion usage
- passive background tasks
  - collect statistical player/world data (original SpockBot goal)
  - protect other players

Usage
-----

1. Install SpockBot (preferably from [my fork](https://github.com/Gjum/SpockBot/))
2. Clone this repository: `git clone https://github.com/Gjum/Bat.git && cd Bat`
3. Start the bot: `python3 start.py`

Legal
-----

Copyright (C) 2016 Gjum

Licensed under the BSD License

