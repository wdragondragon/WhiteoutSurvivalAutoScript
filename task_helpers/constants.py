from app_paths import resource_path

BEAST_RALLY_ASSET_DIR = resource_path("buttons", "beast_rally")
GATHER_ASSET_DIR = resource_path("buttons", "gather")
MARCH_QUEUE_ASSET_DIR = resource_path("buttons", "march_queue")
BASE_SCREEN_WIDTH = 450
BASE_SCREEN_HEIGHT = 800
MARCH_SAME_TARGET = "same_target"
MAX_ACTIVE_MARCHES = 6

GATHER_RESOURCE_OPTIONS = [
    "生肉",
    "木材",
    "煤矿",
    "铁矿",
    "联盟生肉",
    "联盟木材",
    "联盟煤矿",
    "联盟铁矿",
]

GATHER_RESOURCE_ALIASES = {
    "肉": "生肉",
    "粮食": "生肉",
    "meat": "生肉",
    "food": "生肉",
    "wood": "木材",
    "coal": "煤矿",
    "iron": "铁矿",
    "联盟肉": "联盟生肉",
    "联盟粮食": "联盟生肉",
    "联盟meat": "联盟生肉",
    "联盟food": "联盟生肉",
    "联盟wood": "联盟木材",
    "联盟coal": "联盟煤矿",
    "联盟iron": "联盟铁矿",
}

GATHER_RESOURCE_CONFIG = {
    "生肉": {
        "label": "生肉",
        "category_assets": ["meat_category.png"],
        "fallback": (73, 584),
        "has_level": True,
    },
    "木材": {
        "label": "木材",
        "category_assets": ["wood_category.png"],
        "fallback": (130, 584),
        "has_level": True,
    },
    "煤矿": {
        "label": "煤矿",
        "category_assets": ["coal_category.png"],
        "fallback": (187, 584),
        "has_level": True,
    },
    "铁矿": {
        "label": "铁矿",
        "category_assets": ["iron_category.png"],
        "fallback": (244, 584),
        "has_level": True,
    },
    "联盟生肉": {
        "label": "联盟生肉",
        "category_assets": ["alliance_meat_category.png"],
        "fallback": (301, 584),
        "has_level": False,
    },
    "联盟木材": {
        "label": "联盟木材",
        "category_assets": ["alliance_wood_category.png"],
        "fallback": (73, 648),
        "has_level": False,
    },
    "联盟煤矿": {
        "label": "联盟煤矿",
        "category_assets": ["alliance_coal_category.png"],
        "fallback": (130, 648),
        "has_level": False,
    },
    "联盟铁矿": {
        "label": "联盟铁矿",
        "category_assets": ["alliance_iron_category.png"],
        "fallback": (187, 648),
        "has_level": False,
    },
}

GATHER_HERO_SLOT_REGIONS = [
    (0.05, 0.18, 0.34, 0.48),
    (0.35, 0.18, 0.64, 0.48),
    (0.65, 0.18, 0.94, 0.48),
]

MARCH_QUEUE_ROW_BASE_Y = [212, 258, 304, 350, 396, 442]
