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
# Alias kompatibilitas untuk pembaca manifest/laporan historis satu-konektor.
RESEARCH_CONNECTOR = PREFERRED_RESEARCH_CONNECTOR

REFERENCE_MAXIMUM_RANGE_KM = 430
CHARGING_TIME_INCLUDED = False
