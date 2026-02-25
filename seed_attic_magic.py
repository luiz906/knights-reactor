"""
One-time seed script: Creates /var/data/brands/attic_magic/ with settings.json and scenes.json
Extracted from Content_Reactor_v6 n8n workflow.
Run once, then delete or ignore.
"""
import json
from pathlib import Path

DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
BRAND_DIR = DATA_DIR / "brands" / "attic_magic"
BRAND_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# SETTINGS (Brand identity extracted from n8n workflow)
# ═══════════════════════════════════════════════════════════
settings = {
    # Brand
    "brand_name": "Attic Magic",
    "brand_tagline": "Houston's attic insulation and ventilation experts",
    "brand_persona": (
        "A contractor who's seen it all and is finally telling the truth. "
        "Confident, direct, slightly provocative. Educational but NOT boring or corporate. "
        "Houston-based attic insulation and ventilation company. "
        "Speaks like an insider exposing what the industry hides."
    ),
    "brand_voice": (
        "Confident, direct, slightly provocative. "
        "Speak like a contractor who's seen it all. "
        "Educational but NOT boring or corporate. "
        "Short declarative sentences. "
        "Clean punctuation: periods, commas, question marks only. "
        "EVERY transition word MUST have a comma after it (See, So, Which means, Here's why). "
        "NO ellipses, NO em dashes, NO parentheses, NO quotes around words. "
        "Script must be ONE continuous paragraph."
    ),
    "brand_themes": (
        "Attic insulation problems, ventilation issues, energy bills, HVAC efficiency, "
        "R-value myths, air sealing, radiant barriers, Houston heat, home comfort, "
        "contractor secrets, hidden home problems, thermal bridging, humidity control. "
        "Core angles: expose hidden problems, debunk myths, show real solutions, build trust through transparency."
    ),
    "brand_avoid": (
        "Corporate speak, fake urgency, soft openings, 'Did you know' hooks, "
        "passive statements, long scripture quotations, politics, hashtags in script, "
        "warmth or sentimentality, generic advice, boring technical lectures"
    ),

    # Voice (from n8n workflow: VAnZB441uRGQ8uoZunqz = Austin)
    "voice_id": "VAnZB441uRGQ8uoZunqz",
    "voice_model": "eleven_turbo_v2",
    "voice_stability": "0.85",
    "voice_similarity": "0.75",
    "voice_speed": "1.0",
    "voice_style": "0.0",

    # Script (from n8n: 55-65 words, 25 sec)
    "script_model": "gpt-4o",
    "script_temp": "0.85",
    "script_words": 60,

    # Image/Video (keep sensible defaults)
    "image_model": "black-forest-labs/flux-1.1-pro",
    "image_quality": "high",
    "video_model": "bytedance/seedance-1-lite",
    "clip_count": "3",
    "clip_duration": "10",

    # Render
    "render_fps": "30",
    "render_res": "1080",
    "render_aspect": "9:16",
    "render_bg": "#000000",

    # Logo (blank - needs Attic Magic logo)
    "logo_enabled": True,
    "logo_url": "",
    "logo_position": "topRight",
    "logo_scale": "0.12",
    "logo_opacity": "0.8",

    # Blotato accounts (from n8n workflow)
    "blotato_instagram_id": "26890",
    "blotato_facebook_id": "17131",
    "blotato_facebook_page_id": "850572121480083",

    # Platforms
    "on_ig": True,
    "on_fb": True,
    "on_tt": False,   # null in n8n
    "on_yt": False,    # null in n8n
    "on_tw": False,    # null in n8n
    "on_th": False,    # null in n8n
    "on_pn": False,    # null in n8n

    # Category configs (from Prepare Data node)
    "category_config": {
        "Shocking Revelations": {
            "hook_patterns": [
                "Accusation: '[Entity] has been hiding this from you.'",
                "Number: '[Specific stat]. Let that sink in.'",
                "Command: 'Stop trusting [entity] on this.'",
                "Question: 'Know what [entity] won't tell you?'"
            ],
            "tone": "exposé energy, whistleblower confidence",
            "angle": "reveal hidden information that benefits the viewer"
        },
        "Shocking Reveal": {
            "hook_patterns": [
                "Accusation: 'Your [entity] lied about this.'",
                "Warning: 'This is costing you money right now.'",
                "Command: 'Check this before it's too late.'",
                "Number: '[X] percent of homes have this problem.'"
            ],
            "tone": "urgent but credible, contractor who cares",
            "angle": "expose something they can act on immediately"
        },
        "Behind-the-Scenes": {
            "hook_patterns": [
                "Command: 'Watch what contractors actually do.'",
                "Question: 'Ever seen inside an attic job?'",
                "Accusation: 'This is what they don't show you.'",
                "Challenge: 'Bet you've never seen this before.'"
            ],
            "tone": "insider access, exclusive footage energy",
            "angle": "show the real process, build trust through transparency"
        },
        "Myths Debunked": {
            "hook_patterns": [
                "Contrarian: 'This common advice is dead wrong.'",
                "Command: 'Stop believing this myth.'",
                "Question: 'Think [common belief]? Wrong.'",
                "Accusation: 'Whoever told you this was lying.'"
            ],
            "tone": "confident expert, myth-buster authority",
            "angle": "correct a specific misconception with proof"
        },
        "Hidden Truths": {
            "hook_patterns": [
                "Accusation: '[Industry/entity] doesn't want you knowing this.'",
                "Warning: 'They've hidden this for years.'",
                "Question: 'Why won't anyone talk about this?'",
                "Command: 'Stop ignoring this hidden problem.'"
            ],
            "tone": "investigative, conspiracy-meets-facts",
            "angle": "uncover something deliberately obscured"
        }
    }
}

# ═══════════════════════════════════════════════════════════
# SCENES.JSON (Scene pack from AI Visual Prompter SEALCaM)
# ═══════════════════════════════════════════════════════════
scenes = {
    "figures": [
        "single-story 1990s brick ranch, red-brown brick, dark charcoal shingles, white fascia, concrete driveway with hairline cracks, mature live oaks, St. Augustine lawn",
        "two-story traditional 2000s production home, beige stucco, stone veneer accents, 30-year architectural shingles, street-facing two-car garage, knockout roses",
        "1980s Perry home, hardy plank siding, weathered brown shingles, white vinyl soffits, aluminum gutters, crepe myrtles bare branches, muted winter lawn",
        "single-story David Weekley ranch, red brick with stone accents, dark charcoal roof, white trim, St. Augustine lawn with brown patches, pale winter sky",
        "two-story KB Home traditional, beige stucco and brick blend, dark shingles, concrete driveway, mailbox cluster nearby, live oaks mostly green"
    ],

    "themes": {
        "insulation": ["insulation", "R-value", "blown-in", "fiberglass", "cellulose", "batt", "thermal", "heat transfer", "conduction"],
        "ventilation": ["ventilation", "airflow", "soffit", "ridge vent", "attic fan", "circulation", "exhaust", "intake", "breathing"],
        "energy": ["energy", "bill", "cost", "expensive", "AC", "HVAC", "cooling", "heating", "thermostat", "electricity", "power"],
        "moisture": ["moisture", "humidity", "mold", "condensation", "water", "leak", "vapor", "barrier", "damp", "wet"],
        "damage": ["damage", "storm", "hurricane", "wind", "rain", "flood", "disaster", "emergency", "destroyed", "broken"],
        "pests": ["rats", "mice", "pest", "rodent", "squirrel", "raccoon", "animal", "infestation", "droppings", "nesting"],
        "comfort": ["comfort", "hot", "cold", "stuffy", "room", "upstairs", "second floor", "uneven", "temperature", "cool"],
        "myth": ["myth", "wrong", "lie", "scam", "fake", "mislead", "misconception", "debunk", "truth", "fact"],
        "contractor": ["contractor", "install", "job", "work", "crew", "professional", "DIY", "hired", "company", "service"],
        "savings": ["save", "savings", "rebate", "ROI", "payback", "investment", "value", "worth", "cheap", "afford"]
    },

    "moods": {
        "standard": "Editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text. Cool winter daylight 4200K, low sun angle 20-35 degrees, soft shadows.",
        "dramatic": "Editorial realism, dramatic lighting, 24fps, subtle film grain, photorealistic, no text. Dark ominous atmosphere, strong contrast, unsettling tone.",
        "storm": "Editorial realism, disaster footage aesthetic, 24fps, subtle film grain, photorealistic, no text. Dark storm light 3000K, dramatic contrast.",
        "fire": "Editorial realism, emergency footage, 24fps, grain, photorealistic, no text. Orange fire glow 2000K mixed with blue emergency lights.",
        "horror": "Editorial realism, horror film aesthetic, 24fps, grain, photorealistic, no text. Dim purple-blue dusk 3000K, minimal ambient, heavy shadows.",
        "interior": "Editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text. Soft afternoon light 4300K, warm interior tones."
    },

    "stories": [
        {
            "name": "standard_home_exterior",
            "themes": ["insulation", "ventilation", "energy", "comfort", "myth", "contractor"],
            "mood": "standard",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "North Houston subdivision, muted winter lawn, pale blue sky, front facade only",
                    "lighting": "cool winter daylight 4200K, low sun angle, soft shadows",
                    "atmosphere": "pale blue or light overcast sky, longer softer shadows",
                    "composition": "24mm WS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Front facade of home, no AC units visible",
                    "ambient": "Muted winter lawn, bare crepe myrtles",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "dim attic interior, ladder opening glow below",
                    "lighting": "motivated hatch light 3200K, soft falloff",
                    "atmosphere": "dusty look, cobwebs in corners, no floating particles",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Attic floor between 2x6 joists, gray cellulose 3 inches deep, bare drywall spots, silver flex duct",
                    "ambient": "Pull-down attic ladder opening with light spill",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "beige living room, microfiber sofa background",
                    "lighting": "soft afternoon light 4300K through window, warm interior fill",
                    "atmosphere": "comfortable home, calm, clean",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain fully still",
                    "ambient": "Knockdown ceiling texture, honey oak cabinets",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "hurricane_drama",
            "themes": ["damage", "energy", "insulation"],
            "mood": "storm",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "residential neighborhood under extreme weather, chaos, emergency",
                    "lighting": "dark storm light 3000K, dramatic contrast",
                    "atmosphere": "dark ominous clouds, destruction",
                    "composition": "24mm WS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Massive hurricane winds tearing houses apart, debris flying",
                    "ambient": "Emergency atmosphere",
                    "pace": "editorial realism, disaster footage aesthetic, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "dim attic interior, storm damage visible",
                    "lighting": "motivated hatch light 3200K, soft falloff",
                    "atmosphere": "water stains, displaced insulation",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Storm-damaged attic floor, displaced cellulose, exposed joists, water marks",
                    "ambient": "Damaged attic space",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "beige living room after repairs, calm atmosphere",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "comfortable restored home",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain, comfort restored",
                    "ambient": "Clean interior, warm tones",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "money_burning",
            "themes": ["energy", "savings", "insulation", "myth"],
            "mood": "dramatic",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "dark background, isolated focus on burning money",
                    "lighting": "orange fire glow 2200K, dramatic shadows",
                    "atmosphere": "flames consuming currency, dramatic destruction",
                    "composition": "50mm MS, shallow DOF f/2.8",
                    "camera": "static 0 in/sec",
                    "subject": "Stack of cash bills on fire, flames consuming currency",
                    "ambient": "Dark isolated background",
                    "pace": "editorial realism, dramatic metaphor, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "dim attic interior, problem insulation visible",
                    "lighting": "motivated hatch light 3200K, soft falloff",
                    "atmosphere": "dusty settled insulation, bare spots",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Attic floor with thin settled cellulose, gaps showing drywall, flex duct crossing joists",
                    "ambient": "Ladder opening glow below",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "comfortable living room, restored comfort",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "calm home, stable temperature",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain fully still",
                    "ambient": "Warm interior tones",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "haunted_attic",
            "themes": ["pests", "damage", "moisture"],
            "mood": "horror",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "dim hallway, ominous atmosphere, looking up at attic hatch",
                    "lighting": "single harsh bulb 2700K, dramatic shadows",
                    "atmosphere": "dark attic hatch opening, shadows pressing in",
                    "composition": "35mm MS looking up, shallow DOF f/2.8",
                    "camera": "static 0 in/sec",
                    "subject": "Dark attic hatch opening viewed from below, single bare lightbulb",
                    "ambient": "Ominous hallway shadows",
                    "pace": "editorial realism, suspense aesthetic, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "dark attic space, problem area revealed",
                    "lighting": "dim ambient 2800K, dramatic shadows",
                    "atmosphere": "confined space, textured surfaces, pest evidence",
                    "composition": "85mm CU, shallow DOF f/2.8",
                    "camera": "static 0 in/sec",
                    "subject": "Disturbed insulation, rodent damage, displaced fiberglass batts",
                    "ambient": "Dark confined attic space",
                    "pace": "editorial realism, pest documentation, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "bright clean living room, problem solved",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "comfortable home, fresh clean feel",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain, comfort and safety restored",
                    "ambient": "Clean bright interior",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "swat_raid",
            "themes": ["contractor", "myth"],
            "mood": "dramatic",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "suburban street, intense law enforcement presence",
                    "lighting": "mixed emergency lights with ambient 4000K",
                    "atmosphere": "tactical team, police vehicles, emergency lights",
                    "composition": "24mm WS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Tactical team in formation outside house, police vehicles, emergency lights",
                    "ambient": "Suburban street, intensity",
                    "pace": "editorial realism, news footage aesthetic, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "attic interior, evidence of negligent installation",
                    "lighting": "motivated hatch light 3200K",
                    "atmosphere": "poorly installed insulation, shortcuts visible",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Attic floor with gaps in insulation, improper installation, bare spots",
                    "ambient": "Evidence of contractor shortcuts",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "properly insulated home interior",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "comfortable well-maintained home",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window, comfort after proper installation",
                    "ambient": "Clean comfortable interior",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "house_fire",
            "themes": ["damage", "insulation", "energy"],
            "mood": "fire",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "suburban neighborhood, emergency vehicles",
                    "lighting": "orange fire glow 2000K mixed with blue emergency lights",
                    "atmosphere": "flames visible through windows, firefighters at scene",
                    "composition": "24mm WS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Residential house with flames visible through windows, firefighters",
                    "ambient": "Emergency scene atmosphere",
                    "pace": "editorial realism, emergency footage, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "attic interior showing fire risk or damage",
                    "lighting": "motivated light 3200K, harsh shadows",
                    "atmosphere": "old wiring near insulation, fire hazard indicators",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Attic floor with old insulation near electrical, potential hazard area",
                    "ambient": "Warning signs in attic",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "safe comfortable home interior",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "protected home, safety restored",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain, safe comfortable home",
                    "ambient": "Warm protected interior",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "flood_damage",
            "themes": ["damage", "moisture", "insulation"],
            "mood": "storm",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "residential neighborhood during flood emergency",
                    "lighting": "overcast gray 4500K, flat diffused light",
                    "atmosphere": "rising floodwater, debris floating, water covering streets",
                    "composition": "24mm WS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Rising floodwater approaching houses, water covering streets",
                    "ambient": "Flood emergency atmosphere",
                    "pace": "editorial realism, disaster footage, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "attic interior with water damage",
                    "lighting": "motivated hatch light 3200K",
                    "atmosphere": "water stains, soaked insulation",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Water-damaged attic, soaked cellulose, stained joists, compromised insulation",
                    "ambient": "Moisture damage evidence",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "restored dry comfortable living room",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "home restored after damage",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window, comfort restored after remediation",
                    "ambient": "Clean dry interior",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        },
        {
            "name": "luxury_car_crash",
            "themes": ["energy", "savings", "contractor"],
            "mood": "dramatic",
            "clips": [
                {
                    "action": "static scene",
                    "setting": "accident scene, suburban street",
                    "lighting": "overcast daylight 5000K, even diffusion",
                    "atmosphere": "crumpled metal, shattered glass",
                    "composition": "35mm MS, deep focus f/8",
                    "camera": "slow dolly 6 in/sec",
                    "subject": "Expensive vehicle with front-end damage, crumpled metal, shattered glass",
                    "ambient": "Accident scene",
                    "pace": "editorial realism, accident documentation, 24fps, grain, photorealistic, no text"
                },
                {
                    "action": "static scene",
                    "setting": "attic interior showing the real problem",
                    "lighting": "motivated hatch light 3200K",
                    "atmosphere": "old degraded insulation, inefficiency visible",
                    "composition": "50mm overhead pointing down, shallow DOF f/2.8",
                    "camera": "slow push in 0.3 ft/sec",
                    "subject": "Attic floor with compressed old insulation, gaps, duct disconnects",
                    "ambient": "Hidden problem revealed",
                    "pace": "editorial realism, muted tones, 24fps, subtle film grain, photorealistic, no text"
                },
                {
                    "action": "curtain fully still",
                    "setting": "comfortable efficient home",
                    "lighting": "soft afternoon light 4300K",
                    "atmosphere": "properly insulated home, stable temps",
                    "composition": "35mm MS, shallow DOF f/4",
                    "camera": "gentle drift less than 1 in/sec",
                    "subject": "Living room window with sheer curtain, efficient comfortable home",
                    "ambient": "Stable comfortable interior",
                    "pace": "editorial realism, HGTV aesthetic, 24fps, subtle film grain, photorealistic, no text"
                }
            ]
        }
    ],

    "cameras": {
        "steady": "Slow dolly 6 in/sec or static 0 in/sec. 9:16 vertical.",
        "dynamic": "Slow push in 0.3-0.5 ft/sec forward. 9:16 vertical.",
        "handheld": "Gentle drift less than 1 in/sec micro-movement. 9:16 vertical."
    }
}

# ═══════════════════════════════════════════════════════════
# WRITE FILES
# ═══════════════════════════════════════════════════════════

settings_path = BRAND_DIR / "settings.json"
scenes_path = BRAND_DIR / "scenes.json"

# Don't overwrite if settings already exist (preserve user edits)
if not settings_path.exists():
    settings_path.write_text(json.dumps(settings, indent=2))
    print(f"✓ Created {settings_path}")
else:
    # Merge: add missing keys without overwriting existing
    existing = json.loads(settings_path.read_text())
    updated = False
    for k, v in settings.items():
        if k not in existing or not existing[k]:
            existing[k] = v
            updated = True
    if updated:
        settings_path.write_text(json.dumps(existing, indent=2))
        print(f"✓ Updated {settings_path} (merged missing keys)")
    else:
        print(f"⏭ {settings_path} already complete")

# Always update scenes (this is the scene pack)
scenes_path.write_text(json.dumps(scenes, indent=2))
print(f"✓ Created {scenes_path}")

# ═══════════════════════════════════════════════════════════
# TOPICS (from Airtable export)
# ═══════════════════════════════════════════════════════════
import time, random
from datetime import datetime

TOPICS_RAW = """What's Really Hiding in Your Attic Insulation?	Shocking Revelations
The Toxic Truth About Old Attic Insulation	Shocking Revelations
Why Your Attic Is Costing You Thousands Every Year	Shocking Revelations
Energy Company Secrets They Don't Want You to Know	Shocking Revelations
This Shocking Insulation Test Changed Everything	Shocking Revelations
How Contractors REALLY Insulate Attics (Exposed)	Behind-the-Scenes
What Happens Before Insulation Goes In? You'll Be Shocked	Behind-the-Scenes
Hidden Costs of Attic Insulation You Never See	Behind-the-Scenes
Why Most DIY Attic Jobs Fail: Insider Footage	Behind-the-Scenes
Behind the Attic Walls: What Professionals Keep Quiet	Behind-the-Scenes
Fiberglass vs Blown in insulation: The Big Insulation Lie	Myths Debunked
You Don't Need New Insulation? The Myth Exposed	Myths Debunked
R-Value Is a Scam? Insulation Myths Debunked	Myths Debunked
Hot Attic in Summer? This Common Tip Doesn't Work	Myths Debunked
Why More Insulation Might Make Things Worse	Myths Debunked
No One Talks About This Attic Fire Hazard	Hidden Truths
The #1 Mistake Every Homeowner Makes in the Attic	Hidden Truths
Insulation That Attracts Pests? Yes, It Exists	Hidden Truths
Your Attic Could Be Making You Sick	Hidden Truths
The Shocking Link Between Attic Air and Allergies	Hidden Truths
Attic Before vs After: Insulation That Saved $400/mo	Transformations
Watch This Crumbling Attic Become Energy Efficient	Transformations
One Day Insulation Transformation—Start to Finish	Transformations
From Nightmare to Dream Attic in 24 Hours	Transformations
We Sealed This Attic: See the Stunning Results	Transformations
Why Blown-In Insulation Is Overrated (And What's Better)	Hot Takes
Stop Using Fiberglass—Here's Why It's Dangerous	Hot Takes
Your Energy Bill Isn't High—Your Attic Is Useless	Hot Takes
Insulating in Summer Is a Waste—Controversial Truth	Hot Takes
Attic Ventilation Is a Scam? Not Everyone Agrees	Hot Takes"""

topics_path = BRAND_DIR / "topics.json"
existing_topics = []
if topics_path.exists():
    try: existing_topics = json.loads(topics_path.read_text())
    except: pass

existing_ideas = {t.get("idea", "").lower().strip() for t in existing_topics}
added = 0

for line in TOPICS_RAW.strip().split("\n"):
    line = line.strip()
    if not line or "\t" not in line:
        continue
    idea, category = line.rsplit("\t", 1)
    idea = idea.strip()
    category = category.strip()
    if idea.lower() in existing_ideas:
        continue
    topic = {
        "id": f"t_{int(time.time()*1000)}_{random.randint(100,999)}",
        "idea": idea,
        "category": category,
        "scripture": "",
        "status": "new",
        "created": datetime.now().isoformat()
    }
    existing_topics.append(topic)
    existing_ideas.add(idea.lower())
    added += 1
    time.sleep(0.002)  # ensure unique IDs

if added > 0:
    topics_path.write_text(json.dumps(existing_topics, indent=2))
    print(f"✓ Added {added} topics to {topics_path}")
else:
    print(f"⏭ All {len(existing_topics)} topics already present")

print(f"\n✅ Attic Magic brand seeded:")
print(f"   Settings: {len(settings)} keys")
print(f"   Scenes: {len(scenes['stories'])} stories, {len(scenes['figures'])} figures, {len(scenes['themes'])} themes, {len(scenes['moods'])} moods")
print(f"   Topics: {len(existing_topics)} total ({added} new)")
