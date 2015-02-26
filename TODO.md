TODO list
=========

- README
- rename project

- crafting, inventory management
- entity awareness
- objective/activity tree for SMP bot

SMP strategy
------------

1. level: wood
  1. dig 5 log (covers total sticks/planks used)
  1. craft 16 planks (4 log)
  1. craft 16 stick (8 planks)
  1. craft crafting table (4 planks)
  1. craft wooden pickaxe (2 stick, 3 planks)
  1. ? find food
  - materials left: 14 stick, 1 planks, 1 log, ? food
2. level: stone
  1. find 3 iron and dig > 13 cobble
  1. craft furnace (8 cobble)
  1. craft stone sword (1 stick, 2 cobble)
  1. craft stone pickaxe (2 stick, 3 cobble)
  1. dig the 3 iron
  - materials left: 11 stick, 1 planks, 1 log, ? food, ? cobble
3. level: smelting
  1. ? find coal (we have 1 log, 1 planks left)
  1. either:
    1. cook charcoal (requires fast switching)
    1. cook 3 iron
    1. cook < 5 food
  1. or:
    1. craft 4 planks (1 log)
    1. cook 3 iron (2 planks, cooks 3 items)
    1. cook 4 food (3 planks left, cooks 4.5 items)
  1. craft iron pickaxe (2 stick, 3 iron ingot)
  - materials left: 9 stick, ? food, ? cobble
4. level: diamond
  1. find 33 diamond
  1. craft and equip diamond armor + tools (7 stick, 33 diamond)
    - diamond chestplate (8 diamond)
    - diamond leggings   (7 diamond)
    - diamond helmet     (5 diamond)
    - diamond boots      (4 diamond)
    - diamond pickaxe    (3 diamond, 2 stick)
    - diamond axe        (3 diamond, 2 stick)
    - diamond sword      (2 diamond, 1 stick)
    - diamond shovel     (1 diamond, 2 stick)
  - materials left: 2 stick, ? food, ? cobble

### Activities:

- requirements: lists of...
  - items in inventory
  - block nearby
- activities: functions...
  - sending packets
  - setting bot states?
  - TODO
- product:
  - item in inventory (dig, craft)
  - block nearby (place)
  - TODO allow multiple products?

- dig: tool in inventory, block nearby -> item in inventory
  - dig log: -, log nearby -> log
  - dig diamond: iron pick or better, diamond nearby -> diamond
- place: block in inventory -> block nearby
- craft: materials, crafting table near -> item in inventory

