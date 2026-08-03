"""Fonctions utilitaires partagées : normalisation, offsets, filtrage des valeurs."""
import logging
import statistics
import unicodedata

_LOGGER = logging.getLogger(__name__)


def normalize(text):
    """Minuscules et sans accents, pour comparer les mots-clés ('humidité' == 'humidite')."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def parse_offsets(raw):
    """Parse les offsets par capteur, une ligne par capteur : 'sensor.temp_salon = -0.5'."""
    offsets = {}
    for line in str(raw or "").replace(";", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        sep = "=" if "=" in line else ":"
        entity_id, found, value = line.partition(sep)
        if not found:
            _LOGGER.warning("Ligne d'offset ignorée (séparateur '=' ou ':' attendu) : %s", line)
            continue
        try:
            offsets[entity_id.strip().lower()] = float(value.strip().replace(",", "."))
        except ValueError:
            _LOGGER.warning("Ligne d'offset ignorée (valeur non numérique) : %s", line)
    return offsets


def to_float(value):
    """Convertit en float ou None (gère la virgule décimale)."""
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def in_bounds(value, min_valid, max_valid):
    """Vrai si value est dans [min_valid, max_valid] (bornes optionnelles)."""
    if min_valid is not None and value < min_valid:
        return False
    if max_valid is not None and value > max_valid:
        return False
    return True


def reject_outliers_mad(values, threshold):
    """Retourne (gardées, rejetées) via l'écart absolu médian (MAD).

    Une valeur est rejetée si |v - médiane| > threshold * 1.4826 * MAD.
    Robuste aux pics ponctuels. Sans effet si moins de 3 valeurs.
    """
    if not threshold or len(values) < 3:
        return list(values), []
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return list(values), []
    limit = threshold * 1.4826 * mad
    kept = [v for v in values if abs(v - median) <= limit]
    rejected = [v for v in values if abs(v - median) > limit]
    # Ne jamais tout rejeter (garde-fou)
    if not kept:
        return list(values), []
    return kept, rejected


def apply_operation(operation, values):
    """Applique une opération d'agrégat sur une liste de valeurs numériques."""
    if not values:
        return None
    if operation == "mean":
        return statistics.fmean(values)
    if operation == "median":
        return statistics.median(values)
    if operation == "min":
        return min(values)
    if operation == "max":
        return max(values)
    if operation == "sum":
        return sum(values)
    if operation == "range":
        return max(values) - min(values)
    if operation == "stdev":
        return statistics.pstdev(values) if len(values) > 1 else 0.0
    if operation == "count":
        return len(values)
    return statistics.fmean(values)
