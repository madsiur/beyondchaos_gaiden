# Final Fantasy 6 Beyond Chaos Gaiden Randomizer (RotDS compatible)
RotDS fork:         https://github.com/madsiur/beyondchaos_gaiden  
Original project:   https://github.com/abyssonym/beyondchaos_gaiden

## How to use

### Running the randomizer

Please run the command `python radorotds.py` using Python version 3.

### Source rom file

This randomizer is compatible with the following rom:

RotDS v2.13 `4fe96929641b7ced018daa847dd33881`

### Seed value
    
Input a numerical seed value here, or leave it blank if you don't care.

### Flags

`m`  Randomize monsters.

Right now only the `m` flag has been tested for the RotDS hack. Use other flags or the "randomize all" option at your own risk.

### Codes

You can enter codes when you enter flags. For example, `m printme` would randomize monsters and activate the `printme` code. These are the currently available codes:

`printme`   Produce text files of the printable objects in the `printme` directory.

### Randomness
The "randomness" option controls how extreme the randomizations are. At 0.0, almost nothing will be randomized. At 1.0, enemies in the starting area will most likely have boss stats. I suggest leaving it at the default setting of 0.5 for your first run. It is possible to use different settings for different flags. Type "custom" to enable more detailed randomness settings. This is useful, for example, when you want to find high-level gear without fighting high-level enemies.

### Output files

The randomizer will output a new, randomized rom with the seed in the filename.

### Special Thanks
- Assassin17          SrBehemoth rows, control menu MP, formation randomosity, magic damage overflow, rage/mute fix, freeze/morph running animation fix, stacking immunities fix, step mine MP fix, and Gogo yellow streak patches
- Bropedio            Informative miss patch
- darknil             Improved shop preview patch, Regen/Rerise status display patch
- emberling           Music and character palette randomization
- FF6Hacking          Flash tool animation fix patch
- GrayShadows         Combined equipment/relic menu, condensed spell list, and ATB/Max HP select toggle patches
- HatZen08            Colosseum rewards display patch
- Imzogelmo           MP color digits patch
- Leet Sketcher       Color wheel, Y equip relics, vanish/runic, and imp skimp patches
- Myria               Improved party gear screen patch
- myself086           Dance descriptions, item descriptions, status screen, and item/rage locking patches
- Novalia Spirit      Auto-float/interceptor fix and selective re-equip patches
- Seibaby             ATB color gauge patch
- SilentEnigma        Alphabetical Lore, description disruption fix, MP color digits, docile NPCs, Siegfried/Chupon rages, and soft reset patches
- subtractionsoup     Beyond Chaos co-developer, Y equip relics bugfix
- synchysi            Esper allocation patch (base)
- Terii Senshi        Documentation of bank C2
- vivify93            Total graphics uncensorship patch
