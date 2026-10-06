"""Konstanten der Integration Enthärtungsanlage."""
from homeassistant.const import Platform

DOMAIN = "water_softener_refill_sensor"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.DATETIME]

CONF_WATER_ENTITY = "water_entity"
CONF_CAPACITY_KG = "capacity_kg"
CONF_PER_REGEN_KG = "per_regen_kg"
CONF_INITIAL_STOCK_KG = "initial_stock_kg"
CONF_THRESHOLD_L = "threshold_l"
CONF_WINDOW_START = "window_start_hour"
CONF_WINDOW_END = "window_end_hour"
CONF_WARN_REMAINING = "warn_remaining"

DEFAULT_NAME = "Enthärtungsanlage"
DEFAULT_CAPACITY_KG = 25.0
DEFAULT_PER_REGEN_KG = 1.28
DEFAULT_THRESHOLD_L = 45
DEFAULT_WINDOW_START = 2
DEFAULT_WINDOW_END = 3
DEFAULT_WARN_REMAINING = 3

ATTR_CONFIG_ENTRY = "config_entry"
ATTR_KG = "kg"
ATTR_COUNT = "count"
ATTR_DATETIME = "datetime"
SERVICE_REFILL = "refill"
SERVICE_SET_STOCK = "set_salt_stock"
SERVICE_ADD_REGENERATION = "add_regeneration"
SERVICE_SET_LAST_REGENERATION = "set_last_regeneration"
SERVICE_SET_REGENS_SINCE_REFILL = "set_regenerations_since_refill"

STORAGE_VERSION = 1
SAVE_DELAY = 30  # Sekunden


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}"


def notification_id(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_low_salt"


def overdue_notification_id(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_overdue"
