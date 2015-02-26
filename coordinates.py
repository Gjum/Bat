from math import floor
import random

def floorint(f):
    try:
        return int(floor(f))
    except: # no float, so don't round
        return int(f)

def block_coords(*args):
    return map(floorint, args[0] if len(args) == 1 else args)

def add_coords(a, b):
    return [a+b for a, b in zip(a, b)]

def sub_coords(a, b):
    return [a-b for a, b in zip(a, b)]

def center_and_jitter(coords):
    # 0.5: center on block, jitter by 0.2 (player apothem minus a bit)
    coords = list(coords)
    coords[0] += 0.5 + 0.2 * (1 - 2*random.random())
    coords[2] += 0.5 + 0.2 * (1 - 2*random.random())
    return coords
