STATUS_ROTDS_1 = [
    'Blind',
    'Zombie',
    'Poison',
    'Magitek',
    'Clear',
    'Pig',
    'Petrify',
    'Ko\'d'
]

STATUS_ROTDS_2 = [
    'Condemned',
    'Near Fatal',
    'Image',
    'Silence',
    'Berserk',
    'Muddled',
    'Seizure',
    'Sleep',
]

STATUS_ROTDS_MONSTER_3 = [
    'Float',
    'Regen',
    'Slow',
    'Haste',
    'Stop',
    'Shell',
    'Protect',
    'Reflect',
]

STATUS_ROTDS_MONSTER_4 = [
    'True Knight',
    'Runic',
    'Reraise',
    '???',
    '???',
    '???',
    '???',
    'Removeable Float'
]

MISC_ROTDS_MONSTER_1 = [
    'Dies at 0 MP',
    '???',
    'Name does not appear',
    'Doesn\'t die from ID attacks',
    'Human',
    'Dragon',
    'Critical attacks if Pig',
    'Undead'
]

MISC_ROTDS_MONSTER_2 = [
    'Hard to run from',
    'Attack first',
    'Block suplex',
    'Can\'t run from',
    'Can\'t scan',
    'Can\'t sketch',
    'Special event',
    'Can\'t control'
]

ELEMENTS_ROTDS = [
    'Fire',
    'Ice',
    'Lightning',
    'Poison',
    'Wind',
    'Holy',
    'Earth',
    'Water',
]

def get_byte_string_flags(strings, b):
    s = []
    if not b:
        return s
    for i in range(8):
        if b & (1 << i):
            s.append(strings[i])
    return s