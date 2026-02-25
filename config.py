"""
Knights Reactor — Configuration
"""
import os, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("knights")

DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

def env(key, default=""):
    return os.environ.get(key, default)


class Config:
    OPENAI_KEY        = env("OPENAI_API_KEY")
    OPENAI_MODEL      = "gpt-4o"
    REPLICATE_TOKEN   = env("REPLICATE_API_TOKEN")
    IMAGE_MODEL       = env("IMAGE_MODEL", "black-forest-labs/flux-1.1-pro")
    IMAGE_QUALITY     = env("IMAGE_QUALITY", "high")
    VIDEO_PROVIDER    = env("VIDEO_PROVIDER", "replicate")
    VIDEO_MODEL       = env("VIDEO_MODEL", "bytedance/seedance-1-lite")
    ELEVEN_KEY        = env("ELEVENLABS_API_KEY")
    VOICE_ID          = env("ELEVENLABS_VOICE_ID", "bwCXcoVxWNYMlC6Esa8u")
    VOICE_MODEL       = "eleven_turbo_v2"
    VOICE_STABILITY   = 0.5
    VOICE_SIMILARITY  = 0.75
    VOICE_SPEED       = 1.0
    VOICE_STYLE       = 0.0
    SCRIPT_MODEL      = "gpt-4o"
    SCRIPT_TEMP       = 0.85
    SCRIPT_WORDS      = 90
    SCENE_INTENSITY   = "measured"
    SCENE_CAMERA      = "steady"
    SCENE_MOOD_BIAS   = "auto"
    SCENE_STORY       = "auto"
    SCENE_THEME       = "auto"
    SCENE_FIGURE      = "auto"
    CLIP_COUNT        = 3
    CLIP_DURATION     = 10.0
    VIDEO_TIMEOUT     = 600
    RENDER_FPS        = 30
    RENDER_RES        = "1080"
    RENDER_ASPECT     = "9:16"
    RENDER_BG         = "#000000"
    LOGO_URL          = env("LOGO_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/gods_knights.png")
    LOGO_ENABLED      = True
    CAPTIONS_ENABLED  = True
    LOGO_POSITION     = "topRight"
    LOGO_SCALE        = 0.12
    LOGO_OPACITY      = 0.8
    CTA_ENABLED       = True
    CTA_URL           = env("CTA_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/ChristCTA.mp4")
    CTA_DURATION      = 5.0
    # Brand / Persona
    BRAND_NAME        = "Knights Reactor"
    BRAND_PERSONA     = ""   # Loaded from settings
    BRAND_VOICE       = ""
    BRAND_THEMES      = ""
    BRAND_AVOID       = ""
    ON_TT = True; ON_YT = True; ON_IG = True; ON_FB = True
    ON_TW = True; ON_TH = True; ON_PN = False
    SHOTSTACK_KEY     = env("SHOTSTACK_API_KEY")
    SHOTSTACK_ENV     = env("SHOTSTACK_ENV", "stage")
    R2_ACCESS_KEY     = env("R2_ACCESS_KEY")
    R2_SECRET_KEY     = env("R2_SECRET_KEY")
    R2_ENDPOINT       = env("R2_ENDPOINT")
    R2_BUCKET         = env("R2_BUCKET", "app-knight-videos")
    R2_PUBLIC_URL     = env("R2_PUBLIC_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev")
    BLOTATO_KEY       = env("BLOTATO_API_KEY")
    BLOTATO_ACCOUNTS  = {
        "tiktok": env("BLOTATO_TIKTOK_ID"), "youtube": env("BLOTATO_YOUTUBE_ID"),
        "instagram": env("BLOTATO_INSTAGRAM_ID", "31177"), "facebook": env("BLOTATO_FACEBOOK_ID"),
        "facebook_page": env("BLOTATO_FACEBOOK_PAGE_ID"), "pinterest": env("BLOTATO_PINTEREST_ID"),
        "pinterest_board": env("BLOTATO_PINTEREST_BOARD_ID"), "twitter": env("BLOTATO_TWITTER_ID"),
        "threads": env("BLOTATO_THREADS_ID"),
    }
