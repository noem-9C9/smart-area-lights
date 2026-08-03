"""Groupes de lumières par pièce ou pour toute la maison."""
import asyncio
import logging

from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_COLOR_TEMP_KELVIN, ATTR_HS_COLOR,
    ATTR_RGB_COLOR, ATTR_SUPPORTED_COLOR_MODES, ATTR_XY_COLOR, ColorMode, LightEntity
)
from homeassistant.const import STATE_ON

from .entity import OperatorGroupEntity, build_group_entities

_LOGGER = logging.getLogger(__name__)

# Modes considérés comme "couleur" chez les membres
COLOR_MODES = {ColorMode.HS, ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW, ColorMode.XY}
COLOR_ATTRS = (ATTR_RGB_COLOR, ATTR_HS_COLOR, ATTR_XY_COLOR)


def _parse_color_modes(raw):
    """Normalise des modes de couleur (chaînes ou enums) en ColorMode."""
    modes = set()
    for mode in raw or ():
        value = str(getattr(mode, "value", mode)).split('.')[-1].lower()
        try:
            modes.add(ColorMode(value))
        except ValueError:
            pass
    return modes


def _mean(values):
    return sum(values) / len(values) if values else None


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Configure les groupes de lumières depuis les données saisies dans l'UI."""
    async_add_entities(build_group_entities(hass, config_entry, OperatorLight, "Lumières"))


class OperatorLight(OperatorGroupEntity, LightEntity):
    """Groupe de lumières exposant un jeu de modes canonique.

    Plutôt que de propager les modes hétéroclites des membres (hs, xy, rgbww…),
    le groupe n'expose que ONOFF / BRIGHTNESS / COLOR_TEMP / RGB : le service
    `light.turn_on` de Home Assistant convertit automatiquement `rgb_color`
    vers le mode natif de chaque ampoule.
    """

    _domain = "light"

    def __init__(self, hass, name, area_id, config_entry):
        super().__init__(hass, name, area_id, config_entry)
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_is_on = False
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_rgb_color = None
        self._on_members = 0

    def _platform_attributes(self):
        return {"on_lights": self._on_members}

    def _recalc(self, conf):
        """Recalcule modes supportés, moyennes et mode courant du groupe."""
        use_brightness = conf.get("use_brightness", True)
        use_color_temp = conf.get("use_color_temp", True)
        use_rgb_color = conf.get("use_rgb_color", True)

        members = self._member_states()
        on_members = [s for s in members if s.state == STATE_ON]
        self._on_members = len(on_members)
        self._attr_is_on = bool(on_members)

        # 1. Capacités du groupe : union des membres, filtrée par les réglages
        member_modes = set()
        for state in members:
            member_modes |= _parse_color_modes(state.attributes.get(ATTR_SUPPORTED_COLOR_MODES))

        supports_brightness = use_brightness and any(
            m not in (ColorMode.ONOFF, ColorMode.UNKNOWN) for m in member_modes
        )
        supports_temp = supports_brightness and use_color_temp and ColorMode.COLOR_TEMP in member_modes
        supports_color = supports_brightness and use_rgb_color and bool(member_modes & COLOR_MODES)

        modes = set()
        if supports_color:
            modes.add(ColorMode.RGB)
        if supports_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes = {ColorMode.BRIGHTNESS} if supports_brightness else {ColorMode.ONOFF}
        self._attr_supported_color_modes = modes

        # 2. Moyennes sur les membres allumés, par mode courant du membre
        #    (une ampoule en mode température n'alimente pas la moyenne RGB)
        brightness_values = [
            s.attributes[ATTR_BRIGHTNESS] for s in on_members
            if isinstance(s.attributes.get(ATTR_BRIGHTNESS), (int, float))
        ]
        kelvin_values = [
            s.attributes[ATTR_COLOR_TEMP_KELVIN] for s in on_members
            if ColorMode.COLOR_TEMP in _parse_color_modes([s.attributes.get(ATTR_COLOR_MODE)])
            and isinstance(s.attributes.get(ATTR_COLOR_TEMP_KELVIN), (int, float))
        ]
        rgb_values = [
            s.attributes[ATTR_RGB_COLOR] for s in on_members
            if _parse_color_modes([s.attributes.get(ATTR_COLOR_MODE)]) & COLOR_MODES
            and s.attributes.get(ATTR_RGB_COLOR) is not None
            and len(s.attributes[ATTR_RGB_COLOR]) == 3
        ]

        brightness = _mean(brightness_values)
        kelvin = _mean(kelvin_values)
        self._attr_brightness = round(brightness) if brightness is not None and supports_brightness else None
        self._attr_color_temp_kelvin = round(kelvin) if kelvin is not None and supports_temp else None
        if rgb_values and supports_color:
            self._attr_rgb_color = tuple(
                round(_mean([rgb[i] for rgb in rgb_values])) for i in range(3)
            )
        else:
            self._attr_rgb_color = None

        # 3. Mode courant : couleur > température > luminosité > on/off
        if not self._attr_is_on:
            self._attr_color_mode = ColorMode.UNKNOWN
        elif self._attr_rgb_color is not None:
            self._attr_color_mode = ColorMode.RGB
        elif self._attr_color_temp_kelvin is not None:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = next(iter(modes))

    def _member_service_data(self, state, kwargs):
        """Ne transmet à chaque membre que les attributs qu'il supporte."""
        member_modes = _parse_color_modes(state.attributes.get(ATTR_SUPPORTED_COLOR_MODES))
        data = {"entity_id": state.entity_id}

        if ATTR_BRIGHTNESS in kwargs and any(
            m not in (ColorMode.ONOFF, ColorMode.UNKNOWN) for m in member_modes
        ):
            data[ATTR_BRIGHTNESS] = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in kwargs and ColorMode.COLOR_TEMP in member_modes:
            data[ATTR_COLOR_TEMP_KELVIN] = kwargs[ATTR_COLOR_TEMP_KELVIN]
        if member_modes & COLOR_MODES:
            for attr in COLOR_ATTRS:
                if attr in kwargs:
                    data[attr] = kwargs[attr]
        return data

    async def async_turn_on(self, **kwargs):
        """Allume les lumières du groupe."""
        _LOGGER.debug("Appel de turn_on pour %s avec %s", self.name, kwargs)
        self._update_internal_state()

        members = self._member_states()
        if not members:
            _LOGGER.warning("Aucune lumière trouvée pour %s", self.name)
            return

        # Si on ajuste un réglage (luminosité/couleur) alors que le groupe est déjà
        # partiellement allumé, on l'applique UNIQUEMENT aux ampoules DÉJÀ allumées.
        adjust_only = bool(kwargs) and self._attr_is_on
        if adjust_only:
            members = [s for s in members if s.state == STATE_ON]

        await asyncio.gather(*(
            self.hass.services.async_call(
                "light", "turn_on", self._member_service_data(state, kwargs), False
            )
            for state in members
        ))

    async def async_turn_off(self, **kwargs):
        """Éteint les lumières du groupe."""
        _LOGGER.debug("Appel de turn_off pour %s", self.name)
        await self._async_call_members("turn_off")
