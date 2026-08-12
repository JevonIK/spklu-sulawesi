"""Kontrak provider untuk memperoleh jarak dan waktu berkendara."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RoadMetricRequest:
    """Satu pasangan origin-destination yang perlu divalidasi."""

    request_id: str
    origin: tuple[float, float]
    destination: tuple[float, float]
    geodesic_distance_km: float


@dataclass(frozen=True)
class RoadMetricResult:
    """Jarak jalan dan durasi berkendara dari provider."""

    request_id: str
    distance_km: float
    duration_minutes: float | None = None

    def __post_init__(self):
        if not self.request_id:
            raise ValueError("ID hasil jarak jalan tidak boleh kosong.")
        if not math.isfinite(self.distance_km) or self.distance_km < 0:
            raise ValueError("Jarak jalan harus berupa angka nonnegatif.")
        if self.duration_minutes is not None and (
            not math.isfinite(self.duration_minutes)
            or self.duration_minutes < 0
        ):
            raise ValueError("Durasi berkendara harus berupa angka nonnegatif.")


@dataclass(frozen=True)
class RoadMetricBatch:
    """Hasil satu batch validasi beserta jumlah permintaan eksternal."""

    results: tuple[RoadMetricResult, ...]
    external_request_count: int

    def __post_init__(self):
        if self.external_request_count < 0:
            raise ValueError("Jumlah permintaan eksternal tidak boleh negatif.")
        request_ids = [result.request_id for result in self.results]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("Provider mengembalikan ID hasil yang duplikat.")

    def by_request_id(self):
        return {result.request_id: result for result in self.results}


class RoadMetricProvider(Protocol):
    """Antarmuka batch yang akan diimplementasikan adapter Google Maps."""

    def fetch(self, requests: tuple[RoadMetricRequest, ...]) -> RoadMetricBatch:
        """Mengembalikan metrik untuk pasangan yang dapat dirutekan."""

