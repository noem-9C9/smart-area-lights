"""Groupes de volets par pièce ou pour toute la maison."""
import logging

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION, ATTR_POSITION, CoverEntity, CoverEntityFeature
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES, STATE_CLOSED, STATE_CLOSING, STATE_OPEN, STATE_OPENING,
    STATE_UNAVAILABLE, STATE_UNKNOWN
)

from .entity import OperatorGroupEntity, build_group_entities

_LOGGER = logging.getLogger(__name__)

GROUP_FEATURES = (
    CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    | CoverEntityFeature.STOP | CoverEntityFeature.SET_POSITION
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Configure les groupes de volets depuis les données saisies dans l'UI."""
    async_add_entities(build_group_entities(hass, config_entry, OperatorCover, "Volets"))


class OperatorCover(OperatorGroupEntity, CoverEntity):
    """Groupe de volets : ouvert si au moins un membre est ouvert."""

    _domain = "cover"

    def __init__(self, hass, name, area_id, config_entry):
        super().__init__(hass, name, area_id, config_entry)
        self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        self._attr_is_closed = None
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_current_cover_position = None
        self._open_members = 0

    def _platform_attributes(self):
        return {"open_covers": self._open_members}

    def _recalc(self, conf):
        members = self._member_states()
        valid = [s for s in members if s.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)]

        features = CoverEntityFeature(0)
        positions = []
        for state in members:
            raw = state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0
            features |= CoverEntityFeature(int(raw)) & GROUP_FEATURES
            position = state.attributes.get(ATTR_CURRENT_POSITION)
            if isinstance(position, (int, float)):
                positions.append(position)

        self._attr_supported_features = features or (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        )
        self._open_members = sum(s.state == STATE_OPEN for s in valid)
        self._attr_is_opening = any(s.state == STATE_OPENING for s in valid)
        self._attr_is_closing = any(s.state == STATE_CLOSING for s in valid)
        self._attr_is_closed = all(s.state == STATE_CLOSED for s in valid) if valid else None

        if CoverEntityFeature.SET_POSITION in self._attr_supported_features and positions:
            self._attr_current_cover_position = round(sum(positions) / len(positions))
        else:
            self._attr_current_cover_position = None

    async def async_open_cover(self, **kwargs):
        """Ouvre les volets du groupe."""
        await self._async_call_members("open_cover")

    async def async_close_cover(self, **kwargs):
        """Ferme les volets du groupe."""
        await self._async_call_members("close_cover")

    async def async_stop_cover(self, **kwargs):
        """Arrête les volets du groupe (membres qui le supportent)."""
        await self._async_call_members("stop_cover", feature=CoverEntityFeature.STOP)

    async def async_set_cover_position(self, **kwargs):
        """Positionne les volets du groupe (membres qui le supportent)."""
        await self._async_call_members(
            "set_cover_position",
            {ATTR_POSITION: kwargs[ATTR_POSITION]},
            feature=CoverEntityFeature.SET_POSITION,
        )
