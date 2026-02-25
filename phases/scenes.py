"""
Content Reactor — Scene Engine v8
Per-brand scene packs: each brand has its own figures, stories, moods, themes.
Falls back to hardcoded knight defaults if no brand scenes.json exists.
"""
import json, random
from pathlib import Path
from config import Config, log

pick = lambda arr: random.choice(arr)


# ─── BRAND SCENE LOADER ──────────────────────────────────────

def _brand_scenes_path() -> Path:
    """Get the scenes.json path for the active brand."""
    from server import brand_dir
    return brand_dir() / "scenes.json"


def load_brand_scenes() -> dict | None:
    """Load scenes.json for the active brand. Returns None if not found."""
    path = _brand_scenes_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            log.info(f"   🎭 Brand scenes loaded: {path} ({len(data.get('stories', []))} stories, {len(data.get('figures', []))} figures)")
            return data
        except Exception as e:
            log.warning(f"   Failed to load brand scenes: {e}")
    return None


def save_brand_scenes(data: dict):
    """Save scenes.json for the active brand."""
    path = _brand_scenes_path()
    path.write_text(json.dumps(data, indent=2))
    log.info(f"   Scenes saved to {path}")


def export_default_scenes() -> dict:
    """Export the hardcoded knight scene data as a dict (for seeding new brands)."""
    return {
        "figures": list(FIGURES),
        "themes": dict(THEME_KEYWORDS),
        "moods": dict(IMAGE_SUFFIXES),
        "intensity": dict(INTENSITY_MODIFIERS),
        "cameras": dict(CAMERA_STYLES),
        "stories": list(STORY_SEEDS),
    }


def get_scene_data() -> tuple:
    """Get scene data for the active brand.
    Returns (figures, themes, moods, intensity, cameras, stories).
    Tries brand scenes.json first, falls back to hardcoded knights.
    """
    brand = load_brand_scenes()
    if brand:
        figures   = brand.get("figures", FIGURES)
        themes    = brand.get("themes", THEME_KEYWORDS)
        moods     = brand.get("moods", IMAGE_SUFFIXES)
        intensity = brand.get("intensity", INTENSITY_MODIFIERS)
        cameras   = brand.get("cameras", CAMERA_STYLES)
        stories   = brand.get("stories", STORY_SEEDS)
        return figures, themes, moods, intensity, cameras, stories
    # Fallback: hardcoded knight defaults
    return FIGURES, THEME_KEYWORDS, IMAGE_SUFFIXES, INTENSITY_MODIFIERS, CAMERA_STYLES, STORY_SEEDS

THEME_KEYWORDS = {
    "temptation": ["tempt","lust","desire","flesh","crave","hunger","pull","urge","resist","want","pleasure","indulge","forbidden"],
    "endurance": ["endure","tired","weary","exhaust","fatigue","press on","keep going","persist","carry","weight","heavy","burden","grind","worn"],
    "doubt": ["doubt","fear","uncertain","question","waver","hesitat","lost","confused","wonder","shake","weak","fail","falling","anxiety"],
    "discipline": ["disciplin","routine","habit","daily","practice","train","prepare","ready","order","structure","ritual","commit","consistent"],
    "courage": ["courage","brave","bold","stand","rise","fight","warrior","strong","strength","power","lion","fire","forge","iron","conquer","victory"],
    "duty": ["duty","responsib","protect","guard","watch","serve","family","wife","children","son","father","husband","provide","lead","sacrifice"],
    "loss": ["loss","lost","grief","pain","suffer","wound","broken","fall","fallen","hurt","scar","dark","night","shadow","alone","death","gone"],
    "patience": ["wait","patient","still","quiet","silent","peace","calm","rest","trust","faith","pray","kneel","surrender","submit","obey"],
    "anger": ["anger","rage","fury","wrath","burn","fire","destroy","control","contain","restrain","channel","storm","thunder","bitter"],
    "identity": ["who you are","identity","purpose","call","chosen","anointed","crown","king","knight","armor of god","ephesians","helmet"],
}

FIGURES = [
    "a battle-scarred knight in dented steel plate armor, torn dark cape, closed scratched helm",
    "a lone knight in battered grey steel armor, heavy mud-stained cape, weathered closed helm",
    "a medieval warrior in blackened steel plate, tattered cape in shreds, scarred closed helm",
    "a weary knight in ancient dulled steel plate, faded torn surcoat, heavy hooded cape, scratched helm",
    "a solitary knight in tarnished steel armor, stained campaign cape, closed dented helm",
]

IMAGE_SUFFIXES = {
    "storm": "Cinematic dark atmosphere, cold blue-grey tones, rain, fog, 9:16 vertical.",
    "fire": "Cinematic dark atmosphere, orange ember glow against darkness, smoke, ash particles, 9:16 vertical.",
    "dawn": "Cinematic golden hour light, warm amber highlights, cold shadows, fog, 9:16 vertical.",
    "night": "Cinematic moonlit scene, silver-blue cold tones, deep shadows, mist, 9:16 vertical.",
    "grey": "Cinematic overcast atmosphere, muted grey tones, rain, wet surfaces, 9:16 vertical.",
    "battle": "Cinematic dark atmosphere, smoke, distant fire, debris, dramatic lighting, 9:16 vertical.",
}

INTENSITY_MODIFIERS = {
    "still": "Minimal movement. Near-static frame. Subtle breathing and cape drift only. Contemplative stillness.",
    "measured": "Slow deliberate motion. Controlled pacing. Weighted purposeful movement.",
    "dynamic": "Fast aggressive motion. Explosive energy. Rapid camera movement. Combat intensity. Urgent momentum.",
}

CAMERA_STYLES = {
    "steady": "Steady camera.",
    "dynamic": "Dynamic cinematic camera movement.",
    "handheld": "Handheld shaky camera, raw documentary feel.",
}


# All 21 story seeds from the n8n Scene Engine v6
STORY_SEEDS = [
    {"name":"last_stand_defeat","themes":["loss","endurance","courage"],"mood":"battle","clips":[
        {"action":"kneels on the muddy battlefield, greatsword thrust blade-down into the ground","setting":"devastated battlefield at blood-red dawn, broken weapons and toppled siege engines scattered around him","lighting":"blood-red dawn light raking across the battlefield from the horizon","atmosphere":"smoke drifting low across the ground","composition":"Low angle wide shot","camera":"Slow pull back","subject":"Knight's shoulders drop with exhaustion","ambient":"Smoke drifts across frame","pace":"Heavy weighted motion."},
        {"action":"stands alone on the ruined battlefield, sword at his side","setting":"open battlefield at dawn, fallen banners and debris stretching to the horizon","lighting":"blood-red dawn sky behind him, dark foreground","atmosphere":"smoke and ash hanging in the air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight shifts weight, head turns slowly","ambient":"Smoke drifts past him","pace":"Steady motion."},
        {"action":"raises his sword overhead with both hands on the empty battlefield","setting":"open battlefield, shattered shield at his feet","lighting":"dark red dawn light from behind","atmosphere":"smoke rising in the distance","composition":"Side profile full body","camera":"Side profile, slow push-in","subject":"Knight lifts sword slowly overhead","ambient":"Smoke drifts behind him","pace":"Controlled motion."},
    ]},
    {"name":"last_man_standing","themes":["courage","endurance","loss"],"mood":"dawn","clips":[
        {"action":"stands at the crest of a ridge, hand resting on his sword hilt","setting":"ridge overlooking a wide valley at first dawn","lighting":"golden dawn light breaking through low clouds","atmosphere":"morning fog in the valley below","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight turns head slowly toward the valley","ambient":"Cape drifts in morning wind","pace":"Slow smooth motion."},
        {"action":"stands on the ridge looking out over the empty valley below","setting":"ridge above empty battlefield, amber morning sky stretching behind him","lighting":"amber dawn light on his armor","atmosphere":"mist in the valley below","composition":"Three-quarter rear view","camera":"Slow pan left to right","subject":"Knight adjusts grip on sword hilt","ambient":"Cape moves in morning wind","pace":"Slow smooth motion."},
        {"action":"walks forward along the ridge toward the rising sun","setting":"ridge crest, open golden sky ahead, long shadow behind him","lighting":"golden sun rising directly ahead of him","atmosphere":"morning mist burning off the ridge below","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks forward, deliberate steps","ambient":"Cape billows behind him","pace":"Steady motion."},
    ]},
    {"name":"dawn_march","themes":["courage","duty","endurance"],"mood":"dawn","clips":[
        {"action":"stands at the head of a dark road, shield on his arm, sword at his hip","setting":"dark road at pre-dawn, mist filling the valley stretching ahead","lighting":"pale pre-dawn grey light, horizon barely brightening","atmosphere":"mist drifting across the road","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight rolls shoulders forward, settling armor","ambient":"Mist drifts past him","pace":"Slow smooth motion."},
        {"action":"strides down a muddy road through rolling hills","setting":"winding country road, dawn horizon warming ahead of him","lighting":"warm amber dawn light on the horizon","atmosphere":"morning mist low on the fields","composition":"Side profile full body","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Cape flows behind him","pace":"Steady motion."},
        {"action":"crests a hill, pausing at the top","setting":"hilltop at full dawn, stone fortress silhouetted in the far distance","lighting":"golden dawn light flooding the scene from the east","atmosphere":"morning haze between him and the distant fortress","composition":"Low angle full body","camera":"Pull back reveals knight on hill crest","subject":"Knight plants sword tip on the ground","ambient":"Cape drifts in wind","pace":"Slow smooth motion."},
    ]},
    {"name":"outnumbered_ridge","themes":["courage","doubt","duty"],"mood":"storm","clips":[
        {"action":"stands alone on a ridge, sword at his hip","setting":"exposed ridge top, dark storm clouds churning overhead","lighting":"flat grey storm light, lightning flashing in the far distance","atmosphere":"rain beginning to fall, fog rolling in from behind","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight draws sword slowly from hip","ambient":"Storm clouds roll in behind him","pace":"Controlled motion."},
        {"action":"grips his drawn sword with both hands, braced against the storm","setting":"exposed ridge in full storm, dark sky above and below","lighting":"lightning blazing across the sky behind him","atmosphere":"rain hammering his armor and the ground","composition":"Extreme close-up on gauntlet gripping sword","camera":"Close on gauntlet gripping sword hilt","subject":"Knuckles tighten on the hilt","ambient":"Rain pounds the ground","pace":"Controlled motion."},
        {"action":"holds his ground, cape torn and snapping in the gale","setting":"ridge in the full storm, dark clouds pressing down","lighting":"cold flat grey storm light from above","atmosphere":"rain pouring from his helm, wind tearing at his cape","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight holds ground, cape whips violently","ambient":"Rain falls heavy around him","pace":"Controlled motion."},
    ]},
    {"name":"vigil_before_battle","themes":["discipline","patience","duty"],"mood":"night","clips":[
        {"action":"kneels on the stone floor, head bowed","setting":"small stone medieval chapel at night, altar and candle before him","lighting":"single candle on the altar casting warm orange light on the stone","atmosphere":"deep shadows pressing in from all sides of the chapel","composition":"Wide full-body shot","camera":"Crane shot descending slowly","subject":"Knight bows head deeper toward the altar","ambient":"Candlelight flickers on the stone walls","pace":"Slow smooth motion."},
        {"action":"kneels with head bowed, sword across his knees","setting":"dark stone chapel, single candle burning low on the altar","lighting":"dim candlelight on his closed helm and shoulders","atmosphere":"deep shadows filling the room around him","composition":"Close-up on helm and chest","camera":"Close on helmet visor","subject":"Knight's gauntlet tightens on the sword across his knees","ambient":"Candle flame wavers in stillness","pace":"Slow smooth motion."},
        {"action":"stands in the stone archway of the chapel doorway, sword at his hip","setting":"stone chapel doorway, moonlit courtyard visible behind him","lighting":"moonlight from behind, faint candlelight at his back","atmosphere":"mist drifting in the courtyard beyond the doorway","composition":"Three-quarter rear view","camera":"Slow push-in from outside","subject":"Knight shifts weight forward in the archway","ambient":"Mist drifts across the doorway","pace":"Steady motion."},
    ]},
    {"name":"the_watch","themes":["duty","endurance","patience"],"mood":"night","clips":[
        {"action":"stands watch on the stone tower battlement, sword at his side","setting":"stone tower battlement at night, dark landscape stretching below","lighting":"moonlight on his armor from above","atmosphere":"stars above, cold night air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight turns head scanning the horizon","ambient":"Cape drifts in cold night wind","pace":"Slow smooth motion."},
        {"action":"holds his sword at the ready, scanning the darkness below","setting":"tower battlement at deep night, vast dark sky above, forest below","lighting":"moonlight and starlight above, total darkness below","atmosphere":"cold wind across the open battlements","composition":"Side profile full body","camera":"Slow pan across the battlements","subject":"Knight raises sword slightly, scanning below","ambient":"Cape moves in cold wind","pace":"Steady motion."},
        {"action":"stands watch as the first grey light of dawn appears at the horizon","setting":"tower battlement, pale pre-dawn grey at the horizon, night sky still above","lighting":"cold grey pre-dawn light on his armor","atmosphere":"mist in the valley below","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight lowers sword slowly to his side","ambient":"Mist drifts in the valley below","pace":"Slow smooth motion."},
    ]},
    {"name":"the_cliff_prayer","themes":["patience","doubt","identity"],"mood":"night","clips":[
        {"action":"stands at the cliff edge, arms at his sides, facing the ocean","setting":"sea cliff at night, moonlit ocean stretching below","lighting":"moonlight on his cape and shoulders from above","atmosphere":"sea wind moving his cape","composition":"Extreme wide shot from behind","camera":"Wide locked shot from behind","subject":"Knight's cape lifts heavy in the ocean wind","ambient":"Cape drifts in sea wind","pace":"Slow smooth motion."},
        {"action":"kneels at the cliff edge, head bowed toward the ocean","setting":"sea cliff at night, vast moonlit ocean below, stars above","lighting":"silver moonlight on his armor","atmosphere":"sea wind at the cliff edge","composition":"Low angle full body","camera":"Low angle looking up at the knight","subject":"Knight's shoulders rise and fall with heavy breath","ambient":"Cape moves in sea wind","pace":"Slow smooth motion."},
        {"action":"stands at the cliff edge, arms at his sides, turning away","setting":"sea cliff at night, ocean horizon stretching below and behind him","lighting":"full moonlight on his armor and cape","atmosphere":"stars blazing across the full sky above","composition":"Side profile full body","camera":"Slow push-in from behind","subject":"Knight turns slowly away from the cliff","ambient":"Cape fills frame in the wind","pace":"Steady motion."},
    ]},
    {"name":"the_long_night","themes":["endurance","patience","loss"],"mood":"night","clips":[
        {"action":"stands alone in an open field, sword at his side","setting":"open flat ground at deep night, nothing but darkness and sky","lighting":"moonlight on his armor, full dark surrounding him","atmosphere":"stars above, cold night air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight shifts weight from one leg to the other","ambient":"Cape drifts slowly in night wind","pace":"Slow smooth motion."},
        {"action":"sits with his back against a stone wall, sword across his knees","setting":"stone wall at night, moonlit open ground stretching before him","lighting":"cold moonlight on his helm from above","atmosphere":"cold still night air","composition":"Close-up on helm and chest","camera":"Close on helmet visor","subject":"Knight tilts head back against the stone wall","ambient":"Cape settles against stone wall","pace":"Heavy weighted motion."},
        {"action":"stands as pale grey light begins at the horizon, sword drawn","setting":"open ground, night sky still above, pale grey dawn at the horizon","lighting":"pale grey dawn light beginning at the far horizon","atmosphere":"mist rising from the ground","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight raises sword to ready position","ambient":"Mist rises from the ground","pace":"Steady motion."},
    ]},
    {"name":"preparation_ritual","themes":["discipline","identity","duty"],"mood":"dawn","clips":[
        {"action":"stands at a rough wooden table, gauntlets and breastplate laid out before him","setting":"stone chamber at pre-dawn, armor pieces and sword laid flat on the table","lighting":"pale grey pre-dawn light through a narrow stone window","atmosphere":"dust motes drifting in the shaft of window light","composition":"Wide full-body shot","camera":"Close on gauntlet on the table","subject":"Knight reaches for the gauntlet","ambient":"Dust drifts in window light","pace":"Slow smooth motion."},
        {"action":"pulls a chest plate strap tight, chin down","setting":"stone chamber, worn armor on his frame, narrow window behind him","lighting":"dawn light through a narrow stone window on his armor","atmosphere":"grey morning light filling the stone chamber","composition":"Close-up on gauntlet and armor on the table","camera":"Slow push-in","subject":"Knight pulls strap tight","ambient":"Cape hangs still in morning air","pace":"Steady motion."},
        {"action":"stands fully armed in the stone doorway, shield raised","setting":"stone doorway at full dawn, golden light ahead of him","lighting":"golden dawn light flooding in from outside","atmosphere":"morning mist just beyond the doorway","composition":"Front-facing medium shot","camera":"Slow push-in from outside","subject":"Knight steps forward into the doorway","ambient":"Mist drifts in the door opening","pace":"Steady motion."},
    ]},
    {"name":"the_reflection","themes":["identity","doubt","discipline"],"mood":"dawn","clips":[
        {"action":"stands at the edge of a perfectly still lake, arms at his sides","setting":"still lake at first dawn, misty treeline reflected in the water below","lighting":"first pale dawn light on the horizon, pink and grey","atmosphere":"mist drifting low on the water surface","composition":"Wide full-body shot","camera":"Slow push-in","subject":"Knight tilts head down toward the water","ambient":"Mist drifts on the water surface","pace":"Slow smooth motion."},
        {"action":"kneels at the lake edge, looking down at the still water","setting":"lake edge at dawn, still water before him, misty treeline behind","lighting":"warm golden dawn light on his armor","atmosphere":"low mist on the water surface","composition":"Low angle full body","camera":"Low angle looking up at the knight","subject":"Knight reaches gauntlet toward the water surface","ambient":"Mist drifts low on water","pace":"Slow smooth motion."},
        {"action":"stands at the lake, sword raised overhead with both hands","setting":"lake at full dawn, still water behind him reflecting the golden sky","lighting":"full golden dawn light on his armor and raised blade","atmosphere":"mist burning off the water in the morning light","composition":"Side profile full body","camera":"Side profile","subject":"Knight raises sword overhead, holds position","ambient":"Mist drifts behind him on the water","pace":"Steady motion."},
    ]},
    {"name":"the_oath","themes":["identity","duty","discipline"],"mood":"dawn","clips":[
        {"action":"kneels with his sword planted before him, both hands on the hilt","setting":"open ground at dawn, brightening horizon behind him","lighting":"golden dawn light on his bowed helm","atmosphere":"morning mist around him at ground level","composition":"Wide full-body shot","camera":"Overhead angle tilting down","subject":"Knight's grip tightens on the planted sword hilt","ambient":"Mist drifts around him","pace":"Slow smooth motion."},
        {"action":"kneels with his head bowed over his planted sword","setting":"open ground at dawn, mist at knee level around him","lighting":"warm golden dawn light on his armor","atmosphere":"mist swirling around the base of the planted sword","composition":"Overhead downward angle","camera":"Close on helmet visor","subject":"Knight bows head lower over the sword","ambient":"Mist swirls low around him","pace":"Slow smooth motion."},
        {"action":"rises with his sword raised in one hand, cape flowing","setting":"open ground at full dawn, golden sky behind him","lighting":"golden dawn light on his raised sword and armor","atmosphere":"morning mist at ground level","composition":"Side profile full body","camera":"Side profile","subject":"Knight raises sword overhead, holds position","ambient":"Cape flows in morning wind","pace":"Steady motion."},
    ]},
    {"name":"the_return","themes":["loss","endurance","patience"],"mood":"grey","clips":[
        {"action":"walks alone down a wet grey road, shoulders set forward","setting":"flat grey countryside under overcast sky, wet road stretching ahead","lighting":"flat grey overcast light, no shadows","atmosphere":"light rain falling on the road","composition":"Wide full-body shot","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Rain falls lightly around him","pace":"Heavy weighted motion."},
        {"action":"walks toward a stone wall and iron gate ahead","setting":"muddy road leading to an iron gate in a stone wall, overcast sky","lighting":"flat grey overcast light on wet stone","atmosphere":"rain on the stone and muddy ground","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks toward the gate","ambient":"Rain falls on wet ground","pace":"Heavy weighted motion."},
        {"action":"stands at the open stone gate, facing the threshold","setting":"open iron gate in stone wall, wet road behind him","lighting":"flat grey overcast light","atmosphere":"rain falling behind him on the road","composition":"Side profile full body","camera":"Slow push-in from outside","subject":"Knight steps into the doorway","ambient":"Rain falls on wet road behind him","pace":"Steady motion."},
    ]},
    {"name":"the_grave","themes":["loss","patience","duty"],"mood":"grey","clips":[
        {"action":"stands before a simple stone grave marker, arms at his sides","setting":"flat open ground under grey sky, stone marker before him, wet grass around","lighting":"flat grey overcast light, no shadows","atmosphere":"light rain falling on the wet grass","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight's head drops slowly toward the grave","ambient":"Rain falls on wet grass","pace":"Heavy weighted motion."},
        {"action":"kneels before the stone grave marker, head bowed","setting":"grave site, flat grey sky above, wet grass around him","lighting":"flat grey light, no directional shadows","atmosphere":"light rain falling on him and the stone","composition":"Overhead downward angle","camera":"Overhead angle tilting down","subject":"Knight presses gauntlet to the wet ground","ambient":"Rain falls on wet ground","pace":"Heavy weighted motion."},
        {"action":"stands from the grave, shoulders set, facing away","setting":"grave site, stone marker at his feet, grey sky behind him","lighting":"flat grey overcast light","atmosphere":"rain falling around him","composition":"Three-quarter rear view","camera":"Wide shot from behind","subject":"Knight turns away from camera","ambient":"Cape moves in grey wind","pace":"Steady motion."},
    ]},
    {"name":"crossing_the_river","themes":["courage","endurance","doubt"],"mood":"grey","clips":[
        {"action":"stands at the river bank, facing the far shore","setting":"wide grey river at the bank, overcast sky, far shore barely visible","lighting":"flat grey overcast light on the water","atmosphere":"fog on the river surface","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight steps one foot forward to the water edge","ambient":"Fog rolls across the river surface","pace":"Steady motion."},
        {"action":"wades through the river, water at his waist, sword held above the surface","setting":"mid-river crossing, grey sky above, both banks visible","lighting":"flat grey overcast light, water reflecting the sky","atmosphere":"water rushing around him","composition":"Side profile full body","camera":"Tight shot from the side","subject":"Knight wades forward, slow heavy steps","ambient":"Water flows past him","pace":"Heavy weighted motion."},
        {"action":"emerges from the river onto the far bank, water dripping from his armor","setting":"far river bank, river behind him, overcast sky above","lighting":"flat grey overcast light","atmosphere":"fog on the river behind him","composition":"Front-facing medium shot","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Fog drifts on the river behind him","pace":"Steady motion."},
    ]},
    {"name":"kneeling_in_rain","themes":["patience","loss","temptation"],"mood":"storm","clips":[
        {"action":"kneels on a stone road in the heavy rain, head bowed","setting":"stone road in storm, puddles forming around him","lighting":"dark grey storm light from above","atmosphere":"heavy rain pounding the stone and ground","composition":"Wide full-body shot","camera":"Overhead angle tilting down","subject":"Knight's shoulders heave with labored breath","ambient":"Rain pounds around him","pace":"Heavy weighted motion."},
        {"action":"kneels with both gauntleted hands pressed flat to the wet stone","setting":"stone road in storm, water rushing across the ground","lighting":"dark grey storm light","atmosphere":"water rushing across the stone road","composition":"Extreme close-up on gauntlet on wet stone","camera":"Close on gauntlet on wet stone","subject":"Knight's fingers dig into the wet stone","ambient":"Water rushes across the stone","pace":"Heavy weighted motion."},
        {"action":"rises to standing in the rain, shoulders straight","setting":"stone road in storm, dark sky above","lighting":"dark storm light from above","atmosphere":"rain falling around him","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight rises to standing","ambient":"Rain falls around him","pace":"Controlled motion."},
    ]},
    {"name":"controlled_fury","themes":["anger","discipline","courage"],"mood":"storm","clips":[
        {"action":"stands rigid in the violent storm, fists at his sides, cape snapping","setting":"open ground in a violent storm, rain hammering all around him","lighting":"dark grey storm light, lightning on the distant horizon","atmosphere":"rain hammering the ground around him","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight's fists clench tighter at his sides","ambient":"Rain pounds around him","pace":"Controlled motion."},
        {"action":"stands with gauntleted fists clenched at his sides","setting":"open ground in storm, dark sky pressing down","lighting":"lightning flash across the sky above him","atmosphere":"rain pouring from his helm","composition":"Extreme close-up on gauntlet","camera":"Close on gauntlet gripping sword hilt","subject":"Fist tightens","ambient":"Rain hammers down","pace":"Controlled motion."},
        {"action":"stands as the storm begins to ease, shoulders releasing tension","setting":"open ground, dark clouds beginning to thin above him","lighting":"faint grey light breaking through thinning clouds","atmosphere":"rain lightening around him","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight's shoulders slowly release downward","ambient":"Rain eases around him","pace":"Slow smooth motion."},
    ]},
    {"name":"the_burden","themes":["endurance","duty","loss"],"mood":"fire","clips":[
        {"action":"walks through a burning village, carrying a large wooden cross beam on his shoulder","setting":"burning medieval village at night, thatched roofs ablaze, smoke filling the streets","lighting":"orange firelight from the burning buildings on all sides","atmosphere":"smoke rising from the buildings around him","composition":"Wide full-body shot","camera":"Slow push-in from the front","subject":"Knight walks forward under the weight of the beam","ambient":"Smoke rises from the buildings","pace":"Heavy weighted motion."},
        {"action":"kneels under the weight of the beam, one knee on the cobblestone","setting":"burning village street, fire on both sides, smoke filling the air","lighting":"orange firelight from burning buildings on his armor","atmosphere":"embers drifting past him","composition":"Side profile full body","camera":"Side profile","subject":"Knight sinks to one knee under the weight","ambient":"Embers drift past him","pace":"Heavy weighted motion."},
        {"action":"rises with the beam and walks forward through the smoke","setting":"edge of the burning village, dark road ahead, fire behind him","lighting":"orange firelight from behind, dark road ahead","atmosphere":"smoke surrounding him from behind","composition":"Three-quarter rear view","camera":"Slow push-in from behind","subject":"Knight rises and walks forward","ambient":"Smoke drifts behind him","pace":"Steady motion."},
    ]},
    {"name":"the_forge","themes":["discipline","identity","anger"],"mood":"fire","clips":[
        {"action":"stands at a blacksmith anvil, holding a glowing sword blank with tongs","setting":"dark stone forge at night, fire pit blazing to one side, tools hung on the walls","lighting":"orange firelight from the forge pit on his armor","atmosphere":"sparks drifting from the forge fire","composition":"Wide full-body shot","camera":"Close on the glowing metal on the anvil","subject":"Knight lifts hammer above the anvil","ambient":"Sparks drift from the fire","pace":"Controlled motion."},
        {"action":"strikes the glowing metal on the anvil with a heavy hammer","setting":"dark forge, sparks flying from the impact, fire blazing in the pit","lighting":"orange sparks from the hammer strike illuminating his helm","atmosphere":"sparks spraying from the anvil","composition":"Extreme close-up on hammer strike","camera":"Close on hammer striking metal","subject":"Hammer strikes the glowing metal","ambient":"Sparks fly from the anvil","pace":"Controlled motion."},
        {"action":"holds the finished sword up, examining the blade in the firelight","setting":"dark forge, fire burning low in the pit, the completed sword in his gauntlet","lighting":"orange firelight on the blade surface","atmosphere":"embers drifting from the dying fire","composition":"Low angle full body","camera":"Low angle looking up at the raised sword","subject":"Knight raises sword slowly, examining the blade","ambient":"Embers drift from the fire","pace":"Slow smooth motion."},
    ]},
    {"name":"the_desert","themes":["endurance","temptation","patience"],"mood":"fire","clips":[
        {"action":"walks across empty cracked desert ground, sword at his hip","setting":"vast empty desert at high noon, cracked earth stretching in all directions","lighting":"harsh bright sunlight from directly overhead","atmosphere":"heat shimmer on the desert surface","composition":"Wide full-body shot","camera":"Wide locked shot from the front","subject":"Knight walks forward, heavy deliberate steps","ambient":"Heat shimmer distorts the horizon","pace":"Heavy weighted motion."},
        {"action":"kneels on the cracked desert ground, head bowed against the heat","setting":"empty desert, cracked earth, blazing sky above","lighting":"harsh overhead sunlight beating down on his helm","atmosphere":"heat waves rising from the cracked ground","composition":"Overhead downward angle","camera":"Overhead angle tilting down","subject":"Knight bows head low, shoulders slumped","ambient":"Heat shimmer rises from the ground","pace":"Heavy weighted motion."},
        {"action":"stands and walks forward across the desert toward a distant dark shape on the horizon","setting":"empty desert, faint dark shape on the far horizon, blazing sky","lighting":"harsh sunlight from above, dark shape ahead","atmosphere":"heat shimmer between him and the distant shape","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks forward, picking up pace","ambient":"Heat shimmer distorts the distant shape","pace":"Steady motion."},
    ]},
    {"name":"the_shield_wall","themes":["duty","courage","anger"],"mood":"battle","clips":[
        {"action":"stands at the center of a shield wall, shield locked with others on either side","setting":"open field before battle, enemy torches visible in the distant darkness","lighting":"orange torchlight from the enemy lines in the distance","atmosphere":"smoke drifting between the two lines","composition":"Front-facing medium shot","camera":"Slow push-in from the front","subject":"Knight raises shield higher, bracing","ambient":"Smoke drifts between the lines","pace":"Controlled motion."},
        {"action":"braces behind his shield as impact hits the wall","setting":"shield wall under attack, dust and debris in the air","lighting":"dark chaotic light, flash of steel and fire","atmosphere":"dust and debris in the air around the impact","composition":"Extreme close-up on shield edge","camera":"Close on shield taking impact","subject":"Shield arm absorbs the blow","ambient":"Dust and debris fly past","pace":"Controlled motion."},
        {"action":"steps forward from the shield wall, sword drawn, advancing","setting":"broken shield wall, enemy retreating, dust settling","lighting":"dark battlefield, orange fire in the distance","atmosphere":"smoke and dust settling around him","composition":"Side profile full body","camera":"Side profile, slow push-in","subject":"Knight steps forward, sword drawn","ambient":"Smoke settles around him","pace":"Steady motion."},
    ]},
    {"name":"the_gate","themes":["courage","duty","anger"],"mood":"fire","clips":[
        {"action":"stands before two massive iron gates wreathed in fire","setting":"large iron gates in a stone archway, fire burning on the metal and arch above","lighting":"orange firelight from above on his armor","atmosphere":"smoke rising from the gate arch","composition":"Wide full-body shot","camera":"Wide shot, knight small against the towering gates","subject":"Knight steps forward toward the burning gate","ambient":"Smoke rises from the arch above","pace":"Controlled motion."},
        {"action":"places a gauntleted hand flat against the burning iron gate","setting":"iron gate up close, fire on the metal, stone arch above","lighting":"orange firelight on his gauntlet and armor","atmosphere":"embers around his gauntlet from the burning gate","composition":"Extreme close-up on gauntlet on gate","camera":"Close on gauntlet on the burning gate","subject":"Knight presses hand to gate","ambient":"Embers drift around his gauntlet","pace":"Slow smooth motion."},
        {"action":"pushes through the burning iron gate, stepping into the archway","setting":"iron archway with fire and smoke, orange light beyond the gate","lighting":"orange firelight from behind and from beyond the gate","atmosphere":"smoke surrounding the archway","composition":"Three-quarter rear view","camera":"Slow push-in from behind","subject":"Knight steps forward through the gate","ambient":"Smoke drifts around him","pace":"Steady motion."},
    ]},
]


def detect_theme(text: str, theme_keywords: dict = None) -> str:
    kw = theme_keywords or THEME_KEYWORDS
    scores = {}
    for theme, keywords in kw.items():
        scores[theme] = sum(1 for k in keywords if k in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "random"


def scene_engine(script: dict, topic: dict) -> list:
    """Generate clip prompt pairs (image + motion). Scene Engine v8 — per-brand scenes."""
    story_override = getattr(Config, 'SCENE_STORY', 'auto')
    theme_override = getattr(Config, 'SCENE_THEME', 'auto')
    figure_override = getattr(Config, 'SCENE_FIGURE', 'auto')

    # ── LOAD BRAND SCENES ───────────────────────────────────
    figures, theme_keywords, moods, intensity_mods, cameras, stories = get_scene_data()

    log.info(f"🎬 Phase 3: Scene Engine v8 | Clips: {Config.CLIP_COUNT} | Intensity: {getattr(Config, 'SCENE_INTENSITY', 'measured')} | Camera: {Config.SCENE_CAMERA}")
    log.info(f"   Overrides — Story: {story_override} | Theme: {theme_override} | Figure: {figure_override}")
    log.info(f"   Brand pack: {len(stories)} stories, {len(figures)} figures, {len(moods)} moods")

    all_text = " ".join([
        script["hook"], script["build"], script["reveal"],
        script.get("tone", ""), topic.get("category", ""), topic.get("idea", ""),
    ]).lower()

    # ── STORY SELECTION ─────────────────────────────────────
    story = None

    # 1. Forced story seed
    if story_override and story_override != "auto":
        seed_name = story_override.split("—")[0].split(" — ")[0].strip()
        story = next((s for s in stories if s["name"] == seed_name), None)
        if story:
            log.info(f"   Story forced: {story['name']} [{story['mood']}]")

    # 2. Forced theme → pick matching story
    if not story and theme_override and theme_override != "auto":
        matching = [s for s in stories if theme_override in s["themes"]]
        if Config.SCENE_MOOD_BIAS != "auto" and Config.SCENE_MOOD_BIAS in moods:
            mood_match = [s for s in matching if s["mood"] == Config.SCENE_MOOD_BIAS]
            if mood_match:
                matching = mood_match
        if matching:
            story = pick(matching)
            log.info(f"   Theme forced: {theme_override} → {story['name']} [{story['mood']}]")

    # 3. Mood bias → pick matching story
    if not story and Config.SCENE_MOOD_BIAS != "auto" and Config.SCENE_MOOD_BIAS in moods:
        matching = [s for s in stories if s["mood"] == Config.SCENE_MOOD_BIAS]
        if matching:
            story = pick(matching)
            log.info(f"   Mood forced: {Config.SCENE_MOOD_BIAS} → {story['name']}")

    # 4. Auto-detect from script text
    if not story:
        theme = detect_theme(all_text, theme_keywords)
        if theme == "random":
            matching = stories
        else:
            matching = [s for s in stories if theme in s["themes"]]
            if not matching:
                matching = stories
        story = pick(matching)
        log.info(f"   Auto-detect: {theme} → {story['name']} [{story['mood']}]")

    # ── FIGURE SELECTION ────────────────────────────────────
    if figure_override and figure_override != "auto":
        figure = f"a {figure_override}"
    else:
        figure = pick(figures)

    # ── BUILD CLIPS ─────────────────────────────────────────
    img_suffix = moods.get(story["mood"], list(moods.values())[0] if moods else "9:16 vertical.")
    intensity = getattr(Config, 'SCENE_INTENSITY', 'measured')
    intensity_mod = intensity_mods.get(intensity, list(intensity_mods.values())[0] if intensity_mods else "")
    tech_suffix = cameras.get(Config.SCENE_CAMERA, list(cameras.values())[0] if cameras else "Steady camera.") + " " + intensity_mod + " 9:16 vertical."

    clips = []
    story_clips = story["clips"]
    target_count = Config.CLIP_COUNT
    while len(story_clips) < target_count:
        story_clips = story_clips + story["clips"]
    story_clips = story_clips[:target_count]

    for i, clip in enumerate(story_clips):
        image_prompt = f"{figure} {clip['action']}. {clip['setting']}. {clip['composition']}. {clip['lighting']}. {clip['atmosphere']}. {img_suffix}"
        motion_prompt = f"{clip['camera']}. {clip['subject']}. {clip['ambient']}. {clip['pace']} {tech_suffix}"
        clips.append({
            "index": i + 1,
            "image_prompt": image_prompt,
            "motion_prompt": motion_prompt,
        })

    log.info(f"   Final: {story['name']} [{story['mood']}] | Figure: {figure[:50]}...")
    return clips

