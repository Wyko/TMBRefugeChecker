"""Approximate cumulative distances along the TMB anti-clockwise route.

Distances are measured in kilometres from Les Houches, following the
standard anti-clockwise Tour du Mont Blanc circuit (~170 km total).

Sources cross-referenced:
  - Wikipedia "Tour du Mont Blanc" stage table (Cicerone guidebook data)
  - Wikivoyage "Tour du Mont Blanc" intermediate stage distances
  - montourdumontblanc.com area groupings (refuge ordering by trail section)

Key anchor points (km from Les Houches, anti-clockwise):
  Les Houches 0 · Les Contamines 16 · Les Chapieux 34 · Elisabetta 49
  Courmayeur 66 · Bertone 70 · Grand Col Ferret 90 · La Fouly 100
  Champex 115 · Col de la Forclaz 130 · Col de Balme 138
  Tré-le-Champ 143 · Flégère 151 · Les Houches (return) 170
"""

import difflib
import unicodedata

# Maps refuge name → cumulative km from Les Houches (anti-clockwise).
# Names should match those returned by montourdumontblanc.com.
TMB_KM_FROM_START: dict[str, float] = {
    # ── Les Houches (km 0) ──────────────────────────────
    "Chalet Les Méandres (ex Tupilak)": 1.0,
    "Gîte Michel Fagot": 1.0,
    # ── Saint-Gervais (km ~10) ──────────────────────────
    "Refuge du Fioux": 10.0,
    # ── Les Contamines-Montjoie (km 13–22) ──────────────
    "Auberge du Truc": 13.0,
    "La Ferme à Piron": 16.0,
    "Gîte Les Mélèzes": 16.0,
    "Gîte le Pontet": 16.0,
    "Refuge de Nant Borrant": 20.0,
    "Refuge des Prés": 21.5,
    "Refuge de la Balme": 22.0,
    # ── Les Chapieux / Les Mottets (km 34–41) ───────────
    "Auberge-Refuge de la Nova": 35.0,
    "Les Chambres du Soleil": 35.0,
    "Refuge des Mottets": 41.0,
    # ── Val Veny → Courmayeur (km 56–66) ────────────────
    "Rifugio Monte Bianco - Cai Uget": 56.0,
    "Gite le Randonneur du Mont Blanc": 58.0,
    "Rifugio Maison Vieille": 60.0,
    # ── Courmayeur → Italian Val Ferret (km 70–84) ──────
    "Rifugio G. Bertone": 70.0,
    "Hôtel Funivia": 73.0,
    "Rifugio Chapy Mont Blanc": 75.0,
    "Hôtel Lavachey": 80.0,
    "Hôtel Chalet Val Ferret": 84.0,
    # ── Grand Col Ferret → La Fouly (km 87–101) ─────────
    "Rifugio Elena": 87.0,
    "Gîte Alpage de La Peule": 93.0,
    "Hotel du Col de Fenêtre": 97.0,
    "Gîte La Léchère": 99.0,
    "Chalet 'Le Dolent'": 99.5,
    "Auberge Maya-Joie": 100.0,
    "Auberge des Glaciers": 100.0,
    "Gîte de la Fouly": 100.0,
    "Hôtel Edelweiss": 100.5,
    # ── Champex-Lac (km ~115) ───────────────────────────
    "Pension en Plein Air": 115.0,
    "Auberge Gîte Bon Abri": 115.0,
    # ── Champex → Trient (km 117–131) ───────────────────
    "Relais d'Arpette": 117.0,
    "Hôtel du Col de la Forclaz": 129.0,
    "Auberge Mont-Blanc": 130.0,
    "Auberge la Grande Ourse": 130.0,
    "Refuge Le Peuty": 131.0,
    # ── Vallorcine (km ~139) ────────────────────────────
    "Gîte Mermoud": 139.0,
    # ── Le Tour / Argentière / Chamonix (km 140–155) ────
    "Gîte d'Alpage Les Ecuries de Charamillon": 140.0,
    "Chalet Alpin du Tour (FFCAM)": 141.0,
    "Gîte Le Moulin": 148.0,
    "Auberge la Boërne": 150.0,
    "Chalet La Grange": 155.0,
    # ── Special refuges (off montourdumontblanc.com) ────
    "Refuge du Lac Blanc": 149.0,
}


def _normalize(name: str) -> str:
    """Normalize a refuge name for fuzzy comparison.

    Decomposes Unicode characters, strips combining marks (accents),
    and lowercases the result.

    Args:
        name (str): The refuge name to normalize.

    Returns:
        str: The accent-stripped, lowercased name.
    """
    nfkd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower()


# Pre-built normalized lookup for fast accent-insensitive matching.
_NORMALIZED_LOOKUP: dict[str, str] = {
    _normalize(name): name for name in TMB_KM_FROM_START
}


def get_km_from_start(name: str) -> float | None:
    """Look up the cumulative km from Les Houches for a refuge name.

    Tries matching in order: exact match, accent-normalized match,
    then fuzzy similarity (>=85% ratio via ``difflib``).

    Args:
        name (str): The refuge name to look up.

    Returns:
        float | None: The distance in km, or ``None`` if no match found.
    """
    # 1. Exact match.
    km = TMB_KM_FROM_START.get(name)
    if km is not None:
        return km

    # 2. Accent-normalized match.
    norm = _normalize(name)
    canonical = _NORMALIZED_LOOKUP.get(norm)
    if canonical is not None:
        return TMB_KM_FROM_START[canonical]

    # 3. Fuzzy match via difflib on normalized names.
    matches = difflib.get_close_matches(norm, _NORMALIZED_LOOKUP.keys(), n=1, cutoff=0.90)
    if matches:
        canonical = _NORMALIZED_LOOKUP[matches[0]]
        return TMB_KM_FROM_START[canonical]

    return None
