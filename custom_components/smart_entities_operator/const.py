"""Constantes de l'intégration Smart Entities Operator."""

DOMAIN = "smart_entities_operator"

# Types d'entrées de configuration
ENTRY_TYPE_LIGHT = "light"
ENTRY_TYPE_COVER = "cover"
ENTRY_TYPE_SWITCH = "switch"
ENTRY_TYPE_SENSOR = "sensor"

PLATFORMS_BY_TYPE = {
    ENTRY_TYPE_LIGHT: ["light"],
    ENTRY_TYPE_COVER: ["cover"],
    ENTRY_TYPE_SWITCH: ["switch"],
    ENTRY_TYPE_SENSOR: ["sensor"],
}

# Sous-types de capteurs "opérateurs"
KIND_AGGREGATE = "aggregate"
KIND_DIFFERENCE = "difference"
KIND_DERIVATIVE = "derivative"
KIND_MOVING_AVERAGE = "moving_average"

# Opérations d'agrégat disponibles
OP_MEAN = "mean"
OP_MEDIAN = "median"
OP_MIN = "min"
OP_MAX = "max"
OP_SUM = "sum"
OP_RANGE = "range"
OP_STDEV = "stdev"
OP_COUNT = "count"
AGGREGATE_OPERATIONS = (
    OP_MEAN, OP_MEDIAN, OP_MIN, OP_MAX, OP_SUM, OP_RANGE, OP_STDEV, OP_COUNT,
)

# Unités de temps pour la dérivée (facteur vers la seconde)
TIME_UNITS = {
    "s": 1,
    "min": 60,
    "h": 3600,
    "d": 86400,
}

# Rafraîchissement périodique des capteurs temporels (fenêtre glissante / dérivée)
TIME_SENSOR_INTERVAL_SECONDS = 30
