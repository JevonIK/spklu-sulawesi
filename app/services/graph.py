"""Pembentukan graf berarah origin-SPKLU-destination."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .dataset import StationNode, parse_connectors
from .road_metrics import RoadMetricBatch, RoadMetricProvider, RoadMetricRequest
from .spatial import (
    DISTANCE_TOLERANCE_KM,
    CorridorCandidate,
    RouteGeometry,
    haversine_distance_km,
    normalize_coordinate,
)


# Haversine memakai bola rata-rata, sedangkan Routes memakai model jalan di atas
# ellipsoid. Margin 1% mencegah straight-line spherical distance diperlakukan
# keliru sebagai lower bound eksak di dekat ambang jangkauan.
GEODESIC_LOWER_BOUND_MARGIN_RATIO = 0.01
ROAD_DISTANCE_ABSOLUTE_TOLERANCE_KM = 0.05


ORIGIN_NODE_ID = "origin"
DESTINATION_NODE_ID = "destination"


@dataclass(frozen=True)
class GraphNode:
    """Node origin, SPKLU, atau destination pada graf perjalanan."""

    node_id: str
    kind: str
    name: str
    coordinate: tuple[float, float]
    route_progress_km: float
    station: StationNode | None = None

    def to_dict(self):
        payload = {
            "id": self.node_id,
            "kind": self.kind,
            "name": self.name,
            "latitude": self.coordinate[0],
            "longitude": self.coordinate[1],
            "route_progress_km": self.route_progress_km,
        }
        if self.station is not None:
            payload["station"] = self.station.to_dict(include_units=True)
        return payload


@dataclass(frozen=True)
class GraphEdge:
    """Transisi berarah yang telah lolos validasi jarak jalan."""

    source_id: str
    target_id: str
    geodesic_distance_km: float
    road_distance_km: float
    road_duration_minutes: float | None
    route_progress_delta_km: float
    estimated_detour_km: float
    usable_range_limit_km: float
    energy_distance_km: float | None = None
    ferry_distance_km: float = 0.0
    ferry_duration_minutes: float = 0.0

    def __post_init__(self):
        energy_distance = (
            self.road_distance_km
            if self.energy_distance_km is None
            else float(self.energy_distance_km)
        )
        ferry_distance = float(self.ferry_distance_km)
        ferry_duration = float(self.ferry_duration_minutes)
        if not math.isfinite(energy_distance) or energy_distance < 0:
            raise ValueError("Jarak konsumsi energi edge tidak valid.")
        if not math.isfinite(ferry_distance) or ferry_distance < 0:
            raise ValueError("Jarak feri edge tidak valid.")
        if not math.isfinite(ferry_duration) or ferry_duration < 0:
            raise ValueError("Durasi feri edge tidak valid.")
        if (
            energy_distance + ferry_distance
            > self.road_distance_km + ROAD_DISTANCE_ABSOLUTE_TOLERANCE_KM
        ):
            raise ValueError("Komponen jarak edge melebihi jarak total.")
        object.__setattr__(self, "energy_distance_km", energy_distance)
        object.__setattr__(self, "ferry_distance_km", ferry_distance)
        object.__setattr__(self, "ferry_duration_minutes", ferry_duration)

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "geodesic_distance_km": self.geodesic_distance_km,
            "road_distance_km": self.road_distance_km,
            "road_duration_minutes": self.road_duration_minutes,
            "energy_distance_km": self.energy_distance_km,
            "ferry_distance_km": self.ferry_distance_km,
            "ferry_duration_minutes": self.ferry_duration_minutes,
            "contains_ferry": self.ferry_distance_km > 0,
            "route_progress_delta_km": self.route_progress_delta_km,
            "estimated_detour_km": self.estimated_detour_km,
            "usable_range_limit_km": self.usable_range_limit_km,
        }


@dataclass(frozen=True)
class GraphBuildStats:
    """Statistik pemangkasan untuk evaluasi efisiensi pembentukan graf."""

    input_candidate_nodes: int
    compatible_station_nodes: int
    possible_forward_pairs: int
    geodesic_pruned_pairs: int
    road_metric_pairs: int
    unavailable_road_pairs: int
    road_distance_pruned_pairs: int
    detour_pruned_pairs: int
    accepted_edges: int
    external_request_count: int
    ferry_adjusted_pairs: int = 0
    estimated_ferry_distance_km: float = 0.0

    def to_dict(self):
        return {
            "input_candidate_nodes": self.input_candidate_nodes,
            "compatible_station_nodes": self.compatible_station_nodes,
            "possible_forward_pairs": self.possible_forward_pairs,
            "geodesic_pruned_pairs": self.geodesic_pruned_pairs,
            "road_metric_pairs": self.road_metric_pairs,
            "unavailable_road_pairs": self.unavailable_road_pairs,
            "road_distance_pruned_pairs": self.road_distance_pruned_pairs,
            "detour_pruned_pairs": self.detour_pruned_pairs,
            "accepted_edges": self.accepted_edges,
            "external_request_count": self.external_request_count,
            "ferry_adjusted_pairs": self.ferry_adjusted_pairs,
            "estimated_ferry_distance_km": self.estimated_ferry_distance_km,
        }


@dataclass(frozen=True)
class FerryProgressInterval:
    """Segmen feri pada progres polyline rute dasar."""

    start_progress_km: float
    end_progress_km: float
    distance_km: float
    duration_minutes: float
    maneuver: str = "FERRY"

    def __post_init__(self):
        values = (
            self.start_progress_km,
            self.end_progress_km,
            self.distance_km,
            self.duration_minutes,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Segmen feri harus memakai angka finite.")
        if self.start_progress_km < 0:
            raise ValueError("Progres awal feri tidak boleh negatif.")
        if self.end_progress_km <= self.start_progress_km:
            raise ValueError("Progres akhir feri harus lebih besar dari awal.")
        if self.distance_km <= 0 or self.duration_minutes < 0:
            raise ValueError("Jarak/durasi feri tidak valid.")


def ferry_distance_between(intervals, start_progress_km, end_progress_km):
    """Mengestimasi jarak feri yang tumpang tindih dengan satu edge maju."""

    start = float(start_progress_km)
    end = float(end_progress_km)
    if end <= start:
        return 0.0
    total = 0.0
    for interval in intervals:
        overlap = max(
            0.0,
            min(end, interval.end_progress_km)
            - max(start, interval.start_progress_km),
        )
        interval_progress = (
            interval.end_progress_km - interval.start_progress_km
        )
        if overlap > 0:
            total += interval.distance_km * overlap / interval_progress
    return total


def ferry_duration_between(intervals, start_progress_km, end_progress_km):
    """Mengestimasi durasi feri yang tumpang tindih dengan satu edge maju."""

    start = float(start_progress_km)
    end = float(end_progress_km)
    if end <= start:
        return 0.0
    total = 0.0
    for interval in intervals:
        overlap = max(
            0.0,
            min(end, interval.end_progress_km)
            - max(start, interval.start_progress_km),
        )
        interval_progress = (
            interval.end_progress_km - interval.start_progress_km
        )
        if overlap > 0:
            total += interval.duration_minutes * overlap / interval_progress
    return total


@dataclass(frozen=True)
class TravelGraph:
    """Directed acyclic graph yang diurutkan menurut progres rute."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    stats: GraphBuildStats

    def __post_init__(self):
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Graf memiliki ID node yang duplikat.")

        known_ids = set(node_ids)
        for edge in self.edges:
            if edge.source_id not in known_ids or edge.target_id not in known_ids:
                raise ValueError("Edge merujuk node yang tidak terdapat pada graf.")

    def node(self, node_id):
        for graph_node in self.nodes:
            if graph_node.node_id == node_id:
                return graph_node
        raise KeyError(node_id)

    def outgoing_edges(self, node_id):
        return tuple(edge for edge in self.edges if edge.source_id == node_id)

    def reachable_node_ids(self, start_id=ORIGIN_NODE_ID):
        reachable = {start_id}
        frontier = [start_id]
        while frontier:
            source_id = frontier.pop()
            for edge in self.outgoing_edges(source_id):
                if edge.target_id not in reachable:
                    reachable.add(edge.target_id)
                    frontier.append(edge.target_id)
        return frozenset(reachable)

    def has_origin_to_destination_path(self):
        return DESTINATION_NODE_ID in self.reachable_node_ids()

    def to_dict(self):
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "stats": self.stats.to_dict(),
            "has_origin_to_destination_path": self.has_origin_to_destination_path(),
        }


@dataclass(frozen=True)
class _PendingEdge:
    request: RoadMetricRequest
    source: GraphNode
    target: GraphNode
    usable_range_limit_km: float
    route_progress_delta_km: float
    estimated_ferry_distance_km: float
    estimated_ferry_duration_minutes: float


def _positive_distance(value, label):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} harus lebih besar dari nol.")
    return value


def _graph_nodes(origin, destination, route, candidates, connector):
    normalized_connectors = (
        frozenset(parse_connectors(connector)) if connector else None
    )
    compatible = {}

    for candidate in candidates:
        if not isinstance(candidate, CorridorCandidate):
            raise TypeError("Kandidat graf harus berupa CorridorCandidate.")
        if (
            normalized_connectors is not None
            and normalized_connectors.isdisjoint(candidate.node.connectors)
        ):
            continue
        if candidate.route_progress_km <= DISTANCE_TOLERANCE_KM:
            continue
        if (
            candidate.route_progress_km
            >= route.total_distance_km - DISTANCE_TOLERANCE_KM
        ):
            continue
        compatible[candidate.node.node_id] = candidate

    station_nodes = [
        GraphNode(
            node_id=candidate.node.node_id,
            kind="station",
            name=candidate.node.name,
            coordinate=(candidate.node.latitude, candidate.node.longitude),
            route_progress_km=candidate.route_progress_km,
            station=candidate.node,
        )
        for candidate in compatible.values()
    ]
    station_nodes.sort(key=lambda node: (node.route_progress_km, node.node_id))

    nodes = [
        GraphNode(
            node_id=ORIGIN_NODE_ID,
            kind="origin",
            name="Lokasi awal",
            coordinate=origin,
            route_progress_km=0.0,
        ),
        *station_nodes,
        GraphNode(
            node_id=DESTINATION_NODE_ID,
            kind="destination",
            name="Lokasi tujuan",
            coordinate=destination,
            route_progress_km=route.total_distance_km,
        ),
    ]
    return tuple(nodes), len(compatible)


def _empty_batch():
    return RoadMetricBatch(results=(), external_request_count=0)


def build_travel_graph(
    *,
    origin,
    destination,
    route,
    candidates,
    connector,
    initial_usable_range_km,
    post_charge_usable_range_km,
    road_metric_provider: RoadMetricProvider,
    max_edge_detour_km=None,
    ferry_intervals=(),
):
    """Membentuk graf feasible dengan pemangkasan sebelum validasi jalan."""

    geometry = route if isinstance(route, RouteGeometry) else RouteGeometry(route)
    origin = (
        geometry.coordinates[0]
        if origin is None
        else normalize_coordinate(origin)
    )
    destination = (
        geometry.coordinates[-1]
        if destination is None
        else normalize_coordinate(destination)
    )
    initial_range = _positive_distance(
        initial_usable_range_km, "Initial usable range"
    )
    post_charge_range = _positive_distance(
        post_charge_usable_range_km, "Post-charge usable range"
    )
    if max_edge_detour_km is not None:
        max_edge_detour_km = _positive_distance(
            max_edge_detour_km, "Batas detour edge"
        )

    candidates = tuple(candidates)
    ferry_intervals = tuple(ferry_intervals)
    if any(
        not isinstance(interval, FerryProgressInterval)
        for interval in ferry_intervals
    ):
        raise TypeError("Interval feri harus berupa FerryProgressInterval.")
    nodes, compatible_count = _graph_nodes(
        origin,
        destination,
        geometry,
        candidates,
        connector,
    )

    possible_forward_pairs = 0
    geodesic_pruned_pairs = 0
    pending_edges = []
    for source_index, source in enumerate(nodes[:-1]):
        usable_range_limit = (
            initial_range if source.kind == "origin" else post_charge_range
        )
        for target in nodes[source_index + 1 :]:
            if (
                target.route_progress_km
                <= source.route_progress_km + DISTANCE_TOLERANCE_KM
            ):
                continue

            possible_forward_pairs += 1
            route_progress_delta = (
                target.route_progress_km - source.route_progress_km
            )
            estimated_ferry_distance = ferry_distance_between(
                ferry_intervals,
                source.route_progress_km,
                target.route_progress_km,
            )
            estimated_ferry_duration = ferry_duration_between(
                ferry_intervals,
                source.route_progress_km,
                target.route_progress_km,
            )
            geodesic_distance = haversine_distance_km(
                source.coordinate, target.coordinate
            )
            conservative_lower_bound = geodesic_distance * (
                1 - GEODESIC_LOWER_BOUND_MARGIN_RATIO
            )
            if (
                estimated_ferry_distance <= DISTANCE_TOLERANCE_KM
                and
                conservative_lower_bound
                > usable_range_limit + DISTANCE_TOLERANCE_KM
            ):
                geodesic_pruned_pairs += 1
                continue

            request = RoadMetricRequest(
                request_id=f"{source.node_id}->{target.node_id}",
                origin=source.coordinate,
                destination=target.coordinate,
                geodesic_distance_km=geodesic_distance,
            )
            pending_edges.append(
                _PendingEdge(
                    request=request,
                    source=source,
                    target=target,
                    usable_range_limit_km=usable_range_limit,
                    route_progress_delta_km=route_progress_delta,
                    estimated_ferry_distance_km=estimated_ferry_distance,
                    estimated_ferry_duration_minutes=estimated_ferry_duration,
                )
            )

    batch = (
        road_metric_provider.fetch(
            tuple(pending.request for pending in pending_edges)
        )
        if pending_edges
        else _empty_batch()
    )
    if not isinstance(batch, RoadMetricBatch):
        raise TypeError("Provider harus mengembalikan RoadMetricBatch.")

    requested_ids = {pending.request.request_id for pending in pending_edges}
    result_by_id = batch.by_request_id()
    unexpected_ids = set(result_by_id) - requested_ids
    if unexpected_ids:
        raise ValueError(
            "Provider mengembalikan hasil yang tidak diminta: "
            + ", ".join(sorted(unexpected_ids))
        )

    edges = []
    unavailable_road_pairs = 0
    road_distance_pruned_pairs = 0
    detour_pruned_pairs = 0
    for pending in pending_edges:
        result = result_by_id.get(pending.request.request_id)
        if result is None:
            unavailable_road_pairs += 1
            continue

        conservative_lower_bound = pending.request.geodesic_distance_km * (
            1 - GEODESIC_LOWER_BOUND_MARGIN_RATIO
        )
        if (
            result.distance_km + ROAD_DISTANCE_ABSOLUTE_TOLERANCE_KM
            < conservative_lower_bound
        ):
            raise ValueError(
                f"Jarak jalan {pending.request.request_id} lebih pendek "
                "daripada jarak geodesik."
            )
        ferry_distance = min(
            result.distance_km,
            pending.estimated_ferry_distance_km,
        )
        energy_distance = max(0.0, result.distance_km - ferry_distance)
        if (
            energy_distance
            > pending.usable_range_limit_km + DISTANCE_TOLERANCE_KM
        ):
            road_distance_pruned_pairs += 1
            continue

        estimated_detour = max(
            0.0,
            result.distance_km - pending.route_progress_delta_km,
        )
        if (
            max_edge_detour_km is not None
            and estimated_detour > max_edge_detour_km
        ):
            detour_pruned_pairs += 1
            continue

        edges.append(
            GraphEdge(
                source_id=pending.source.node_id,
                target_id=pending.target.node_id,
                geodesic_distance_km=pending.request.geodesic_distance_km,
                road_distance_km=result.distance_km,
                road_duration_minutes=result.duration_minutes,
                route_progress_delta_km=pending.route_progress_delta_km,
                estimated_detour_km=estimated_detour,
                usable_range_limit_km=pending.usable_range_limit_km,
                energy_distance_km=energy_distance,
                ferry_distance_km=ferry_distance,
                ferry_duration_minutes=min(
                    result.duration_minutes
                    if result.duration_minutes is not None
                    else pending.estimated_ferry_duration_minutes,
                    pending.estimated_ferry_duration_minutes,
                ),
            )
        )

    stats = GraphBuildStats(
        input_candidate_nodes=len(candidates),
        compatible_station_nodes=compatible_count,
        possible_forward_pairs=possible_forward_pairs,
        geodesic_pruned_pairs=geodesic_pruned_pairs,
        road_metric_pairs=len(pending_edges),
        unavailable_road_pairs=unavailable_road_pairs,
        road_distance_pruned_pairs=road_distance_pruned_pairs,
        detour_pruned_pairs=detour_pruned_pairs,
        accepted_edges=len(edges),
        external_request_count=batch.external_request_count,
        ferry_adjusted_pairs=sum(
            pending.estimated_ferry_distance_km > DISTANCE_TOLERANCE_KM
            for pending in pending_edges
        ),
        estimated_ferry_distance_km=sum(
            pending.estimated_ferry_distance_km
            for pending in pending_edges
        ),
    )
    return TravelGraph(nodes=nodes, edges=tuple(edges), stats=stats)
