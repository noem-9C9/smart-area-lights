"""Base commune des groupes : découverte des membres par pièce/label et écouteurs."""
import logging

from homeassistant.const import ATTR_SUPPORTED_FEATURES, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import callback
from homeassistant.helpers import (
    area_registry as ar, device_registry as dr, entity_registry as er
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def build_group_entities(hass, config_entry, factory, name_prefix):
    """Crée une entité par pièce ciblée et/ou une entité globale Maison."""
    conf = {**config_entry.data, **config_entry.options}
    area_reg = ar.async_get(hass)

    target_areas = conf.get("target_areas") or []
    if conf.get("all_areas"):
        target_areas = list(area_reg.areas)

    entities = []
    for area_id in target_areas:
        area = area_reg.async_get_area(area_id)
        name = f"{name_prefix} {area.name}" if area else f"{name_prefix} {area_id}"
        entities.append(factory(hass, name, area_id, config_entry))

    if conf.get("create_global"):
        entities.append(factory(hass, f"{name_prefix} Maison", None, config_entry))

    return entities


class OperatorGroupEntity(Entity):
    """Groupe dynamique basé sur une pièce (ou toute la maison) et un label.

    Les sous-classes définissent `_domain` et implémentent `_recalc(conf)`
    pour calculer l'état du groupe à partir de `self._member_states()`.
    """

    _attr_should_poll = False
    _domain = None

    def __init__(self, hass, name, area_id, config_entry):
        self.hass = hass
        self._attr_name = name
        # area_id None = groupe global pour toute la maison
        self._area_id = area_id.lower() if area_id else None
        self.config_entry = config_entry

        self._tracked_entities = []
        self._unavailable_entities = []
        self._unsub_track_state = None

        scope = self._area_id or "home"
        initial_label = config_entry.data.get("label_filter")
        if not initial_label or initial_label == "none":
            initial_label = "all"
        self._attr_unique_id = f"group_auto_{scope}_{initial_label}".strip('_')
        # Force l'ID d'entité technique
        self.entity_id = f"{self._domain}.group_auto_{scope}_{initial_label}".strip('_')

    @property
    def _conf(self):
        """Configuration courante (data + options)."""
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def extra_state_attributes(self):
        """Attributs supplémentaires pour l'entité."""
        label_id = self._conf.get("label_filter")
        attrs = {
            "scope": self._area_id or "home",
            "label_filter": label_id if label_id and label_id != "none" else None,
            "total_members": len(self._tracked_entities),
            # Convention HA : liste des membres (lue par les cartes et l'UI)
            "entity_id": self._tracked_entities,
            "unavailable_members": self._unavailable_entities,
        }
        attrs.update(self._platform_attributes())
        return attrs

    def _platform_attributes(self):
        """Attributs spécifiques à la plateforme (surchargé par les sous-classes)."""
        return {}

    async def async_added_to_hass(self):
        """Appelé quand l'entité est ajoutée à Home Assistant."""
        self._update_internal_state()

        # Écouter l'ajout ou la modification d'appareils (pour MQTT/Zigbee Discovery)
        self.async_on_remove(
            self.hass.bus.async_listen("entity_registry_updated", self._async_registry_updated)
        )
        self.async_on_remove(
            self.hass.bus.async_listen("device_registry_updated", self._async_registry_updated)
        )

        # Si HA n'a pas encore fini de démarrer, on attend le signal pour recalculer l'état final
        if not self.hass.is_running:
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_ha_started
            )

    async def async_will_remove_from_hass(self):
        """Appelé quand l'entité est supprimée."""
        if self._unsub_track_state:
            self._unsub_track_state()

    def _setup_listeners(self):
        if self._unsub_track_state:
            self._unsub_track_state()
            self._unsub_track_state = None

        if self._tracked_entities:
            self._unsub_track_state = async_track_state_change_event(
                self.hass, self._tracked_entities, self._async_state_changed
            )

    @callback
    def _async_ha_started(self, _event):
        """Recalculer l'état quand Home Assistant a fini de démarrer."""
        self._update_internal_state()
        self.async_write_ha_state()

    @callback
    def _async_state_changed(self, event):
        self._update_internal_state()
        self.async_write_ha_state()

    @callback
    def _async_registry_updated(self, event):
        """Recalculer si une entité est ajoutée ou modifiée dans le registre."""
        self._update_internal_state()
        self.async_write_ha_state()

    def _member_states(self):
        """Objets State des membres présents dans la machine d'états."""
        states = (self.hass.states.get(entity_id) for entity_id in self._tracked_entities)
        return [state for state in states if state is not None]

    def _update_internal_state(self):
        """Met à jour la liste des membres suivis puis recalcule l'état du groupe."""
        try:
            conf = self._conf
            label_filter = conf.get("label_filter")
            if label_filter == "none":
                label_filter = None

            entity_reg = er.async_get(self.hass)
            device_reg = dr.async_get(self.hass)

            new_tracked = []
            for entity_id, entry in entity_reg.entities.items():
                # Ignorer nos propres groupes et les entités désactivées
                if entry.platform == DOMAIN or entry.disabled_by:
                    continue
                if not entity_id.startswith(f"{self._domain}."):
                    continue

                ent_area = entry.area_id
                ent_labels = entry.labels or set()

                # La pièce et les labels peuvent venir de l'appareil parent
                if entry.device_id:
                    device = device_reg.async_get(entry.device_id)
                    if device:
                        if not ent_area:
                            ent_area = device.area_id
                        if device.labels:
                            ent_labels = ent_labels.union(device.labels)

                if self._area_id and (not ent_area or ent_area.lower() != self._area_id):
                    continue
                if label_filter and label_filter not in ent_labels:
                    continue
                new_tracked.append(entity_id)

            if set(new_tracked) != set(self._tracked_entities):
                self._tracked_entities = new_tracked
                self._setup_listeners()

            # Membres actuellement indisponibles (exposés en attribut, exclus des calculs)
            self._unavailable_entities = [
                entity_id for entity_id in self._tracked_entities
                if (state := self.hass.states.get(entity_id)) is None
                or state.state in ("unknown", "unavailable")
            ]

            self._recalc(conf)

        except Exception as err:
            _LOGGER.exception("Erreur critique lors de la mise à jour de %s : %s", self.name, err)

    def _recalc(self, conf):
        """Calcule l'état du groupe à partir des membres (à surcharger)."""
        raise NotImplementedError

    async def _async_call_members(self, service, data=None, feature=None):
        """Appelle un service du domaine sur les membres, filtrés par capacité si demandé."""
        if feature is not None:
            targets = [
                state.entity_id for state in self._member_states()
                if int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0) & feature
            ]
        else:
            targets = self._tracked_entities

        if not targets:
            _LOGGER.warning("Aucun membre trouvé pour %s (%s)", self.name, service)
            return

        await self.hass.services.async_call(
            self._domain, service, {**(data or {}), "entity_id": targets}, False
        )
