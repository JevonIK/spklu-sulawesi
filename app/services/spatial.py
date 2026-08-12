"""Indeks Ball Tree dan operasi spasial untuk koridor perjalanan."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import BallTree

from .dataset import StationNode, normalize_connector


EARTH_RADIUS_KM = 6371.0088
DISTANCE_TOLERANCE_KM = 1e-6


def _coordinate(value):
    if len(value) != 2:
        raise ValueError("Koordinat harus berisi latitude dan longitude.")

    latitude, longitude = float(value[0]), float(value[1])
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Koordinat harus berupa angka finite.")
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude harus berada pada rentang -90 sampai 90.")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude harus berada pada rentang -180 sampai 180.")
    return latitude, longitude


def haversine_distance_km(first, second):
    """Menghitung jarak great-circle dua koordinat dalam kilometer."""

    lat1, lon1 = _coordinate(first)
    lat2, lon2 = _coordinate(second)
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(
        math.radians, (lat1, lon1, lat2, lon2)
    )
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    angular_distance = 2 * math.asin(min(1.0, math.sqrt(haversine)))
    return EARTH_RADIUS_KM * angular_distance


@dataclass(frozen=True)
class RouteProjection:
    """Posisi suatu titik relatif terhadap polyline rute."""

    distance_to_route_km: float
    progress_km: float
    progress_ratio: float
    closest_coordinate: tuple[float, float]
    segment_index: int


@dataclass(frozen=True)
class RadiusMatch:
    """Node SPKLU yang ditemukan oleh query radius Ball Tree."""

    node: StationNode
    distance_km: float


@dataclass(frozen=True)
class CorridorCandidate:
    """Node SPKLU yang lolos penyaringan koridor dan arah perjalanan."""

    node: StationNode
    distance_to_route_km: float
    route_progress_km: float
    route_progress_ratio: float
    straight_line_distance_km: float | None = None

    def to_dict(self):
        payload = self.node.to_dict(include_units=True)
        payload.update(
            {
                "distance_to_route_km": self.distance_to_route_km,
                "route_progress_km": self.route_progress_km,
                "route_progress_ratio": self.route_progress_ratio,
                "straight_line_distance_km": self.straight_line_distance_km,
            }
        )
        return payload


class RouteGeometry:
    """Polyline tervalidasi dengan jarak kumulatif dan operasi proyeksi."""

    def __init__(self, coordinates):
        normalized = tuple(_coordinate(point) for point in coordinates)
        if len(normalized) < 2:
            raise ValueError("Polyline rute harus memiliki sedikitnya dua titik.")

        cumulative = [0.0]
        for first, second in zip(normalized, normalized[1:]):
            cumulative.append(
                cumulative[-1] + haversine_distance_km(first, second)
            )

        if cumulative[-1] <= DISTANCE_TOLERANCE_KM:
            raise ValueError("Polyline rute harus memiliki panjang lebih dari nol.")

        self.coordinates = normalized
        self.cumulative_distances_km = tuple(cumulative)
        self.total_distance_km = cumulative[-1]

    def sample(self, step_km):
        """Mengambil sampel polyline dengan jarak antarsampel maksimum step."""

        step_km = float(step_km)
        if not math.isfinite(step_km) or step_km <= 0:
            raise ValueError("Jarak sampling harus lebih besar dari nol.")

        samples = [self.coordinates[0]]
        for index, (first, second) in enumerate(
            zip(self.coordinates, self.coordinates[1:])
        ):
            segment_length = (
                self.cumulative_distances_km[index + 1]
                - self.cumulative_distances_km[index]
            )
            if segment_length <= DISTANCE_TOLERANCE_KM:
                continue

            subdivisions = max(1, math.ceil(segment_length / step_km))
            for part in range(1, subdivisions + 1):
                ratio = part / subdivisions
                samples.append(
                    (
                        first[0] + (second[0] - first[0]) * ratio,
                        first[1] + (second[1] - first[1]) * ratio,
                    )
                )
        return tuple(samples)

    def project(self, point):
        """Memproyeksikan titik ke segmen polyline terdekat."""

        point = _coordinate(point)
        best_distance = math.inf
        best_progress = 0.0
        best_coordinate = self.coordinates[0]
        best_segment_index = 0

        for index, (first, second) in enumerate(
            zip(self.coordinates, self.coordinates[1:])
        ):
            mean_latitude = math.radians(
                (first[0] + second[0] + point[0]) / 3
            )
            longitude_scale = EARTH_RADIUS_KM * math.cos(mean_latitude)

            segment_x = math.radians(second[1] - first[1]) * longitude_scale
            segment_y = math.radians(second[0] - first[0]) * EARTH_RADIUS_KM
            point_x = math.radians(point[1] - first[1]) * longitude_scale
            point_y = math.radians(point[0] - first[0]) * EARTH_RADIUS_KM
            segment_squared = segment_x**2 + segment_y**2

            if segment_squared <= DISTANCE_TOLERANCE_KM**2:
                ratio = 0.0
            else:
                ratio = max(
                    0.0,
                    min(
                        1.0,
                        (point_x * segment_x + point_y * segment_y)
                        / segment_squared,
                    ),
                )

            closest = (
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
            )
            distance = haversine_distance_km(point, closest)
            segment_length = (
                self.cumulative_distances_km[index + 1]
                - self.cumulative_distances_km[index]
            )
            progress = self.cumulative_distances_km[index] + ratio * segment_length

            if distance < best_distance:
                best_distance = distance
                best_progress = progress
                best_coordinate = closest
                best_segment_index = index

        return RouteProjection(
            distance_to_route_km=best_distance,
            progress_km=best_progress,
            progress_ratio=best_progress / self.total_distance_km,
            closest_coordinate=best_coordinate,
            segment_index=best_segment_index,
        )


class StationSpatialIndex:
    """Indeks Ball Tree Haversine untuk seluruh node SPKLU."""

    def __init__(self, nodes):
        self.nodes = tuple(nodes)
        if not self.nodes:
            raise ValueError("Indeks spasial memerlukan sedikitnya satu node SPKLU.")

        coordinate_matrix = np.asarray(
            [(node.latitude, node.longitude) for node in self.nodes],
            dtype=float,
        )
        self._coordinates_radians = np.radians(coordinate_matrix)
        self._tree = BallTree(self._coordinates_radians, metric="haversine")

    def summary(self):
        return {
            "index_type": "BallTree",
            "metric": "haversine",
            "earth_radius_km": EARTH_RADIUS_KM,
            "indexed_nodes": len(self.nodes),
        }

    def query_radius(self, center, radius_km, connector=None):
        """Mengembalikan seluruh node dalam radius, tanpa membatasi nilai K."""

        center = _coordinate(center)
        radius_km = float(radius_km)
        if not math.isfinite(radius_km) or radius_km <= 0:
            raise ValueError("Radius pencarian harus lebih besar dari nol.")

        normalized_connector = (
            normalize_connector(connector) if connector else None
        )
        center_radians = np.radians(np.asarray([center], dtype=float))
        indexes, angular_distances = self._tree.query_radius(
            center_radians,
            r=radius_km / EARTH_RADIUS_KM,
            return_distance=True,
            sort_results=True,
        )

        matches = []
        for node_index, angular_distance in zip(
            indexes[0], angular_distances[0]
        ):
            node = self.nodes[int(node_index)]
            if (
                normalized_connector is not None
                and normalized_connector not in node.connectors
            ):
                continue
            matches.append(
                RadiusMatch(
                    node=node,
                    distance_km=float(angular_distance) * EARTH_RADIUS_KM,
                )
            )
        return tuple(matches)


def find_corridor_candidates(
    spatial_index,
    route,
    corridor_radius_km,
    connector=None,
    sample_step_km=5.0,
):
    """Menghimpun dan memfilter seluruh SPKLU di sepanjang koridor rute."""

    geometry = route if isinstance(route, RouteGeometry) else RouteGeometry(route)
    corridor_radius_km = float(corridor_radius_km)
    sample_step_km = float(sample_step_km)
    if not math.isfinite(corridor_radius_km) or corridor_radius_km <= 0:
        raise ValueError("Radius koridor harus lebih besar dari nol.")
    if not math.isfinite(sample_step_km) or sample_step_km <= 0:
        raise ValueError("Jarak sampling harus lebih besar dari nol.")

    # Tambahan setengah jarak sampling menjaga titik dekat segmen tidak terlewat
    # pada tahap penghimpunan. Filter proyeksi tetap memakai radius koridor asli.
    collection_radius_km = corridor_radius_km + sample_step_km / 2
    collected_nodes = {}
    for sample in geometry.sample(sample_step_km):
        for match in spatial_index.query_radius(
            sample,
            collection_radius_km,
            connector=connector,
        ):
            collected_nodes[match.node.node_id] = match.node

    candidates = []
    for node in collected_nodes.values():
        projection = geometry.project((node.latitude, node.longitude))
        if projection.distance_to_route_km > corridor_radius_km:
            continue
        candidates.append(
            CorridorCandidate(
                node=node,
                distance_to_route_km=projection.distance_to_route_km,
                route_progress_km=projection.progress_km,
                route_progress_ratio=projection.progress_ratio,
            )
        )

    return tuple(
        sorted(candidates, key=lambda item: (item.route_progress_km, item.node.node_id))
    )


def find_reachable_forward_candidates(
    spatial_index,
    route,
    origin,
    usable_range_km,
    corridor_radius_km,
    connector=None,
    minimum_progress_km=None,
):
    """Mencari kandidat dalam usable range yang bergerak maju di koridor."""

    geometry = route if isinstance(route, RouteGeometry) else RouteGeometry(route)
    origin = _coordinate(origin)
    corridor_radius_km = float(corridor_radius_km)
    if not math.isfinite(corridor_radius_km) or corridor_radius_km <= 0:
        raise ValueError("Radius koridor harus lebih besar dari nol.")

    if minimum_progress_km is None:
        minimum_progress_km = geometry.project(origin).progress_km
    minimum_progress_km = float(minimum_progress_km)

    candidates = []
    for match in spatial_index.query_radius(
        origin,
        usable_range_km,
        connector=connector,
    ):
        projection = geometry.project(
            (match.node.latitude, match.node.longitude)
        )
        if projection.distance_to_route_km > corridor_radius_km:
            continue
        if projection.progress_km <= minimum_progress_km + DISTANCE_TOLERANCE_KM:
            continue

        candidates.append(
            CorridorCandidate(
                node=match.node,
                distance_to_route_km=projection.distance_to_route_km,
                route_progress_km=projection.progress_km,
                route_progress_ratio=projection.progress_ratio,
                straight_line_distance_km=match.distance_km,
            )
        )

    return tuple(
        sorted(candidates, key=lambda item: (item.route_progress_km, item.node.node_id))
    )

