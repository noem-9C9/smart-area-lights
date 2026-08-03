"""Smart Entities Operator : groupes par pièce/maison et capteurs opérateurs.

Opère automatiquement sur des ensembles d'entités (découverts par label/mot-clé
ou choisis explicitement) : agrégats, différences, dérivées, moyennes glissantes.
"""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import ENTRY_TYPE_LIGHT, PLATFORMS_BY_TYPE


def _entry_platforms(entry: ConfigEntry) -> list[str]:
    """Retourne les plateformes à charger selon le type d'entrée."""
    entry_type = entry.data.get("entry_type", ENTRY_TYPE_LIGHT)
    return PLATFORMS_BY_TYPE.get(entry_type, ["light"])


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure l'intégration à partir de l'interface UI."""
    await hass.config_entries.async_forward_entry_setups(entry, _entry_platforms(entry))

    # Les entités sont recréées via un rechargement quand les options changent
    # (le nombre d'entités peut varier : pièces, mots-clés, entité globale…).
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'entrée quand ses options sont modifiées."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Désinstalle l'intégration si on la supprime de l'UI."""
    return await hass.config_entries.async_unload_platforms(entry, _entry_platforms(entry))
