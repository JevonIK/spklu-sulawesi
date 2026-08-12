"""Model jarak efektif dan konsumsi State of Charge kendaraan listrik."""

from __future__ import annotations

import math
from dataclasses import dataclass


SOC_TOLERANCE = 1e-9


def _finite_number(value, label):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} harus berupa angka finite.")
    return value


@dataclass(frozen=True)
class EnergyParameters:
    """Parameter energi kendaraan dan batas operasional SOC."""

    maximum_range_km: float
    minimum_soc_percent: float
    target_soc_percent: float
    safety_factor: float = 0.90
    soc_step_percent: float = 5.0

    def __post_init__(self):
        maximum_range = _finite_number(
            self.maximum_range_km, "Jangkauan maksimum"
        )
        minimum_soc = _finite_number(
            self.minimum_soc_percent, "SOC minimum"
        )
        target_soc = _finite_number(
            self.target_soc_percent, "Target SOC"
        )
        safety_factor = _finite_number(self.safety_factor, "Safety factor")
        soc_step = _finite_number(self.soc_step_percent, "Interval SOC")

        if maximum_range <= 0:
            raise ValueError("Jangkauan maksimum harus lebih besar dari nol.")
        if not 0 <= minimum_soc < 100:
            raise ValueError("SOC minimum harus berada pada rentang 0 sampai <100.")
        if not minimum_soc < target_soc <= 100:
            raise ValueError("Target SOC harus lebih besar dari SOC minimum dan <=100.")
        if not 0 < safety_factor <= 1:
            raise ValueError("Safety factor harus berada pada rentang >0 sampai 1.")
        if not 0 < soc_step <= 100 - minimum_soc:
            raise ValueError("Interval SOC tidak valid untuk batas SOC minimum.")

        object.__setattr__(self, "maximum_range_km", maximum_range)
        object.__setattr__(self, "minimum_soc_percent", minimum_soc)
        object.__setattr__(self, "target_soc_percent", target_soc)
        object.__setattr__(self, "safety_factor", safety_factor)
        object.__setattr__(self, "soc_step_percent", soc_step)

    @property
    def effective_full_range_km(self):
        return self.maximum_range_km * self.safety_factor

    def validate_current_soc(self, current_soc_percent):
        current_soc = _finite_number(current_soc_percent, "SOC saat ini")
        if not self.minimum_soc_percent <= current_soc <= 100:
            raise ValueError(
                "SOC saat ini harus berada di antara SOC minimum dan 100."
            )
        return current_soc

    def usable_range_km(self, soc_percent):
        """Jarak yang dapat dipakai tanpa melanggar SOC minimum."""

        soc = _finite_number(soc_percent, "SOC")
        if not 0 <= soc <= 100:
            raise ValueError("SOC harus berada pada rentang 0 sampai 100.")
        usable_soc = max(0.0, soc - self.minimum_soc_percent)
        return usable_soc / 100 * self.effective_full_range_km

    def consumption_percent(self, road_distance_km):
        """Mengonversi jarak jalan menjadi estimasi konsumsi SOC."""

        distance = _finite_number(road_distance_km, "Jarak jalan")
        if distance < 0:
            raise ValueError("Jarak jalan tidak boleh negatif.")
        return distance / self.effective_full_range_km * 100

    def arrival_soc_percent(self, departure_soc_percent, road_distance_km):
        departure_soc = _finite_number(departure_soc_percent, "SOC keberangkatan")
        if not 0 <= departure_soc <= 100:
            raise ValueError("SOC keberangkatan harus berada pada rentang 0 sampai 100.")
        return departure_soc - self.consumption_percent(road_distance_km)

    def to_dict(self):
        return {
            "maximum_range_km": self.maximum_range_km,
            "minimum_soc_percent": self.minimum_soc_percent,
            "target_soc_percent": self.target_soc_percent,
            "safety_factor": self.safety_factor,
            "soc_step_percent": self.soc_step_percent,
            "effective_full_range_km": self.effective_full_range_km,
        }


class SocDiscretizer:
    """Grid SOC konservatif yang berjangkar pada batas SOC minimum."""

    def __init__(self, parameters: EnergyParameters):
        self.parameters = parameters
        levels = [parameters.minimum_soc_percent]
        next_level = parameters.minimum_soc_percent + parameters.soc_step_percent
        while next_level <= 100 + SOC_TOLERANCE:
            levels.append(min(100.0, next_level))
            next_level += parameters.soc_step_percent

        # Target dan 100 dipertahankan sebagai cap eksplisit meskipun bukan
        # kelipatan tepat dari interval yang berjangkar pada SOC minimum.
        levels.extend((parameters.target_soc_percent, 100.0))
        self.levels = tuple(
            sorted(dict.fromkeys(round(level, 8) for level in levels))
        )
        self.target_level = self.quantize_down(parameters.target_soc_percent)

    def quantize_down(self, soc_percent):
        """Membulatkan SOC ke grid terdekat yang tidak melebihi nilai aktual."""

        soc = _finite_number(soc_percent, "SOC")
        eligible = [level for level in self.levels if level <= soc + SOC_TOLERANCE]
        if not eligible:
            raise ValueError("SOC berada di bawah batas minimum grid.")
        return max(eligible)

    def charging_levels(self, arrival_level):
        """Menghasilkan semua SOC keberangkatan yang lebih tinggi hingga target."""

        arrival_level = self.quantize_down(arrival_level)
        return tuple(
            level
            for level in self.levels
            if arrival_level + SOC_TOLERANCE < level <= self.target_level + SOC_TOLERANCE
        )
