from randomtools.tablereader import (
    TableObject, get_global_label, addresses, names, gen_random_normal,
    get_activated_patches, mutate_normal, shuffle_normal, write_patch,
    get_random_degree, tblpath, get_open_file)
from randomtools.utils import (
    classproperty, cached_property, utilrandom as random)
from randomtools.interface import (
    get_outfile, get_seed, get_flags, get_activated_codes, activate_code,
    run_interface, rewrite_snes_meta, clean_and_write, finish_interface)

from bcg_junction import JunctionManager
from ex_utils import generate_character_palette, hue_rgb
from collections import Counter, defaultdict
from time import time, gmtime
from itertools import combinations
from os import path
from traceback import format_exc


VERSION = "7.4"
ALL_OBJECTS = None
DEBUG_MODE = False
FOOLS = False

JP_MAPPING = path.join(tblpath, 'jp_address_mapping.txt')

def to_ascii(text):
    s = ''
    for c in text:
        if 0x80 <= c <= 0x99:
            s += chr(ord('A') + c-0x80)
        elif 0x9A <= c <= 0xB3:
            s += chr(ord('a') + c-0x9A)
        elif 0xB4 <= c <= 0xBD:
            s += chr(ord('0') + c-0xB4)
        else:
            s += '_'
    return s


class EncodeDecodeMixin(TableObject):
    TABLE = {
        0x80: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        0x9a: 'abcdefghijklmnopqrstuvwxyz',
        0xb4: '0123456789!?',
        0xc0: '/:"\'-.,…;#+()%~',
        0xff: ' ',
        }

    for index, s in sorted(TABLE.items()):
        for i, c in enumerate(s):
            TABLE[index + i] = c
            TABLE[c] = index + i

    def encode_bytes(self, word):
        s = []
        i = 0
        while i < len(word):
            c = word[i]
            if c == '<':
                assert word[i+3] == '>'
                code = int(word[i+1:i+3], 0x10)
                s.append(code)
                i += 4
            else:
                s.append(self.TABLE[c])
                i += 1
        return bytes(s)

    def decode_bytes(self, bytestring):
        s = ''
        for c in bytestring:
            if c in self.TABLE:
                s += self.TABLE[c]
            else:
                s += '<{0:0>2x}>'.format(c)
        return s


class VanillaObject(TableObject):
    flag = 'v'
    flag_description = 'nothing'


class MonsterObject(TableObject):
    flag = 'm'
    flag_description = 'monsters'
    custom_random_enable = True
    custom_difficulty_enable = False

    magic_mutate_bit_attributes = {
        ('statuses', 'immunities'): (0xFFFFFFFF, 0xFFFFFF),
        ('absorb', 'null', 'weakness'): (0xFF, 0xFF, 0xFF),
        }

    mutate_attributes = {
        'speed': None,
        'attack': None,
        'hit': None,
        'evade': None,
        'mblock': None,
        'def': None,
        'mdef': None,
        'mpow': None,
        'hp': None,
        'mp': None,
        'xp': None,
        'gp': None,
        'level': None,
        }

    randomselect_attributes = [
        'speed', 'attack', 'hit', 'evade', 'mblock', 'def', 'mdef', 'mpow',
        'hp', 'xp', 'gp', 'level', 'morph_id', 'animation', 'special',
        ]

    REFLECT = 0x00800000

    @classproperty
    def special_ranks(self):
        if hasattr(self, '_special_ranks'):
            return self._special_ranks
        summer_dict = defaultdict(set)
        for m in MonsterObject.every:
            special = m.old_data['special'] & 0x3f
            if special & 0x20:
                continue
            summer_dict[special].add(m.rank)
        self._special_ranks = {}
        for key in summer_dict:
            self._special_ranks[key] = (sum(summer_dict[key]) /
                                        len(summer_dict[key]))
        self._special_ranks = dict(
            [(k, n) for (n, k) in enumerate(sorted(
                self._special_ranks.keys(),
                key=lambda k2: (self._special_ranks[k2], k2)))])
        return self.special_ranks

    @classproperty
    def tutorial_banned(self):
        if 'BNW' in get_global_label():
            return ['Vargas', 'Hell_Angel', 'Templar', 'Merchant', 'Whelk']
        else:
            return []

    @classproperty
    def problematic_enemies(self):
        if 'BNW' in get_global_label():
            return ['Bomb'] + self.tutorial_banned
        else:
            return []

    @property
    def name(self):
        if 'JP' in get_global_label():
            if self.index in [0x16e, 0x16f, 0x170, 0x172, 0x173, 0x174, 0x177,
                              0x178, 0x17a, 0x17b, 0x17c, 0x17e, 0x17f]:
                return 'Event %x' % self.index
            return '%x' % self.index
        return MonsterNameObject.get(self.index).name

    @property
    def is_boss(self):
        return not self.is_farmable

    @property
    def intershuffle_valid(self):
        if 'BNW' in get_global_label():
            if self.old_data['level'] in [1, 99] or self.old_data['hp'] <= 1:
                return False
        return self.rank >= 0

    @property
    def ai(self):
        return MonsterAIObject.get(self.index)

    @property
    def hp_refills(self):
        return max(self.old_data['hp'] % 10, 1)

    @property
    def true_hp(self):
        return self.hp * self.hp_refills

    @property
    def true_hp_old(self):
        return self.old_data['hp'] * self.hp_refills

    @property
    def ai_script(self):
        return self.ai.ai_script

    @property
    def pretty_ai_script(self):
        return self.ai.pretty_ai_script

    @property
    def metamorph(self):
        return MetamorphObject.get(self.morph_id & 0x1F)

    @property
    def old_morphrate(self):
        return self.old_data['morph_id'] >> 5

    @property
    def loot(self):
        ml = MonsterLootObject.get(self.index)
        return ml.loot

    @property
    def drops(self):
        ml = MonsterLootObject.get(self.index)
        return ml.drops

    @cached_property
    def is_farmable(self):
        for f in FormationObject.every:
            if f.is_random_encounter and self in f.old_enemies:
                return True
        return False

    @property
    def rank(self):
        if hasattr(self, '_rank'):
            return self._rank

        MonsterObject.class_reseed('ranking')
        monsters = list(MonsterObject.every)
        if 'BNW' in get_global_label():
            max_hp = 65535
        else:
            max_hp = 65536

        monsters = [m for m in monsters if m.old_data['level'] > 0
                    and m.old_data['hp'] < max_hp
                    and 'Event' not in m.name and set(m.name) != {'_'}]

        score_a = lambda m: (m.old_data['level'], m.true_hp_old,
                             len(m.ai_script), m.signature)
        score_b = lambda m: (m.true_hp_old, m.old_data['level'],
                             len(m.ai_script), m.signature)
        by_a = sorted(monsters, key=score_a)
        by_b = sorted(monsters, key=score_b)

        LEVEL_MULTIPLIER = 1.5
        HP_MULTIPLIER = 1

        for m in MonsterObject.every:
            if m in monsters:
                a, b = (by_a.index(m) * LEVEL_MULTIPLIER,
                        by_b.index(m) * HP_MULTIPLIER)
                m._base_rank = max(a, b) * (a+b)
            else:
                m._base_rank = -1

        companion_dict = defaultdict(set)
        for f in FormationObject.every:
            enemies = set([m for m in f.enemies if m._base_rank >= 0])
            for m in enemies:
                companion_dict[m] |= enemies

        for m in MonsterObject.every:
            if m in companion_dict:
                companion_rank = (
                    sum([m2._base_rank for m2 in companion_dict[m]])
                    / len(companion_dict[m]))
                similarity = m._base_rank / companion_rank
                if similarity > 1:
                    similarity = 1 / similarity
                ratio = similarity / 2
                if m.is_boss:
                    m._rank = m._base_rank
                    continue
                m._rank = (m._base_rank*(1-ratio)) + (companion_rank*ratio)
            else:
                m._rank = -1

        return self.rank

    @property
    def tags(self):
        tags = set()
        element = self.absorb | self.null
        for i in range(8):
            if element & (1 << i):
                tags.add(SkillObject.ELEMENT_NAMES[i])

        for i in range(8):
            if self.weakness & (1 << i):
                tags.add('-%s' % SkillObject.ELEMENT_NAMES[i])

        if self.get_bit('dies_zero_mp'):
            tags.add('mp')

        if self.get_bit('is_undead'):
            tags |= {'death', 'zombie'}

        for i in range(32):
            if self.statuses & (1 << i):
                tags.add(SkillObject.STATUS_NAMES[i])

        if self.special == 0x30:
            tags.add('drain')
        elif self.special == 0x31:
            tags |= {'drain', 'mp'}
        elif self.special & 0xf0 == 0x20:
            tags.add('physical')
        elif self.special >> 4 <= 1:
            tags.add(SkillObject.STATUS_NAMES[self.special & 0xf])

        tags = sorted(tags) * 2

        #for i in range(32):
        #    if self.immunities & (1 << i):
        #        tags.append(SkillObject.STATUS_NAMES[i])

        for cls in (MonsterCtrlObject, MonsterSketchObject, MonsterRageObject):
            try:
                mob = cls.get(self.index)
            except KeyError:
                continue
            for index in mob.commands:
                if index in {0xee, 0xef, 0xff}:
                    continue
                tags += SkillObject.get(index).tags

        for element in SkillObject.OPPOSITE_ELEMENTS:
            if element in tags:
                tags = [t for t in tags if t != '-%s' % element]
        if set(tags) >= {'buff', 'debuff'}:
            tags = [t for t in tags if t not in {'-buff', '-debuff'}]
        tags = ['float' if t == 'dance' else t for t in tags]

        return sorted(tags)

    def mutate(self):
        if self.rank < 0:
            return

        if self.intershuffle_valid:
            assert self.random_selected

        super(MonsterObject, self).mutate()

        for name in self.tutorial_banned:
            if name in self.name:
                self.special = self.old_data['special']

        special = self.special & 0x3f
        if special & 0x3f in self.special_ranks:
            max_index = len(self.special_ranks)-1
            special_ratio = self.special_ranks[special] / max_index
            ranked_ratio = self.ranked_ratio or 0
            assert 0 <= special_ratio <= 1
            assert 0 <= ranked_ratio <= 1
            difference = (special_ratio - ranked_ratio) * 2
            if difference > 0:
                factor = (difference**2) * ((1-self.random_degree) ** (1/2))
                if factor >= 1 or random.random() < factor:
                    self.special = self.old_data['special']

        if not self.is_boss and self.hp > self.old_data['hp']:
            self.hp = mutate_normal(
                self.old_data['hp'], self.old_data['hp'], self.hp,
                wide=True, random_degree=self.random_degree)

        if self.level > self.old_data['level']:
            self.level = mutate_normal(
                self.old_data['level'], self.old_data['level'], self.level,
                wide=True, random_degree=self.random_degree)

        for name in self.problematic_enemies:
            if name in self.name:
                for attr in sorted(self.mutate_attributes.keys()):
                    newval = getattr(self, attr)
                    oldval = self.old_data[attr]
                    value = ((newval * self.random_degree)
                             + (oldval * (1-self.random_degree)))
                    setattr(self, attr, int(round(value)))

    def difficulty_boost(self):
        if self.random_difficulty == 1.0 or not self.ranked_ratio:
            return

        if self.random_difficulty > 1.0:
            difficulty = self.random_difficulty - 1
            difficulty = (difficulty * (self.ranked_ratio)) + 1
        else:
            difficulty = self.random_difficulty

        negative_attrs = ['speed', 'attack', 'hit', 'evade', 'mblock',
                          'def', 'mdef', 'mpow', 'hp', 'mp', 'level']
        positive_attrs = ['xp', 'gp']

        for diffattr in positive_attrs + negative_attrs:
            value = getattr(self, diffattr)
            if diffattr in negative_attrs:
                value = int(round(value * random.uniform(1.0, difficulty)))
            elif diffattr in positive_attrs:
                value = int(round(value / random.uniform(1.0, difficulty)))
            length = [l for (attr, l, _) in self.specs.attributes
                      if attr == diffattr][0]
            if length == 1:
                minval, maxval = 0, 0xFE
            elif length == 2:
                minval, maxval = 0, 0xFFFE
            else:
                minval, maxval = None, None
            maxval = max(maxval, self.old_data[diffattr])
            value = max(minval, min(maxval, value))
            setattr(self, diffattr, value)

    def preclean(self):
        self.reseed('difficulty')
        self.difficulty_boost()

    def cleanup(self):
        elements, old_elements = (self.absorb | self.null), (
            self.old_data['absorb'] | self.old_data['null'])
        if (elements & old_elements) == elements:
            self.absorb = self.old_data['absorb']
            self.null = self.old_data['null']
        if self.immunities & self.old_data['immunities'] == self.immunities:
            self.immunities = self.old_data['immunities']

        if self.is_boss and self.rank >= 0:
            for attr in sorted(self.mutate_attributes):
                setattr(self, attr, max(getattr(self, attr),
                                        self.old_data[attr]))

        self.statuses ^= (self.statuses & self.immunities)

        if 'easymodo' in get_activated_codes():
            for attr in self.mutate_attributes:
                setattr(self, attr, 1)
            self.xp = 65535
            self.gp = 65535

        if 'BNW' in get_global_label():
            self.hp = (self.hp // 10) * 10
            self.hp += self.old_data['hp'] % 10
            while self.hp >= 0xFFFE:
                self.hp -= 10

            if 'Tonberry' in self.name and self.statuses & self.REFLECT:
                self.statuses ^= self.REFLECT
                assert not self.statuses & self.REFLECT


class MonsterNameObject(EncodeDecodeMixin):
    @property
    def name(self):
        return to_ascii(self.name_text)

    @classmethod
    def full_cleanup(cls):
        if hasattr(addresses, 'myself_rages_address'):
            f = open(get_outfile(), 'r+b')
            counter = 0
            for mno in sorted(MonsterNameObject.every, key=lambda n: n.name):
                if mno.index >= 0x100:
                    continue
                f.seek(addresses.myself_rages_address + counter)
                f.write(bytes([mno.index]))
                counter += 1
            assert counter <= 0x100
            while counter < 0x100:
                f.write(b'\xff')
            f.close()

        super(MonsterNameObject, cls).full_cleanup()


class MonsterLootObject(TableObject):
    flag = 't'
    custom_random_enable = True

    @classproperty
    def intershuffle_attributes(self):
        if 'BNW' in get_global_label():
            return ['drop_item_ids']
        else:
            return ['steal_item_ids', 'drop_item_ids']

    @property
    def intershuffle_valid(self):
        return self.is_farmable

    @property
    def monster(self):
        return MonsterObject.get(self.index)

    @property
    def is_farmable(self):
        return self.monster.is_farmable

    @property
    def loot(self):
        return [ItemObject.get(i)
                for i in self.steal_item_ids + self.drop_item_ids if i < 0xFF]

    @property
    def drops(self):
        return [ItemObject.get(i) for i in self.drop_item_ids if i < 0xFF]

    @property
    def rank(self):
        return self.monster.rank

    def mutate(self):
        for i, s in enumerate(self.steal_item_ids):
            if s < 0xFF:
                s = ItemObject.get(s).get_similar(
                    random_degree=self.random_degree).index
                self.steal_item_ids[i] = s

        for i, d in enumerate(self.drop_item_ids):
            if d < 0xFF:
                d = ItemObject.get(d).get_similar(
                    random_degree=self.random_degree).index
                self.drop_item_ids[i] = d

    def cleanup(self):
        old_drops = set(self.old_data['drop_item_ids'])
        if len(old_drops) == 1 and old_drops != {0xff}:
            self.drop_item_ids = [self.drop_item_ids[0]] * 2
            assert len(set(self.drop_item_ids)) == 1

        old_steals = set(self.old_data['steal_item_ids'])
        if len(old_steals) == 1 and old_steals != {0xff}:
            self.steal_item_ids = [self.steal_item_ids[0]] * 2
            assert len(set(self.steal_item_ids)) == 1

        if 'BNW' in get_global_label():
            for n, i in enumerate(self.steal_item_ids):
                index = self.old_data['steal_item_ids'][n]
                if not 0 <= index <= 0xfe:
                    continue
                item = ItemObject.get(index)
                if 'Gum_Pod' in item.name:
                    self.steal_item_ids[n] = self.old_data['steal_item_ids'][n]


class MonsterCtrlObject(TableObject): pass
class MonsterSketchObject(TableObject): pass


class MonsterRageObject(TableObject):
    @property
    def monster(self):
        return MonsterObject.get(self.index)

    @property
    def ailment_special(self):
        if self.monster.special & 0x20:
            return None
        return self.monster.special & 0x1f

    @property
    def old_ailment_special(self):
        old_special = self.monster.old_data['special']
        if old_special & 0x20:
            return None
        return old_special & 0x1f

    def cleanup(self):
        if not hasattr(MonsterRageObject, '_allowed_specials'):
            MonsterRageObject._allowed_specials = set()
            for mro in MonsterRageObject.every:
                if 0xEF in mro.old_data['commands']:
                    MonsterRageObject._allowed_specials.add(
                        mro.old_ailment_special)

        special = self.ailment_special
        if special not in MonsterRageObject._allowed_specials:
            self.commands = [0xEE if c == 0xEF else c for c in self.commands]


class MonsterAIObject(TableObject):
    AICODES = {0xF0: 3, 0xF1: 1, 0xF2: 3, 0xF3: 2,
               0xF4: 3, 0xF5: 3, 0xF6: 3, 0xF7: 1,
               0xF8: 2, 0xF9: 3, 0xFA: 3, 0xFB: 2,
               0xFC: 3, 0xFD: 0, 0xFE: 0, 0xFF: 0
               }

    @cached_property
    def ai_script(self):
        pointer = addresses.ai_scripts_address + self.ai_pointer
        f = open(get_outfile(), 'r+b')
        f.seek(pointer)
        script = []
        seen = False
        while True:
            value = f.read(1)
            try:
                numargs = self.AICODES[ord(value)]
                args = f.read(numargs)
            except KeyError:
                args = b''
            script.append(value + args)
            if ord(value) == 0xFF:
                if seen:
                    break
                else:
                    seen = True
        f.close()
        return script

    @cached_property
    def hp_refills(self):
        for (i, line) in enumerate(self.ai_script):
            if line == [0xFC, 0x06, 0x36, 0x00]:
                for line2 in self.ai_script[i+1:]:
                    if line2[0] == 0xFC:
                        if line2[:2] == [0xFC, 0x0D]:
                            return line2[3] + 1
                    elif line2[0] in [0xFE, 0xFF]:
                        break
        return 1

    @cached_property
    def pretty_ai_script(self):
        s = ''
        for line in self.ai_script:
            s += ('{0:0>2X} : '.format(line[0])) + ' '.join(
                ['{0:0>2X}'.format(v) for v in line[1:]])
            s = s.strip() + '\n'
        return s.strip()


class MetamorphObject(TableObject):
    def __repr__(self):
        s = 'MORPH %x\n' % self.index
        for i in self.items:
            s += str(i.name) + '\n'
        return s.strip()

    @property
    def items(self):
        return [ItemObject.get(i) for i in self.item_ids if i <= 0xFE]


class FormationObject(TableObject):
    custom_random_enable = 'f'

    def __repr__(self):
        s = 'FORMATION %x: %s' % (
            self.index, ' '.join(e.name for e in self.enemies))
        return s

    @cached_property
    def guaranteed_treasure(self):
        if self.rank < 0:
            return None
        guaranteed = []
        for e in self.enemies:
            drops = e.drops
            if len(drops) < 2:
                continue
            guaranteed.append(min(drops, key=lambda d: d.rank))
        if not guaranteed:
            return None
        return max(guaranteed, key=lambda d: d.rank)

    @cached_property
    def is_random_encounter(self):
        for p in FourPackObject.every:
            if (p.is_random_encounter and self in p.old_formations):
                return True
        return False

    @cached_property
    def is_rare_encounter(self):
        if not self.is_random_encounter:
            return False
        for p in FourPackObject.every:
            if self in p.formations[:3]:
                return False
        return True

    @cached_property
    def is_random_event(self):
        for p in TwoPackObject.every:
            if (p.is_random and self in p.old_formations):
                return True
        return False

    @cached_property
    def is_fixed_event(self):
        for p in TwoPackObject.every:
            if (self in p.old_formations and not p.is_random):
                return True
        return False

    @cached_property
    def is_chest_encounter(self):
        for c in ChestObject.every:
           if c.old_formation and self in c.old_formation.formations:
                return True
        return False
    
    @cached_property
    def is_inescapable(self):
        for e in self.enemies:
            if e.get_bit('is_inescapable'):
                return True

    @property
    def metadata(self):
        return FormationMetaObject.get(self.index)

    @property
    def has_xp(self):
        return any([e.xp > 0 and e.rank >= 0 for e in self.enemies])

    def clear_music(self, force=False):
        self.metadata.clear_music(force=force)

    @property
    def true_enemy_ids(self):
        eids = []
        for (i, eid) in enumerate(self.enemy_ids):
            if eid == 0xFF and not self.enemies_present & (1 << i):
                continue
            if self.bossbyte & (1 << i):
                eid |= 0x100
                if eid > MonsterObject.count:
                    continue
            eids.append(eid)
        return eids

    @cached_property
    def old_true_enemy_ids(self):
        eids = []
        for (i, eid) in enumerate(self.old_data['enemy_ids']):
            if eid == 0xFF and not self.old_data['enemies_present'] & (1 << i):
                continue
            if self.old_data['bossbyte'] & (1 << i):
                eid |= 0x100
            eids.append(eid)
        return eids

    @property
    def enemies(self):
        return [MonsterObject.get(eid) for eid in self.true_enemy_ids]

    @cached_property
    def old_enemies(self):
        true_enemy_ids = [eid for eid in self.old_true_enemy_ids if eid <= MonsterObject.count]
        return [MonsterObject.get(eid) for eid in true_enemy_ids]

    @property
    def rank(self):
        if hasattr(self, '_rank'):
            return self._rank

        for f in FormationObject.every:
            enemy_ranks = [e.rank for e in f.enemies if e.rank > 0]
            if not enemy_ranks:
                f._base_rank = -1
            else:
                f._base_rank = max(enemy_ranks) * (sum(enemy_ranks)**0.0625)
            f._rank = f._base_rank

        companion_dict = defaultdict(set)
        for fp in FourPackObject.every:
            formations = set([f for f in fp.formations if f._base_rank >= 0])
            for f in formations:
                companion_dict[f] |= formations

        for f in FormationObject.every:
            if f in companion_dict:
                companion_rank = (
                    sum([f2._base_rank for f2 in companion_dict[f]])
                    / len(companion_dict[f]))
                similarity = f._base_rank / companion_rank
                if similarity > 1:
                    similarity = 1 / similarity
                ratio = similarity / 2
                f._rank = (f._base_rank*(1-ratio)) + (companion_rank*ratio)

        return self.rank

    @cached_property
    def two_packs(self):
        return [p for p in TwoPackObject.every if self in p.formations]


class FormationMetaObject(TableObject):
    @property
    def music(self):
        return (self.music_misc >> 3) & 0x7

    def set_music(self, music):
        self.music_misc |= (0x7 << 3)
        self.music_misc ^= (0x7 << 3)
        self.music_misc |= (music << 3)
        assert self.music == music

    def clear_music(self, force=False):
        if self.music == 0 or force:
            self.set_bit('disable_fanfare', True)
            self.set_bit('continue_current_music', True)

    def reload_randomized_music(self):
        new_data = dict(self.old_data)
        self.read_data()
        new_music = self.music
        df = self.get_bit('disable_fanfare')
        ccm = self.get_bit('continue_current_music')
        for attr, value in new_data.items():
            setattr(self, attr, value)
        self.set_music(new_music)
        self.set_bit('disable_fanfare', df)
        self.set_bit('continue_current_music', ccm)


class PackObject(TableObject):
    def __repr__(self):
        s = '%s-PACK %x:\n%s' % (
            len(self.formations), self.index,
            '\n'.join(str(f) for f in self.formations))
        return s

    @cached_property
    def guaranteed_treasure(self):
        treasure = None
        for f in self.formations:
            if f.guaranteed_treasure is None:
                return None
            if treasure is None:
                treasure = f.guaranteed_treasure
            elif f.guaranteed_treasure.rank < treasure.rank:
                treasure = f.guaranteed_treasure
        return treasure

    @cached_property
    def treasure_rank(self):
        if self.guaranteed_treasure is None:
            return 0
        return self.guaranteed_treasure.rank

    @property
    def has_xp(self):
        return all([f.has_xp and f.rank >= 0 for f in self.formations])

    @property
    def rank(self):
        if any([f.rank < 0 for f in self.formations]):
            return -1

        if len(self.formations) == 4:
            weights = [5, 5, 5, 1]
        else:
            assert len(self.formations) == 2
            weights = [1, 1]

        rank = 0
        for w, f in zip(weights, self.formations):
            rank += (w / float(sum(weights))) * f.rank

        return rank

    @property
    def formation_ids(self):
        formation_ids = []
        for attr in ['common', 'common1', 'common2', 'common3', 'rare']:
            if hasattr(self, attr):
                formation_ids.append(getattr(self, attr))
        assert len(formation_ids) in [2, 4]
        return formation_ids

    @property
    def formations(self):
        return [FormationObject.get(fid & 0x7fff)
                for fid in self.formation_ids]

    @cached_property
    def old_formation_ids(self):
        formation_ids = []
        for attr in ['common', 'common1', 'common2', 'common3', 'rare']:
            if hasattr(self, attr):
                formation_ids.append(self.old_data[attr])
        assert len(formation_ids) in [2, 4]
        return formation_ids

    @cached_property
    def old_formations(self):
        return [FormationObject.get(fid & 0x7fff)
                for fid in self.old_formation_ids]


class FourPackObject(PackObject):
    @property
    def formations(self):
        return [FormationObject.get(self.common1 & 0x7fff),
                FormationObject.get(self.common2 & 0x7fff),
                FormationObject.get(self.common3 & 0x7fff),
                FormationObject.get(self.rare & 0x7fff),
                ]

    @cached_property
    def is_random_encounter(self):
        for l in LocationObject.every:
            if not l.get_bit('enable_encounters'):
                continue
            if self.index == l.area_pack.old_data['pack_id']:
                return True

        for zpp in ZonePackPackObject.every:
            if self.index in zpp.old_data['pack_ids']:
                return True

        return False

    def cleanup(self):
        # TODO To restore
        #if MusicObject.flag in get_flags():
        #    return
        for f in self.formations:
            f.clear_music()


class TwoPackObject(PackObject):
    @property
    def formations(self):
        return [FormationObject.get(self.common),
                FormationObject.get(self.rare),
                ]

    @property
    def is_random(self):
        return len(set(self.formations)) == 2


class ZonePackPackObject(TableObject):
    @property
    def packs(self):
        return [FourPackObject.get(pid) for pid in self.pack_ids]

    @property
    def formations(self):
        return [f for pack in self.packs for f in pack.formations]


class AreaPackObject(TableObject):
    @property
    def pack(self):
        return FourPackObject.get(self.pack_id)

    @property
    def formations(self):
        return self.pack.formations


class LocationObject(TableObject):
    @property
    def events(self):
        #return EventObject.getgroup(self.index)
        raise NotImplementedError("To import!")

    @property
    def npcs(self):
        #return NpcObject.getgroup(self.index)
        raise NotImplementedError("To import!")

    @property
    def exits(self):
        #return EntranceObject.getgroup(self.index)
        raise NotImplementedError("To import!")

    @property
    def long_exits(self):
        #return LongEntranceObject.getgroup(self.index)
        raise NotImplementedError("To import!")

    @property
    def chests(self):
        return ChestObject.getgroup(self.index)

    @property
    def area_pack(self):
        return AreaPackObject.get(self.index)

    @property
    def pack(self):
        return self.area_pack.pack

    def set_enemy_pack(self, pack):
        self.area_pack.pack_id = pack.index & 0xFF
        assert self.pack is pack

    @property
    def formations(self):
        return self.pack.formations

    def purge_associated_objects(self):
        for x in self.exits + self.long_exits:
            x.groupindex = -1
        for e in self.events:
            e.groupindex = -1
        for n in self.npcs:
            n.groupindex = -1

    def set_palette(self, value):
        self.palette_index |= 0x3F
        self.palette_index ^= 0x3F
        self.palette_index |= value

    def reload_randomized_music(self):
        new_data = dict(self.old_data)
        self.read_data()
        new_music = self.music
        for attr, value in new_data.items():
            setattr(self, attr, value)
        self.music = new_music


class ItemObject(TableObject):
    custom_random_enable = 'i'

    mutate_attributes = {
        'power': None,
        'price': None,
        }

    magic_mutate_bit_attributes = {
        'equipability': 0xBFFF,
        #('elements', 'elemabsorbs', 'elemnulls', 'elemweaks'): (
        #    0xFF, 0xFF, 0xFF, 0xFF),
        }

    bnw_price_correction = {
            'Bouncy_Ball': 10000,
        }

    def __repr__(self):
        return self.name

    @property
    def magic_mutate_valid(self):
        return (EquipabilityObject.flag in get_flags() and self.equipability
                and 1 <= (self.itemtype & 0x7) <= 5)

    @property
    def name(self):
        return ItemNameObject.get(self.index).name

    @property
    def is_legit(self):
        if 'BNW' in get_global_label():
            return set(self.name) != {'_'}
        return True

    @property
    def pretty_type(self):
        return {0: 'tool',
                1: 'weapon',
                2: 'armor',
                3: 'shield',
                4: 'helm',
                5: 'relic',
                6: 'consumable'}[self.itemtype & 0x7]

    @property
    def tags(self):
        if self.itemtype & 0xf in (0, 6):
            return []

        tags = set()

        elements = self.elements | self.elemabsorbs | self.elemnulls
        for i in range(8):
            if elements & (1 << i):
                tags.add(SkillObject.ELEMENT_NAMES[i])

        for i in range(8):
            if self.elemweaks & (1 << i):
                if SkillObject.ELEMENT_NAMES[i] not in tags:
                    tags.add('-%s' % SkillObject.ELEMENT_NAMES[i])

        for i in range(8):
            bitmask = (1 << i)
            if self.statusacquire2 & bitmask:
                tags |= {'status', 'buff'}
                tags.add(SkillObject.STATUS_NAMES[8:16][i])
            if self.statusacquire3 & bitmask:
                tags |= {'status', 'buff'}
                tags.add(SkillObject.STATUS_NAMES[16:24][i])
            if self.statusprotect1 & bitmask:
                tags |= {'status', 'heal'}
                tags.add(SkillObject.STATUS_NAMES[0:8][i])
            if self.statusprotect2 & bitmask:
                tags |= {'status', 'heal'}
                tags.add(SkillObject.STATUS_NAMES[8:16][i])

        if self.itemtype & 0xf == 1:
            if not self.elements:
                tags.add('physical')
            special_tags = [
                None, 'luck', '-death', 'death',
                'death', 'drain', ('drain', 'mp'), 'mp',
                '-float', 'luck', 'death', 'wind',
                'heal', 'death', 'mp', None]
            special_tag = special_tags[self.specialaction >> 4]
            if special_tag is not None:
                if isinstance(special_tag, str):
                    special_tag = [special_tag]
                tags |= set(special_tag)

        if self.equipability & 0x4000:
            tags.add('imp')

        if self.get_bit('weapon_death_protect'):
            tags |= {'life', 'death'}

        if self.special3 & 0x18:
            tags.add('luck')

        if self.special3 & 0x80:
            tags |= {'death', 'zombie'}

        if self.special2 & 0x66:
            tags.add('defend')

        if self.special2 & 0x19:
            tags.add('physical')

        if self.special3 & 0x07:
            tags.add('buff')

        if self.fieldeffect & 0x80:
            tags.add('heal')

        if self.fieldeffect & 0x20:
            tags.add('haste')

        if self.fieldeffect & 0x03:
            tags.add('luck')

        if self.statboost1 & 0xe0:
            tags.add('mp')

        if self.statboost1 & 0x02:
            tags.add('magic')

        if self.statboost2 & 0x01:
            tags.add('luck')

        if self.statboost2 & 0x0c:
            tags.add('sketch')

        if self.statboost2 & 0x90:
            tags.add('physical')

        if self.statboost2 & 0x60:
            tags.add('mp')

        if self.special1 & 0x03:
            tags.add('luck')

        if self.special1 & 0x80:
            tags.add('hide')

        tags = ['float' if t == 'dance' else t for t in tags]
        if ((self.itemtype & 0x20 or self.breakeffect)
                and self.itemtype & 0xf < 6):
            tags += sorted(set(SkillObject.get(self.breakeffect & 0x3f).tags))

        return sorted(tags)

    @property
    def rank(self):
        if hasattr(self, '_rank'):
            return self._rank

        ItemObject.class_reseed('ranking')

        if 'BNW' in get_global_label():
            BANNED_INDEXES = [0x10]  # Narpas
        else:
            BANNED_INDEXES = []

        # TODO: also consider morphs?
        tier0 = [i for i in ItemObject.every if i.is_buyable]
        tier0 = sorted(tier0, key=lambda i: (i.is_buyable, i.signature))
        tier1 = [i for i in ItemObject.every
                 if i.is_farmable and i not in tier0]
        tier1 = sorted(tier1, key=lambda i: (i.is_farmable, i.signature))
        tier2b = [i for i in ItemObject.every
                  if i.is_boss_loot and i not in tier0 + tier1]
        tier2b = sorted(tier2b,
                        key=lambda i: (i.is_boss_loot, i.signature))
        tier2c = [i for i in ItemObject.every
                  if i.is_chest and i not in tier0 + tier1]
        tier2c = sorted(tier2c, key=lambda i: (i.is_chest, i.signature),
                        reverse=True)
        tier2 = [i for i in ItemObject.every
                 if i in tier2b and i in tier2c]
        tier2 = sorted(
            tier2, key=lambda i: ((tier2b.index(i)/(len(tier2b)-1)) +
                                  (tier2c.index(i)/(len(tier2c)-1)),
                                  i.signature))
        tier3 = [i for i in ItemObject.every
                 if i in tier2b + tier2c and i not in tier2]

        def t3_sorter(i):
            mylist = tier2b if i in tier2b else tier2c
            return (mylist.index(i) / (len(mylist)-1), i.signature)

        tier3 = sorted(tier3, key=t3_sorter)
        tier4 = [i for i in ItemObject.every if i.is_legit and
                 i not in tier0 + tier1 + tier2 + tier3]
        tier4 = sorted(tier4, key=lambda i: i.signature)

        full_list = tier0 + tier1 + tier2 + tier3 + tier4

        assert len(full_list) == len(set(full_list))
        full_list = [i for i in full_list if i.is_legit]

        for i in full_list:
            i._rank_no_colosseum = full_list.index(i)

        for i in full_list:
            i._rank = i._rank_no_colosseum
            if i.is_colosseum:
                colosseum_rank = min(i2._rank_no_colosseum
                                     for i2 in i.is_colosseum)
                colosseum_rank = max(
                    colosseum_rank, max(i2._rank_no_colosseum
                                        for i2 in full_list if i2.is_buyable))
                if 0 < colosseum_rank < i._rank_no_colosseum:
                    i._rank = (colosseum_rank + i._rank_no_colosseum) / 2

        full_list = sorted(full_list, key=lambda i: (i._rank, i.signature))

        if 'BNW_2' in get_global_label():
            tierlist = path.join(tblpath, 'item_tiers_bnw2.txt')
            tiers = {}
            with open(tierlist) as f:
                for line in f:
                    tier, index, name, price = line.split()
                    index = int(index, 0x10)
                    tier = int(tier)
                    tiers[index] = tier
            max_value = max(tiers.values()) + 1
            for i in ItemObject.every:
                if i.is_legit and i.index not in tiers:
                    if i.is_legit:
                        tiers[i.index] = max_value
                    else:
                        tiers[i.index] = -1

            full_list = sorted(
                full_list, key=lambda i: (tiers[i.index], i._rank,
                                          i.signature))

        for i in full_list:
            i._rank = full_list.index(i)

        for i in ItemObject.every:
            if i.index in BANNED_INDEXES or not hasattr(i, '_rank'):
                i._rank = -1

        return self.rank

    @cached_property
    def highest_rank_price(self):
        return max([i.old_data['price'] for i in ItemObject.every
                    if i.rank <= self.rank and i.rank >= 0])

    @cached_property
    def is_buyable(self):
        for s in ShopObject.every:
            if set(s.old_data['item_ids']) <= {0x00, 0xFF}:
                continue
            if self.index in s.old_data['item_ids']:
                if 'BNW' in get_global_label():
                    for name in sorted(self.bnw_price_correction):
                        if name in self.name:
                            self.price = self.bnw_price_correction[name]
                            break
                return self.price
        return 0

    @cached_property
    def is_farmable(self):
        mls = []
        for ml in MonsterLootObject.every:
            if (ml.is_farmable and self.index in ml.old_data['steal_item_ids']
                    + ml.old_data['drop_item_ids']):
                mls.append(ml)
        if mls:
            return min([ml.monster.rank for ml in mls])
        return 0

    @cached_property
    def is_boss_loot(self):
        mls = []
        for ml in MonsterLootObject.every:
            if (not ml.is_farmable and
                    self.index in ml.old_data['steal_item_ids']
                    + ml.old_data['drop_item_ids']):
                mls.append(ml)
        if mls:
            return min([ml.monster.rank for ml in mls])
        return 0

    @cached_property
    def is_chest(self):
        cs = []
        for c in ChestObject.every:
            if self is c.old_treasure:
                cs.append(c)
        for c in CharacterObject.every[:14]:
            if self in c.old_initial_equipment:
                return 999
        return len(cs)

    @cached_property
    def is_initial_equipment(self):
        for c in CharacterObject.every[:14]:
            if self in c.old_initial_equipment:
                return True
        return False

    @property
    def is_colosseum(self):
        if hasattr(self, '_is_colosseum'):
            return self._is_colosseum

        for i in ItemObject.every:
            i._is_colosseum = set([])

        for c in ColosseumObject.every:
            if c.is_legit:
                c.trade._is_colosseum.add(c.item)

        while True:
            finished = True
            for i in ItemObject.every:
                for i2 in list(i._is_colosseum):
                    if i2._is_colosseum - i._is_colosseum:
                        i._is_colosseum |= i2._is_colosseum
                        finished = False
            if finished:
                break

        return self.is_colosseum

    @property
    def command_changes(self):
        raise NotImplementedError("To import!")
        """matches = []
        for c in CmdChangeFBObject.every:
            if c.equipment_bit & self.special1:
                matches.append(c)
        return matches"""

    @property
    def mutate_valid(self):
        return self.is_equipable

    def mutate(self):
        if not self.mutate_valid:
            return
        if EquipmentStatsObject.flag not in get_flags():
            return
        super(ItemObject, self).mutate()
        if self.pretty_type == 'weapon':
            candidates = [o for o in self.every if o.pretty_type == 'weapon']
        else:
            candidates = [o for o in self.every if o.pretty_type != 'weapon']
        candidates = [o for o in candidates if o.mutate_valid]
        values = [o.hitmdef for o in candidates]
        minval, maxval = min(values), max(values)
        self.hitmdef = mutate_normal(self.hitmdef, minval, maxval,
                                     random_degree=self.random_degree)
        candidates = [o for o in self.every if o.mutate_valid]
        make_negative = lambda v: -(v & 0x7) if v >= 8 else v
        reverse_negative = lambda v: (0x8 | abs(v)) if v < 0 else v
        for attribute in ['speedvigor', 'magstam']:
            myval = make_negative(getattr(self, attribute) & 0xF)
            myval = mutate_normal(myval, -7, 7,
                                  random_degree=self.random_degree)
            myval = reverse_negative(myval)
            setattr(self, attribute,
                    (getattr(self, attribute) & 0xF0) | myval)

            myval = make_negative(getattr(self, attribute) >> 4)
            myval = mutate_normal(myval, -7, 7,
                                  random_degree=self.random_degree)
            myval = reverse_negative(myval)
            setattr(self, attribute,
                    (getattr(self, attribute) & 0xF) | (myval << 4))

        blockranks = [0xa, 0x9, 0x8, 0x7, 0x6, 0x0, 0x1, 0x2, 0x3, 0x4, 0x5]
        myval = self.mblockevade & 0xF
        index = mutate_normal(blockranks.index(myval), 0, len(blockranks)-1,
                              random_degree=self.random_degree)
        self.mblockevade = (self.mblockevade & 0xF0) | blockranks[index]

        myval = self.mblockevade >> 4
        index = mutate_normal(blockranks.index(myval), 0, len(blockranks)-1,
                              random_degree=self.random_degree)
        self.mblockevade = (self.mblockevade & 0xF) | (blockranks[index] << 4)

    @property
    def is_equipable(self):
        equiptypes = ['weapon', 'armor', 'shield', 'helm', 'relic']
        return (self.pretty_type in equiptypes and self.rank >= 0
                and self.old_data['equipability'] & 0x3fff)

    def magic_mutate_bits(self):
        if not self.is_equipable:
            return

        equiptypes = ['weapon', 'armor', 'shield', 'helm', 'relic']
        if not hasattr(ItemObject, 'character_mapping'):
            self.class_reseed('mut_equips')
            ItemObject.character_mapping = {}
            for equiptype in equiptypes:
                if equiptype not in self.character_mapping:
                    shuffled = list(range(14))
                    random.shuffle(shuffled)
                    self.character_mapping[equiptype] = shuffled

        equipability = self.equipability & 0x3fff
        random_degree = EquipabilityObject.random_degree
        if (bin(equipability).count('1') >= 2
                and random.random() < ((random_degree**0.5)
                                       *self.ranked_ratio)):
            equipables = [i for i in ItemObject.every if i.is_equipable]
            chosen = random.choice(equipables)
            if chosen is not self and (
                    chosen.old_data['equipability'] & equipability ==
                    chosen.old_data['equipability'] & 0x3fff):
                self.equipability = chosen.old_data['equipability']

        old_equip = self.equipability
        super(ItemObject, self).magic_mutate_bits()
        if self.pretty_type == 'weapon':
            for i in range(14):
                mask = 1 << i
                xor = old_equip ^ self.equipability
                if (mask & xor and random.random()**2 > random_degree):
                    self.equipability = (self.equipability | mask) ^ mask
                    self.equipability |= (old_equip & mask)

        if self.is_equipable and not self.equipability & 0x3fff:
            self.equipability |= self.old_data['equipability'] & 0x3fff

        self.equipability = (self.equipability | 0x4000) ^ 0x4000
        self.equipability |= (self.old_data['equipability'] & 0x4000)

        if not self.is_equipable or 'c' not in get_flags():
            return

        mutated = self.equipability
        self.equipability &= 0xC000
        for (i, c) in enumerate(self.character_mapping[self.pretty_type]):
            if mutated & (1 << i):
                self.equipability |= (1 << c)

    def cleanup(self):
        if self.pretty_type not in ['armor', 'shield', 'helm', 'relic']:
            for attribute in ['elements', 'elemabsorbs',
                              'elemnulls', 'elemweaks']:
                setattr(self, attribute, self.old_data[attribute])
            if 'q' in get_flags():
                self.set_bit('swdtech', True)
                self.set_bit('runic_percentage', True)

        if not self.is_equipable:
            attrs = [a for (a, b, c) in self.specs.attributes]
            assert 'price' in attrs
            for a in attrs:
                if a != 'price':
                    setattr(self, a, self.old_data[a])

        if self.price > 100 and 'i' in get_flags():
            price = self.price * 2
            counter = 0
            while price >= 100:
                price //= 10
                counter += 1
            price *= (10**counter)
            self.price = price // 2

        if self.price < 10 and self.old_data['price'] <= 2:
            self.price = self.old_data['price']

        if self.is_equipable and 'q' in get_flags():
            assert (self.equipability & 0x4000 ==
                    self.old_data['equipability'] & 0x4000)
            if self.command_changes:
                equip_mask = 0
                for cc in self.command_changes:
                    for c in CharacterObject.every[:14]:
                        if cc.command in c.commands:
                            equip_mask |= (1 << c.index)
                equip_mask |= 0x1000
                self.equipability = equip_mask

            if self.equipability & 0xbfff == 0xbfff:
                self.equipability ^= 0x8000

        if 'BNW' in get_global_label() and 'Moogle_Charm' in self.name:
            self.equipability |= 0x3fff

        if (self.learnrate > 0 and 'a' in get_flags() and 'q' in get_flags()
                and self.is_equipable and self.pretty_type != 'weapon'):
            raise NotImplementedError("Esper allocation not in randomizer")
            """equipability = self.equipability & 0xfff
            learnability = 0
            for i in range(14):
                spells = CharEsperObject.get_character_spells(i)
                if self.learnspell in spells:
                    learnability |= (1 << i)
            both = equipability & learnability
            if both:
                self.equipability &= 0xf000
                self.equipability |= both
            elif bin(equipability).count('1') > bin(learnability).count('1'):
                self.equipability &= 0xf000
                self.equipability |= learnability"""

        if 'fanatix' in get_activated_codes():
            if self.index in [0xF6, 0xF7]:
                self.price = 0
                self.otherproperties = 0
                self.itemtype = 6



class ItemNameObject(EncodeDecodeMixin):
    @property
    def name(self):
        return to_ascii(self.name_text)

    def emphasize(self):
        name_text = self.name_text.rstrip(b'\xff')
        if 'JP' not in get_global_label():
            name_text = name_text[:12]
            name_text += b'\xca'
        else:
            name_text = name_text[:8]
            name_text += b'\xd3'
        while len(name_text) < len(self.name_text):
            name_text += b'\xff'
        self.name_text = name_text


class EquipabilityObject(TableObject):
    flag = 'q'
    flag_description = 'equipment'
    custom_random_enable = 'q'


class EquipmentStatsObject(TableObject):
    flag = 'i'
    flag_description = 'equipment stats'
    custom_random_enable = 'i'


class ColosseumObject(TableObject):
    def __repr__(self):
        return '%s -> %s : %s' % (
            self.item.name, self.trade.name, self.opponent.name)

    @property
    def is_legit(self):
        if 'JP' in get_global_label():
            return self.opponent.index != 0x40
        return 'chupon' not in str(self).lower()

    @property
    def opponent(self):
        return MonsterObject.get(self.opponent_id)

    @property
    def item(self):
        return ItemObject.get(self.index)

    @property
    def trade(self):
        return ItemObject.get(self.trade_id)


class CharacterObject(TableObject):
    flag = 'c'
    flag_description = 'characters'
    custom_random_enable = True

    randomize_attributes = [
        'hp', 'mp', 'vigor', 'speed', 'stamina', 'magpwr',
        'batpwr', 'def', 'magdef', 'evade', 'mblock',
        ]
    mutate_attributes = {
        'hp': None,
        'mp': None,
        'vigor': None,
        'speed': None,
        'stamina': None,
        'magpwr': None,
        'batpwr': None,
        'def': None,
        'magdef': None,
        'evade': None,
        'mblock': None,
        }

    @classproperty
    def after_order(cls):
        return [CmdChangeFBObject]

    @property
    def intershuffle_valid(self):
        return self.index < 12

    @property
    def name(self):
        return to_ascii(CharNameObject.get(self.index).name_text)

    @property
    def old_initial_equipment_ids(self):
        return ([self.old_data[attr]
                 for attr in ['weapon', 'shield', 'helm', 'armor']]
                + self.old_data['relics'])

    @property
    def old_initial_equipment(self):
        return [ItemObject.get(i)
                for i in self.old_initial_equipment_ids if i <= 0xFE]

    @classproperty
    def valid_commands(cls):
        if hasattr(CharacterObject, '_valid_commands'):
            return CharacterObject._valid_commands

        valid_commands = set([])
        seen_commands = set([])
        for char in CharacterObject.every:
            for c in char.commands:
                if c <= 0x1f:
                    if char.index < 14:
                        valid_commands.add(c)
                    seen_commands.add(c)
        for c in CmdChangeFBObject.every:
            if c.command in valid_commands:
                command = CmdChangeTBObject.get(c.index).command
                valid_commands.add(command)
                seen_commands.add(command)
        for command in [0x19, 0x1a, 0x1b]:
            if command in seen_commands:
                valid_commands.add(command)
        if 'BNW_2' not in get_global_label():
            valid_commands.add(0x1d)
        for command in [0x00, 0x01, 0x02, 0x11, 0xff]:
            if command in valid_commands:
                valid_commands.remove(command)
        CharacterObject._valid_commands = sorted(valid_commands)

        return CharacterObject.valid_commands

    @classproperty
    def current_initial_commands(cls):
        seen_commands = set([])
        for char in CharacterObject.every:
            if char.index < 14:
                seen_commands |= set(char.commands)
        if 0xFF in seen_commands:
            seen_commands.remove(0xFF)
        return seen_commands

    def randomize_commands(self):
        raise NotImplementedError("To import!")
        """if CmdChangeFBObject.flag not in get_flags() or self.index in [12, 13]:
            return

        if not hasattr(CharacterObject, '_done_commands'):
            CharacterObject._done_commands = set([0, 2, 1])

        if self.index > 13 or 'wildcommands' not in get_activated_codes():
            commands = [c for c in self.old_data['commands']
                        if c in [0x00, 0x02, 0x11, 0x01]]
            if 0x11 in commands and 0x00 not in commands:
                commands.remove(0x11)
                commands.insert(0, 0)
        else:
            while True:
                commands = []
                if random.choice([True, True, False]):
                    commands.append(0x00)
                if random.choice([True, True, False]):
                    commands.append(0x02)
                if random.choice([True, True, False]):
                    commands.append(0x01)
                if 0x00 in commands or 0x01 in commands:
                    break

        if not commands:
            return

        while len(commands) < 4:
            valid_commands = CharacterObject.valid_commands
            if (self.index <= 0xc
                    and 'wildcommands' not in get_activated_codes()):
                valid_commands = [c for c in valid_commands
                                  if c not in CharacterObject._done_commands]
            chosen = random.choice(valid_commands)
            if chosen not in commands:
                if commands[0] == 0x00:
                    commands.insert(1, chosen)
                else:
                    commands.insert(0, chosen)

        NO_RAGE_PATCH = True
        for patchfilename in get_activated_patches():
            if 'patch_auto_learn_rage' in patchfilename.lower():
                NO_RAGE_PATCH = False
                break

        assert not NO_RAGE_PATCH
        if not NO_RAGE_PATCH:
            assert 0x11 not in commands

        self.commands = commands
        if self.index <= 0xc:
            CharacterObject._done_commands |= set(self.commands)"""

    def randomize(self):
        self.reseed('rand_escape')
        if self.index < 14:
            c = CharacterObject.get(random.randint(0, 14))
            escape = c.old_data['level_escape'] & 3
            c.level_escape = (c.level_escape & 0xFC) | escape
        super(CharacterObject, self).randomize()

    def cleanup(self):
        if self.index < 14:
            for attr in ['weapon', 'shield', 'helm', 'armor']:
                index = getattr(self, attr)
                if index == 0xFF:
                    continue
                item = ItemObject.get(index)
                if not item.equipability & (1 << self.index):
                    candidates = [
                        i for i in ItemObject.ranked if i.pretty_type == attr
                        and i.rank >= 0
                        and (i.is_buyable or i.is_initial_equipment)
                        and i.equipability & (1 << self.index)]
                    if candidates:
                        setattr(self, attr, candidates[0].index)
                    else:
                        setattr(self, attr, 0xff)
            for (i, r) in enumerate(self.relics):
                if r == 0xFF:
                    continue
                item = ItemObject.get(r)
                if not item.equipability & (1 << self.index):
                    self.relics[i] = 0xFF

        if 'fanatix' in get_activated_codes():
            self.level_escape &= 0xF3
            if self.index == 0x0E:
                if get_global_label() not in ['FF6_NA_1.0', 'FF6_NA_1.1',
                                              'FF6_JP']:
                    self.level_escape |= 0x08
                self.relics = [0xFF, 0xFF]
                for attr in ['weapon', 'shield', 'helm', 'armor']:
                    setattr(self, attr, 0xFF)

        if self.index == 0x1b and 't' in get_flags():
            self.weapon = 0x29

        if 'o' in get_flags():
            if 'FF6_NA' in get_global_label():
                assert 'patch_auto_learn_rage.txt' in get_activated_patches()
                assert 0x11 not in self.commands
            if 'FF6_JP' in get_global_label():
                assert ('patch_auto_learn_rage_jp.txt'
                        in get_activated_patches())
                assert 0x11 not in self.commands


class CharNameObject(EncodeDecodeMixin): pass


class CmdChangeMixin(object):
    @property
    def equipment_bit(self):
        i = (4-self.index) + 2
        return (1 << i)

class CmdChangeFBObject(TableObject, CmdChangeMixin):
    flag = 'o'
    flag_description = 'character commands'

    def __repr__(self):
        return '{0:0>2X} -> {1:0>2X}'.format(
            self.command, CmdChangeTBObject.get(self.index).command)

    @classmethod
    def randomize_all(cls):
        cls.class_reseed('rand_commands')
        if CmdChangeFBObject.flag in get_flags():
            if get_global_label() in ['FF6_NA_1.0', 'FF6_NA_1.1']:
                write_patch(get_outfile(), 'patch_auto_learn_rage.txt')
            if 'BNW' in get_global_label():
                write_patch(get_outfile(), 'patch_auto_learn_rage.txt')
            if 'JP' in get_global_label():
                write_patch(get_outfile(), 'patch_auto_learn_rage_jp.txt')
        for c in CharacterObject.every:
            assert not hasattr(c, 'randomized')
            c.randomize_commands()
        super().randomize_all()

    def randomize(self):
        valid_commands = sorted(CharacterObject.current_initial_commands)
        self.command = random.choice(valid_commands)

class CmdChangeTBObject(TableObject, CmdChangeMixin):
    @classproperty
    def after_order(cls):
        return [CharacterObject, CmdChangeFBObject]

    def randomize(self):
        from_command = CmdChangeFBObject.get(self.index).command
        existing_commands = sorted(CharacterObject.current_initial_commands)
        potential_commands = [c for c in CharacterObject.valid_commands
                              if c not in existing_commands]
        if from_command in potential_commands:
            potential_commands.remove(from_command)
        seen_commands = [tb.command for tb in CmdChangeTBObject.every
                         if hasattr(tb, 'randomized') and tb.randomized]
        temp = [c for c in potential_commands if c not in seen_commands]
        if temp:
            potential_commands = temp
        companion = CmdChangeFBObject.get(self.index)
        if self.command in existing_commands and (
                potential_commands or companion.command == self.command
                or random.choice([True, False])):
            if not potential_commands:
                banned_commands = {self.companion.command}
                for c in CharacterObject.every[:14]:
                    if self.companion.command in c.commands:
                        banned_commands |= set(c.commands)
                for c in CharacterObject.every[:14]:
                    if (self.companion.command in c.commands
                            and 0x02 not in c.commands
                            and 0x17 not in c.commands):
                        banned_commands -= {0x02, 0x17}
                potential_commands = [c for c in existing_commands
                                      if c not in banned_commands]
                if not potential_commands:
                    potential_commands = existing_commands

            self.command = random.choice(potential_commands)

    @classmethod
    def randomize_all(cls):
        CmdChangeTBObject.class_reseed('ran_order')
        objs = list(CmdChangeTBObject.every)
        random.shuffle(objs)
        for o in objs:
            if hasattr(o, 'randomized') and o.randomized:
                continue
            o.reseed(salt='ran')
            o.randomize()
            o.randomized = True


class ChestObject(TableObject):
    flag = 't'
    flag_description = 'treasure'
    custom_random_enable = True

    @property
    def memid(self):
        memid = self.memid_low
        if self.get_bit('memid_high'):
            memid |= 0x100
        return memid

    @property
    def mutate_valid(self):
        return self.rank is not None and self.rank >= 0

    def set_memid(self, index):
        assert index <= 0x1FF
        if self.index & 0x100:
            self.set_bit('memid_high', True)
        else:
            self.set_bit('memid_high', False)
        self.memid_low = index & 0xFF

    @cached_property
    def old_treasure(self):
        if self.old_data['misc'] & 0x40:
            return ItemObject.get(self.old_data['contents'])
        return None

    @cached_property
    def old_formation(self):
        if self.old_data['misc'] & 0x20:
            return TwoPackObject.get(self.old_data['contents'])
        return None

    @cached_property
    def rank(self):
        item = None
        if self.old_treasure:
            item = self.old_treasure
        if self.old_formation:
            item = self.old_formation.guaranteed_treasure
            if item is None:
                rank = (self.old_formation.ranked_ratio**2
                        if self.old_formation.ranked_ratio is not None else -1)
                return rank

        if item:
            return item.ranked_ratio if item.ranked_ratio is not None else -1

        if self.old_data['misc'] & 0x80:
            return self.old_data['contents'] / 655.35
        else:
            return 0

    def set_contents(self, item):
        for bitname in ['gold', 'treasure', 'monster', 'empty1', 'empty2']:
            self.set_bit(bitname, False)
        if isinstance(item, ItemObject):
            self.set_bit('treasure', True)
            item = item.index
        elif isinstance(item, TwoPackObject):
            self.set_bit('monster', True)
            item = item.index
        elif isinstance(item, int):
            self.set_bit('gold', True)
        else:
            raise NotImplementedError
        self.contents = item

    def mutate(self):
        if not hasattr(ChestObject, '_done_miabs'):
            ChestObject._done_miabs = set()

        candidates = [c for c in ChestObject.every if c.rank > 0]
        chosen_type = random.choice(candidates)
        if chosen_type.old_treasure:
            candidates = ItemObject.ranked
        elif chosen_type.old_formation:
            if chosen_type.old_formation.guaranteed_treasure:
                candidates = [tp for tp in TwoPackObject.ranked
                              if tp.guaranteed_treasure]
            else:
                candidates = TwoPackObject.ranked
            candidates = [c for c in candidates
                          if c not in ChestObject._done_miabs]
            if not candidates:
                chosen_type = [c for c in ChestObject.every
                               if c.old_treasure][0]
                candidates = ItemObject.ranked
        else:
            # gold
            candidates = None
            value = (self.ranked_ratio**2) * 255
            value = mutate_normal(value, 0, 255, wide=True,
                                  random_degree=self.random_degree)
            value = min(255, int(round(value)))
            self.set_contents(value)
            return

        candidates = [c for c in candidates
                      if c.rank >= 0 and c.ranked_ratio is not None]
        max_index = len(candidates)-1
        if chosen_type.old_treasure:
            index = len([c for c in candidates
                         if c.ranked_ratio <= self.ranked_ratio]) - 1
        else:
            index = len([c for c in candidates
                         if c.ranked_ratio <= self.ranked_ratio**0.5]) - 1
        index = max(index, 0)
        index = mutate_normal(index, 0, max_index, wide=True,
                              random_degree=self.random_degree)
        chosen = candidates[index]
        if isinstance(chosen, TwoPackObject):
            ChestObject._done_miabs.add(chosen)
        self.set_contents(chosen)

    @classmethod
    def mutate_all(cls):
        ChestObject.class_reseed('chests')
        ordering = list(ChestObject.every)
        random.shuffle(ordering)
        for o in ordering:
            if hasattr(o, "mutated") and o.mutated:
                continue
            o.reseed(salt="mut")
            if o.mutate_valid:
                o.mutate()
            o.mutated = True

    def cleanup(self):
        if not hasattr(self, 'old_data'):
            return

        for c in ChestObject.every:
            if c.index >= self.index:
                break
            if not hasattr(c, 'old_data'):
                continue
            if (c.memid == self.memid
                    and c.old_data['misc'] == self.old_data['misc']
                    and c.old_data['contents'] == self.old_data['contents']):
                self.misc = c.misc
                self.contents = c.contents
                break


class ShopObject(TableObject):
    flag = 'p'
    flag_description = 'shops'
    #custom_random_enable = True

    def __repr__(self):
        s = '%s SHOP %x\n' % (self.shop_type.upper(), self.index)
        for i in self.items:
            s += '%s %s\n' % (str(i), i.price)
        return s.strip()

    @property
    def items(self):
        return [ItemObject.get(i) for i in self.item_ids if i < 0xFF]

    @property
    def old_items(self):
        return [ItemObject.get(i) for i in self.old_data['item_ids']
                if i < 0xFF]

    @property
    def shop_type(self):
        shop_types = {1:'weapons', 2:'armor', 3:'items', 4:'relics', 5:'misc'}
        return shop_types[self.misc & 0x7]

    @property
    def rank(self):
        if len(self.old_items) <= 0:
            return -1
        if set(self.old_data['item_ids']) == {255}:
            return -1
        return max(i.price for i in self.old_items)

    @property
    def current_rank(self):
        if len(self.items) <= 0:
            return -1
        if set(self.item_ids) == {255}:
            return -1
        return sum(i.price for i in self.items) / float(len(self.items))

    @classproperty
    def consumables(cls):
        if hasattr(ShopObject, '_consumables'):
            return ShopObject._consumables
        consumables = set([])
        for s in ShopObject.every:
            if s.shop_type == 'items':
                consumables |= set(s.old_items)
        ShopObject._consumables = sorted(consumables, key=lambda i: i.index)
        return ShopObject.consumables

    def mutate(self):
        items = list(self.items)
        num_items = len(items)
        if num_items <= 0:
            return
        candidate_shops = [
            s for s in ShopObject.every if s.shop_type == self.shop_type
            or (self.shop_type == 'misc' and s.shop_type == 'items')]
        candidate_shops = [c for c in candidate_shops
                           if c.rank >= 0 and len(c.old_items) > 0]
        num_items = len(random.choice(candidate_shops).old_items)
        num_items = mutate_normal(num_items, 1, 8, wide=False,
                                  random_degree=self.random_degree)

        candidates = []
        for s in candidate_shops:
            candidates.extend(s.old_data['item_ids'])
        candidates = [c for c in candidates if c != 0xff]

        new_items = []
        while len(new_items) < num_items:
            remaining = num_items - len(new_items)
            new_items += random.sample(candidates, remaining)
            new_items = sorted(set(new_items))
            candidates = [c for c in candidates if c not in new_items]

        new_items = sorted(set(new_items))

        if self.index == 0xc and 0xfe in self.old_data['item_ids']:
            # dried meat in mobliz
            if len(new_items) == 8:
                new_items.remove(random.choice(new_items))
            max_index = len(new_items)-1
            new_items.insert(random.randint(0, max_index), 0xfe)

        while len(new_items) < 8:
            new_items.append(0xff)

        assert len(new_items) == 8
        self.item_ids = new_items

    def cleanup(self):
        self.reseed('cleanup')
        if 'fanatix' in get_activated_codes() and self.shop_type == 'items':
            for banned_id in [0xF6, 0xF7]:
                if banned_id not in self.item_ids:
                    continue
                consumables = [i for i in self.consumables
                               if i.index not in self.item_ids]
                i = random.choice(consumables)
                self.item_ids.remove(banned_id)
                self.item_ids.append(i.index)
        self.item_ids = sorted(self.item_ids)


class SkillObject(TableObject):
    bit_similarity_attributes = {
        'targeting': 0xff,
        'elements': 0xff,
        'misc1': 0xff,
        'misc2': 0xff,
        'misc3': 0xff,
        'statuses': 0xffffffff,
        }

    STATUS_NAMES = [
        'blind', 'zombie', 'poison', 'magitek',
        'clear', 'imp', 'petrify', 'wound',

        'condemned', 'near fatal', 'image', 'mute',
        'berserk', 'muddled', 'seizure', 'sleep',

        'dance', 'regen', 'slow', 'haste',
        'stop', 'shell', 'safe', 'reflect',

        'rage', 'freeze', 'life 3', 'morph',
        'control', 'hide', 'interceptor', 'float'
        ]

    ELEMENT_NAMES = [
        'fire', 'ice', 'bolt', 'poison',
        'wind', 'pearl', 'earth', 'water',
        ]

    OPPOSITE_ELEMENTS = {
        'fire':     ('ice', 'water',),
        'ice':      ('fire',),
        'bolt':     ('water',),
        'poison':   ('pearl',),
        'wind':     ('earth',),
        'pearl':    ('poison',),
        'earth':    ('wind',),
        'water':    ('fire', 'bolt'),
        }

    @property
    def rank(self):
        return self.mp

    @property
    def name(self):
        return names.skills[self.index]

    @property
    def tags(self):
        tags = set()
        for i in range(8):
            if self.elements & (1 << i):
                tags.add(self.ELEMENT_NAMES[i])

        for t in sorted(tags):
            if t in self.OPPOSITE_ELEMENTS:
                for t2 in self.OPPOSITE_ELEMENTS[t]:
                    if t2 not in tags:
                        tags.add('-%s' % t2)

        if not self.get_bit('cure_status'):
            for i in range(32):
                if self.statuses & (1 << i):
                    tags.add(self.STATUS_NAMES[i])

        if self.power and not any(
                [self.elements, self.get_bit('percentage'),
                 self.get_bit('physical'), self.get_bit('draining'),
                 self.get_bit('concerns_mp'), self.get_bit('healing')]):
            tags.add('nuke')

        if self.get_bit('draining'):
            tags.add('drain')

        if self.get_bit('physical'):
            tags.add('physical')

        death_bit = 1 << (self.STATUS_NAMES.index('wound'))

        if self.statuses & death_bit:
            if self.get_bit('cure_status'):
                tags.add('life')
            else:
                tags.add('death')

        if self.get_bit('healing') and not self.statuses & death_bit:
            tags.add('heal')

        if self.get_bit('miss_if_death_prot'):
            tags.add('death')

        death_bit |= 1 << (self.STATUS_NAMES.index('hide'))
        if self.statuses & (0xffffffff ^ death_bit):
            tags.add('status')
            if self.get_bit('cure_status'):
                tags.add('heal')
            else:
                if self.get_bit('target_enemy_default'):
                    tags.add('debuff')
                    tags.add('-buff')
                else:
                    tags.add('buff')
                    tags.add('-debuff')

        if tags >= {'buff', 'debuff'}:
            tags -= {'-buff', '-debuff'}

        if self.get_bit('concerns_mp'):
            tags.add('mp')

        if 'wound' in tags:
            tags -= {'hide'}

        return sorted(tags)


class OverworldRateObject(TableObject): pass
class DungeonRateObject(TableObject): pass

    
def handle_exhirom():
    with open(get_outfile(), 'r+b') as f:
        f.seek(0)
        block = f.read(0x10000)
        #f.seek(0x400000)
        #empty = f.read(0x10000)
        #assert empty in [block, b'\x00'*0x10000]
        f.seek(0x400000)
        f.write(block)


def export_all(object_list):
    from os import mkdir
    import json
    EXPORT_DIRECTORY = 'exported'
    try:
        mkdir(EXPORT_DIRECTORY)
    except FileExistsError:
        pass
    for obj in object_list:
        if not hasattr(obj, 'specs'):
            continue
        name = obj.__name__
        print(name)
        fn = path.join(EXPORT_DIRECTORY, 'data.%s.json' % name)
        data = obj.export_all()
        with open(fn, 'w+') as f:
            f.write(json.dumps(data, indent=4))


def import_all(object_list, dirname='import'):
    from os import listdir
    import json
    for fn in listdir(dirname):
        if not (fn.startswith('data.') and fn.endswith('.json')):
            continue
        _, name, _ = fn.split('.')
        objs = [o for o in object_list if o.__name__ == name]
        assert len(objs) == 1
        obj = objs[0]
        fpath = path.join(dirname, fn)
        with open(fpath) as f:
            data = json.loads(f.read())
        obj.import_all(data)


if __name__ == '__main__':
    try:
        print('You are using the Beyond Chaos Gaiden '
              'randomizer version %s.' % VERSION)

        ALL_OBJECTS = [g for g in globals().values()
                       if isinstance(g, type) and issubclass(g, TableObject)
                       and g not in [TableObject]]

        codes = {}

        run_interface(ALL_OBJECTS, snes=True, codes=codes,
                      custom_degree=True, custom_difficulty=True)

        if 'export' in get_activated_codes():
            export_all(ALL_OBJECTS)

        for code in sorted(get_activated_codes()):
            print('Code "%s" activated.' % code)

        # to verify
        # handle_exhirom()

        clean_and_write(ALL_OBJECTS)
        rewrite_snes_meta('BCG-R', VERSION, lorom=False)

        finish_interface()

    except Exception:
        print('ERROR: %s' % format_exc())
        input('Press Enter to close this program. ')