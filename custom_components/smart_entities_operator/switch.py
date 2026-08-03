"""Groupes de switchs par pièce ou pour toute la maison."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON

from .entity import OperatorGroupEntity, build_group_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Configure les groupes de switchs depuis les données saisies dans l'UI."""
    async_add_entities(build_group_entities(hass, config_entry, OperatorSwitch, "Switchs"))


class OperatorSwitch(OperatorGroupEntity, SwitchEntity):
    """Groupe de switchs : allumé si au moins un membre est allumé."""

    _domain = "switch"

    def __init__(self, hass, name, area_id, config_entry):
        super().__init__(hass, name, area_id, config_entry)
        self._attr_is_on = False
        self._on_members = 0

    def _platform_attributes(self):
        return {"on_switches": self._on_members}

    def _recalc(self, conf):
        members = self._member_states()
        self._on_members = sum(s.state == STATE_ON for s in members)
        self._attr_is_on = self._on_members > 0

    async def async_turn_on(self, **kwargs):
        """Allume les switchs du groupe."""
        await self._async_call_members("turn_on")

    async def async_turn_off(self, **kwargs):
        """Éteint les switchs du groupe."""
        await self._async_call_members("turn_off")
