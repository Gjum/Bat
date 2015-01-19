packet_dict = {
    'play': {
        'send': {
            0x04: 'player position',
            0x05: 'player look',
            0x06: 'player position and look',
            0x07: 'player digging',
        },
        'recv': {
            0x00: 'keep alive',
            0x02: 'chat message',
            0x03: 'time update',
            0x06: 'player health',
            0x08: 'player position and look',
            0x0b: 'animation',
            0x0c: 'spawn player',

            0x12: 'entity velocity',
            0x14: 'entity init',
            0x15: 'entity relative move',
            0x16: 'entity look',
            0x17: 'entity rel move and look',
            0x18: 'entity teleport',
            0x19: 'entity head look',
            0x1a: 'entity status',

            0x1f: 'player experience',

            0x21: 'chunk data',
            0x22: 'multi block change',
            0x23: 'block change',
            0x26: 'map chunk bulk',

            0x29: 'sound effect',
            0x2c: 'global entity (thunderbolt)',
            0x2f: 'set slot',
            0x30: 'window items',
            0x33: 'update sign',
            0x35: 'update block entity',

            0x37: 'statistics',
            0x38: 'player list entry',
            0x42: 'combat',
            0x44: 'world border',
        },
    },
}

