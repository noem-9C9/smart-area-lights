"""Interface de configuration (UI) de Smart Entities Operator."""
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import label_registry as lr, selector

from .const import (
    AGGREGATE_OPERATIONS, DOMAIN, ENTRY_TYPE_COVER, ENTRY_TYPE_LIGHT,
    ENTRY_TYPE_SENSOR, ENTRY_TYPE_SWITCH, KIND_AGGREGATE, KIND_DERIVATIVE,
    KIND_DIFFERENCE, KIND_MOVING_AVERAGE, OP_MEAN,
)

_LOGGER = logging.getLogger(__name__)

# (step_id) -> (entry_type, titre)
GROUP_STEPS = {
    "lights": (ENTRY_TYPE_LIGHT, "Lumières intelligentes"),
    "covers": (ENTRY_TYPE_COVER, "Volets intelligents"),
    "switches": (ENTRY_TYPE_SWITCH, "Switchs intelligents"),
}

# (step_id) -> (sensor_kind, titre)
SENSOR_STEPS = {
    "aggregate": (KIND_AGGREGATE, "Agrégat de capteurs"),
    "difference": (KIND_DIFFERENCE, "Différence (A − B)"),
    "derivative": (KIND_DERIVATIVE, "Dérivée temporelle"),
    "moving_average": (KIND_MOVING_AVERAGE, "Moyenne glissante"),
}

LIGHT_OPTION_KEYS = ("use_brightness", "use_color_temp", "use_rgb_color")

# Entités numériques acceptées comme sources
NUMERIC_DOMAINS = ["sensor", "input_number", "number"]

OPERATION_LABELS = {
    "mean": "Moyenne", "median": "Médiane", "min": "Minimum", "max": "Maximum",
    "sum": "Somme", "range": "Amplitude (max − min)", "stdev": "Écart-type",
    "count": "Nombre de valeurs",
}
UNIT_TIME_LABELS = {
    "s": "par seconde", "min": "par minute", "h": "par heure", "d": "par jour",
}


def _get_label_options(hass, none_label="Aucun (pas de filtre)"):
    """Liste des labels existants pour le sélecteur (avec une option 'aucun')."""
    try:
        label_reg = lr.async_get(hass)
        return [{"value": "none", "label": none_label}] + [
            {"value": label.label_id, "label": label.name}
            for label in label_reg.labels.values()
        ]
    except Exception as err:
        _LOGGER.error("Erreur lors de la récupération des labels : %s", err)
        return []


def _select(options):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
    )


def _entity(multiple=False):
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=NUMERIC_DOMAINS, multiple=multiple)
    )


def _required_entity(key, conf):
    """Champ entité obligatoire, prérempli sans imposer de valeur par défaut invalide."""
    value = conf.get(key)
    marker = vol.Required(key, description={"suggested_value": value}) if value else vol.Required(key)
    return marker, _entity()


def _number(minimum=0, maximum=6, step=1):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    )


def _group_schema(hass, conf, entry_type):
    """Schéma commun des groupes : pièces ciblées et/ou entité globale Maison."""
    schema = {
        vol.Required("all_areas", default=conf.get("all_areas", False)): selector.BooleanSelector(),
        vol.Optional("target_areas", default=conf.get("target_areas", [])): selector.AreaSelector(
            selector.AreaSelectorConfig(multiple=True)
        ),
        vol.Required("create_global", default=conf.get("create_global", False)): selector.BooleanSelector(),
        vol.Optional("label_filter", default=conf.get("label_filter", "none")): _select(_get_label_options(hass)),
    }
    if entry_type == ENTRY_TYPE_LIGHT:
        for key in LIGHT_OPTION_KEYS:
            schema[vol.Required(key, default=conf.get(key, True))] = selector.BooleanSelector()
    return vol.Schema(schema)


def _aggregate_schema(hass, conf):
    """Agrégat : mots-clés et/ou entités précises, opération, filtres anti-aberrations."""
    return vol.Schema({
        vol.Optional("keywords", default=conf.get("keywords", "temperature, humidite")): selector.TextSelector(),
        vol.Optional("entities", default=conf.get("entities", [])): _entity(multiple=True),
        vol.Optional("name", default=conf.get("name", "")): selector.TextSelector(),
        vol.Required("operation", default=conf.get("operation", OP_MEAN)): _select(
            [{"value": op, "label": OPERATION_LABELS[op]} for op in AGGREGATE_OPERATIONS]
        ),
        vol.Optional("label_filter", default=conf.get("label_filter", "none")): _select(_get_label_options(hass)),
        vol.Required("precision", default=conf.get("precision", 2)): _number(),
        vol.Optional("min_valid", default=conf.get("min_valid", "")): selector.TextSelector(),
        vol.Optional("max_valid", default=conf.get("max_valid", "")): selector.TextSelector(),
        vol.Optional("outlier_mad", default=conf.get("outlier_mad", "")): selector.TextSelector(),
        vol.Optional("offsets", default=conf.get("offsets", "")): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        ),
    })


def _difference_schema(hass, conf):
    marker_a, sel_a = _required_entity("entity_a", conf)
    marker_b, sel_b = _required_entity("entity_b", conf)
    return vol.Schema({
        vol.Optional("name", default=conf.get("name", "")): selector.TextSelector(),
        marker_a: sel_a,
        marker_b: sel_b,
        vol.Required("abs_value", default=conf.get("abs_value", False)): selector.BooleanSelector(),
        vol.Required("precision", default=conf.get("precision", 2)): _number(),
    })


def _derivative_schema(hass, conf):
    marker_src, sel_src = _required_entity("source", conf)
    return vol.Schema({
        vol.Optional("name", default=conf.get("name", "")): selector.TextSelector(),
        marker_src: sel_src,
        vol.Required("unit_time", default=conf.get("unit_time", "h")): _select(
            [{"value": u, "label": UNIT_TIME_LABELS[u]} for u in ("s", "min", "h", "d")]
        ),
        vol.Required("time_window", default=conf.get("time_window", 0)): _number(minimum=0, maximum=86400, step=1),
        vol.Required("precision", default=conf.get("precision", 3)): _number(),
    })


def _moving_average_schema(hass, conf):
    marker_src, sel_src = _required_entity("source", conf)
    return vol.Schema({
        vol.Optional("name", default=conf.get("name", "")): selector.TextSelector(),
        marker_src: sel_src,
        vol.Required("window", default=conf.get("window", 300)): _number(minimum=1, maximum=86400, step=1),
        vol.Required("precision", default=conf.get("precision", 2)): _number(),
        vol.Optional("min_valid", default=conf.get("min_valid", "")): selector.TextSelector(),
        vol.Optional("max_valid", default=conf.get("max_valid", "")): selector.TextSelector(),
        vol.Optional("max_step", default=conf.get("max_step", "")): selector.TextSelector(),
    })


SENSOR_SCHEMAS = {
    "aggregate": _aggregate_schema,
    "difference": _difference_schema,
    "derivative": _derivative_schema,
    "moving_average": _moving_average_schema,
}


def _clean(user_input):
    """Retire les champs texte laissés vides (traités comme 'non défini')."""
    return {k: v for k, v in user_input.items() if not (isinstance(v, str) and v.strip() == "")}


class SmartEntitiesOperatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère l'interface de configuration depuis l'UI."""

    # Aligné sur les entrées héritées de smart_area (migration en place).
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartEntitiesOperatorOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Étape principale : choisir le type d'opérateur à créer."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                "lights", "covers", "switches",
                "aggregate", "difference", "derivative", "moving_average",
            ],
        )

    async def _create_group(self, step_id, user_input):
        entry_type, title = GROUP_STEPS[step_id]
        if user_input is not None:
            user_input["entry_type"] = entry_type
            return self.async_create_entry(title=title, data=_clean(user_input))
        return self.async_show_form(step_id=step_id, data_schema=_group_schema(self.hass, {}, entry_type))

    async def _create_sensor(self, step_id, user_input):
        kind, title = SENSOR_STEPS[step_id]
        if user_input is not None:
            user_input["entry_type"] = ENTRY_TYPE_SENSOR
            user_input["sensor_kind"] = kind
            return self.async_create_entry(title=title, data=_clean(user_input))
        return self.async_show_form(step_id=step_id, data_schema=SENSOR_SCHEMAS[step_id](self.hass, {}))

    async def async_step_lights(self, user_input=None):
        return await self._create_group("lights", user_input)

    async def async_step_covers(self, user_input=None):
        return await self._create_group("covers", user_input)

    async def async_step_switches(self, user_input=None):
        return await self._create_group("switches", user_input)

    async def async_step_aggregate(self, user_input=None):
        return await self._create_sensor("aggregate", user_input)

    async def async_step_difference(self, user_input=None):
        return await self._create_sensor("difference", user_input)

    async def async_step_derivative(self, user_input=None):
        return await self._create_sensor("derivative", user_input)

    async def async_step_moving_average(self, user_input=None):
        return await self._create_sensor("moving_average", user_input)


class SmartEntitiesOperatorOptionsFlow(config_entries.OptionsFlow):
    """Options de l'intégration (l'entrée est rechargée à la validation)."""

    @property
    def _conf(self):
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input=None):
        """Aiguiller vers les options du bon type d'entrée."""
        entry_type = self.config_entry.data.get("entry_type", ENTRY_TYPE_LIGHT)
        if entry_type == ENTRY_TYPE_SENSOR:
            kind = self.config_entry.data.get("sensor_kind", KIND_AGGREGATE)
            step_id = next(s for s, (k, _) in SENSOR_STEPS.items() if k == kind)
            return await self._edit_sensor(step_id, user_input)
        step_id = next(s for s, (t, _) in GROUP_STEPS.items() if t == entry_type)
        return await self._edit_group(step_id, user_input)

    async def _edit_group(self, step_id, user_input):
        if user_input is not None:
            return self.async_create_entry(title="", data=_clean(user_input))
        entry_type, _ = GROUP_STEPS[step_id]
        return self.async_show_form(step_id=step_id, data_schema=_group_schema(self.hass, self._conf, entry_type))

    async def _edit_sensor(self, step_id, user_input):
        if user_input is not None:
            return self.async_create_entry(title="", data=_clean(user_input))
        return self.async_show_form(step_id=step_id, data_schema=SENSOR_SCHEMAS[step_id](self.hass, self._conf))

    async def async_step_lights(self, user_input=None):
        return await self._edit_group("lights", user_input)

    async def async_step_covers(self, user_input=None):
        return await self._edit_group("covers", user_input)

    async def async_step_switches(self, user_input=None):
        return await self._edit_group("switches", user_input)

    async def async_step_aggregate(self, user_input=None):
        return await self._edit_sensor("aggregate", user_input)

    async def async_step_difference(self, user_input=None):
        return await self._edit_sensor("difference", user_input)

    async def async_step_derivative(self, user_input=None):
        return await self._edit_sensor("derivative", user_input)

    async def async_step_moving_average(self, user_input=None):
        return await self._edit_sensor("moving_average", user_input)
