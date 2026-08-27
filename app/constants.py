"""Konstanta ruang lingkup penelitian yang tidak dapat diubah saat runtime."""


# ``DEFAULT_CONNECTOR`` dipertahankan untuk payload klien lama yang hanya
# menerima satu nilai. Kendaraan Combo 2 pada antarmuka dan eksperimen baru
# memakai kedua konektor di bawah: CCS2 diprioritaskan untuk pemberhentian DC,
# sedangkan AC Type 2 hanya menjadi fallback yang ditandai secara eksplisit.
DEFAULT_CONNECTOR = "CCS2"
DEFAULT_CONNECTORS = ("AC TYPE 2", "CCS2")
RESEARCH_CONNECTORS = DEFAULT_CONNECTORS
PREFERRED_RESEARCH_CONNECTOR = "CCS2"
FALLBACK_RESEARCH_CONNECTOR = "AC TYPE 2"
COMBO2_CONNECTOR_POLICY = "combo2_ccs2_primary_ac_type2_fallback"
COMBO2_CONNECTOR_SCOPE = "exact_combo2_connector_set"
SINGLE_CONNECTOR_POLICY = "single_connector"
NEUTRAL_CONNECTOR_POLICY = "selected_connectors_equal"
# Alias kompatibilitas untuk pembaca manifest/laporan historis satu-konektor.
RESEARCH_CONNECTOR = PREFERRED_RESEARCH_CONNECTOR

REFERENCE_MAXIMUM_RANGE_KM = 430
DETOUR_REFERENCE_MULTIPLIER = 2
REFERENCE_MAX_TOTAL_DETOUR_KM = 20
DETOUR_SENSITIVITY_LEVELS_KM = (10, 20, 30)


def connector_preference_policy(connectors):
    """Kembalikan kebijakan eksplisit tanpa mengurutkan standar heterogen."""

    values = tuple(connectors)
    if len(values) == 1:
        return SINGLE_CONNECTOR_POLICY
    if len(values) == 2 and frozenset(values) == frozenset(DEFAULT_CONNECTORS):
        return COMBO2_CONNECTOR_POLICY
    return NEUTRAL_CONNECTOR_POLICY


def preferred_connector_for(connectors):
    """Tetapkan konektor utama hanya untuk satu konektor atau profil Combo 2."""

    values = tuple(connectors)
    policy = connector_preference_policy(values)
    if policy == COMBO2_CONNECTOR_POLICY:
        return PREFERRED_RESEARCH_CONNECTOR
    if policy == SINGLE_CONNECTOR_POLICY:
        return values[0]
    return None


def fallback_connectors_for(connectors):
    """AC Type 2 menjadi fallback hanya pada profil tepat Combo 2."""

    if connector_preference_policy(connectors) == COMBO2_CONNECTOR_POLICY:
        return (FALLBACK_RESEARCH_CONNECTOR,)
    return ()
