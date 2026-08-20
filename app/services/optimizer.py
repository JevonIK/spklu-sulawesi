"""Dynamic Programming dengan state SOC untuk menyusun itinerary pengisian."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .energy import EnergyParameters, SOC_TOLERANCE, SocDiscretizer
from .graph import DESTINATION_NODE_ID, ORIGIN_NODE_ID, GraphEdge, TravelGraph


@dataclass(frozen=True)
class OptimizationCost:
    """Biaya leksikografis sebuah state DP."""

    primary_travel_cost: float
    charging_stop_count: int
    total_detour_km: float
    total_charged_soc_percent: float
    total_road_distance_km: float

    def key(self):
        return (
            round(self.primary_travel_cost, 8),
            self.charging_stop_count,
            round(self.total_detour_km, 8),
            round(self.total_charged_soc_percent, 8),
            round(self.total_road_distance_km, 8),
        )


@dataclass(frozen=True)
class DpTransition:
    """Predecessor yang digunakan untuk merekonstruksi solusi."""

    source_state: tuple[str, float]
    edge: GraphEdge
    source_arrival_soc_level: float
    departure_soc_level: float
    target_arrival_soc_level: float


@dataclass(frozen=True)
class _DpRecord:
    cost: OptimizationCost
    predecessor: DpTransition | None


@dataclass(frozen=True)
class OptimizationStats:
    processed_states: int
    evaluated_transitions: int
    energy_pruned_transitions: int
    accepted_state_updates: int
    destination_state_count: int

    def to_dict(self):
        return {
            "processed_states": self.processed_states,
            "evaluated_transitions": self.evaluated_transitions,
            "energy_pruned_transitions": self.energy_pruned_transitions,
            "accepted_state_updates": self.accepted_state_updates,
            "destination_state_count": self.destination_state_count,
        }


@dataclass(frozen=True)
class ItineraryLeg:
    sequence: int
    source_id: str
    source_name: str
    target_id: str
    target_name: str
    road_distance_km: float
    road_duration_minutes: float | None
    estimated_detour_km: float
    departure_soc_percent: float
    arrival_soc_percent: float
    consumption_soc_percent: float
    energy_distance_km: float
    ferry_distance_km: float
    ferry_duration_minutes: float

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "road_distance_km": self.road_distance_km,
            "road_duration_minutes": self.road_duration_minutes,
            "estimated_detour_km": self.estimated_detour_km,
            "departure_soc_percent": self.departure_soc_percent,
            "arrival_soc_percent": self.arrival_soc_percent,
            "consumption_soc_percent": self.consumption_soc_percent,
            "energy_distance_km": self.energy_distance_km,
            "ferry_distance_km": self.ferry_distance_km,
            "ferry_duration_minutes": self.ferry_duration_minutes,
            "contains_ferry": self.ferry_distance_km > 0,
        }


@dataclass(frozen=True)
class ChargingStop:
    sequence: int
    node_id: str
    name: str
    arrival_soc_percent: float
    departure_soc_percent: float
    charged_soc_percent: float
    station: dict | None

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "node_id": self.node_id,
            "name": self.name,
            "arrival_soc_percent": self.arrival_soc_percent,
            "departure_soc_percent": self.departure_soc_percent,
            "charged_soc_percent": self.charged_soc_percent,
            "station": self.station,
        }


@dataclass(frozen=True)
class Itinerary:
    legs: tuple[ItineraryLeg, ...]
    charging_stops: tuple[ChargingStop, ...]
    total_road_distance_km: float
    total_driving_duration_minutes: float | None
    total_detour_km: float
    final_soc_percent: float
    minimum_observed_soc_percent: float
    objective_mode: str
    objective_value: float
    total_energy_distance_km: float
    total_ferry_distance_km: float
    total_ferry_duration_minutes: float
    total_travel_duration_minutes: float | None

    def to_dict(self):
        return {
            "legs": [leg.to_dict() for leg in self.legs],
            "charging_stops": [stop.to_dict() for stop in self.charging_stops],
            "charging_stop_count": len(self.charging_stops),
            "total_road_distance_km": self.total_road_distance_km,
            "total_driving_duration_minutes": self.total_driving_duration_minutes,
            "total_detour_km": self.total_detour_km,
            "final_soc_percent": self.final_soc_percent,
            "minimum_observed_soc_percent": self.minimum_observed_soc_percent,
            "objective_mode": self.objective_mode,
            "objective_value": self.objective_value,
            "total_energy_distance_km": self.total_energy_distance_km,
            "total_ferry_distance_km": self.total_ferry_distance_km,
            "total_ferry_duration_minutes": self.total_ferry_duration_minutes,
            "total_travel_duration_minutes": self.total_travel_duration_minutes,
            "contains_ferry": self.total_ferry_distance_km > 0,
        }


@dataclass(frozen=True)
class OptimizationResult:
    feasible: bool
    reason: str
    message: str
    parameters: EnergyParameters
    initial_usable_range_km: float
    post_charge_usable_range_km: float
    stats: OptimizationStats
    itinerary: Itinerary | None = None

    def to_dict(self):
        return {
            "feasible": self.feasible,
            "reason": self.reason,
            "message": self.message,
            "parameters": self.parameters.to_dict(),
            "initial_usable_range_km": self.initial_usable_range_km,
            "post_charge_usable_range_km": self.post_charge_usable_range_km,
            "stats": self.stats.to_dict(),
            "itinerary": self.itinerary.to_dict() if self.itinerary else None,
        }


def _objective_mode(graph):
    return (
        "driving_duration_minutes"
        if graph.edges
        and all(edge.road_duration_minutes is not None for edge in graph.edges)
        else "road_distance_km"
    )


def _edge_primary_cost(edge, objective_mode):
    if objective_mode == "driving_duration_minutes":
        return float(edge.road_duration_minutes)
    return edge.road_distance_km


def _empty_stats(**overrides):
    values = {
        "processed_states": 0,
        "evaluated_transitions": 0,
        "energy_pruned_transitions": 0,
        "accepted_state_updates": 0,
        "destination_state_count": 0,
    }
    values.update(overrides)
    return OptimizationStats(**values)


def _cost_after_transition(
    current_cost,
    edge,
    objective_mode,
    charged_soc_percent,
    is_charging_stop,
):
    return OptimizationCost(
        primary_travel_cost=(
            current_cost.primary_travel_cost
            + _edge_primary_cost(edge, objective_mode)
        ),
        charging_stop_count=(
            current_cost.charging_stop_count + int(is_charging_stop)
        ),
        total_detour_km=current_cost.total_detour_km + edge.estimated_detour_km,
        total_charged_soc_percent=(
            current_cost.total_charged_soc_percent + charged_soc_percent
        ),
        total_road_distance_km=(
            current_cost.total_road_distance_km + edge.road_distance_km
        ),
    )


def _reconstruct_transitions(states, destination_state):
    transitions = []
    current_state = destination_state
    while current_state[0] != ORIGIN_NODE_ID:
        predecessor = states[current_state].predecessor
        if predecessor is None:
            raise RuntimeError("Rantai predecessor DP terputus.")
        transitions.append(predecessor)
        current_state = predecessor.source_state
    transitions.reverse()
    return tuple(transitions)


def simulate_itinerary(
    graph,
    transitions,
    parameters,
    current_soc_percent,
    objective_mode,
    objective_value,
):
    """Mensimulasikan ulang solusi memakai SOC kontinu untuk verifikasi akhir."""

    current_soc = parameters.validate_current_soc(current_soc_percent)
    legs = []
    stops = []
    minimum_observed_soc = current_soc
    all_durations_available = True

    for sequence, transition in enumerate(transitions, start=1):
        source_node = graph.node(transition.edge.source_id)
        target_node = graph.node(transition.edge.target_id)

        if source_node.kind == "station":
            departure_soc = max(current_soc, transition.departure_soc_level)
            charged_soc = max(0.0, departure_soc - current_soc)
            if charged_soc <= SOC_TOLERANCE:
                raise RuntimeError("Solusi mengunjungi SPKLU tanpa melakukan pengisian.")
            stops.append(
                ChargingStop(
                    sequence=len(stops) + 1,
                    node_id=source_node.node_id,
                    name=source_node.name,
                    arrival_soc_percent=current_soc,
                    departure_soc_percent=departure_soc,
                    charged_soc_percent=charged_soc,
                    station=(
                        source_node.station.to_dict(include_units=True)
                        if source_node.station
                        else None
                    ),
                )
            )
        else:
            departure_soc = current_soc

        consumption = parameters.consumption_percent(
            transition.edge.energy_distance_km
        )
        arrival_soc = departure_soc - consumption
        if arrival_soc + SOC_TOLERANCE < parameters.minimum_soc_percent:
            raise RuntimeError("Simulasi akhir menemukan pelanggaran SOC minimum.")

        minimum_observed_soc = min(minimum_observed_soc, arrival_soc)
        all_durations_available = (
            all_durations_available
            and transition.edge.road_duration_minutes is not None
        )
        legs.append(
            ItineraryLeg(
                sequence=sequence,
                source_id=source_node.node_id,
                source_name=source_node.name,
                target_id=target_node.node_id,
                target_name=target_node.name,
                road_distance_km=transition.edge.road_distance_km,
                road_duration_minutes=transition.edge.road_duration_minutes,
                estimated_detour_km=transition.edge.estimated_detour_km,
                departure_soc_percent=departure_soc,
                arrival_soc_percent=arrival_soc,
                consumption_soc_percent=consumption,
                energy_distance_km=transition.edge.energy_distance_km,
                ferry_distance_km=transition.edge.ferry_distance_km,
                ferry_duration_minutes=(
                    transition.edge.ferry_duration_minutes
                ),
            )
        )
        current_soc = arrival_soc

    return Itinerary(
        legs=tuple(legs),
        charging_stops=tuple(stops),
        total_road_distance_km=sum(leg.road_distance_km for leg in legs),
        total_driving_duration_minutes=(
            sum(
                max(
                    0.0,
                    float(leg.road_duration_minutes)
                    - leg.ferry_duration_minutes,
                )
                for leg in legs
            )
            if all_durations_available
            else None
        ),
        total_detour_km=sum(leg.estimated_detour_km for leg in legs),
        final_soc_percent=current_soc,
        minimum_observed_soc_percent=minimum_observed_soc,
        objective_mode=objective_mode,
        objective_value=objective_value,
        total_energy_distance_km=sum(
            leg.energy_distance_km for leg in legs
        ),
        total_ferry_distance_km=sum(
            leg.ferry_distance_km for leg in legs
        ),
        total_ferry_duration_minutes=sum(
            leg.ferry_duration_minutes for leg in legs
        ),
        total_travel_duration_minutes=(
            sum(float(leg.road_duration_minutes) for leg in legs)
            if all_durations_available
            else None
        ),
    )


def optimize_itinerary(
    graph: TravelGraph,
    *,
    current_soc_percent,
    parameters: EnergyParameters,
):
    """Mencari itinerary feasible dan terbaik dengan DP state (node, SOC)."""

    if not isinstance(graph, TravelGraph):
        raise TypeError("Optimizer memerlukan TravelGraph.")
    if not isinstance(parameters, EnergyParameters):
        raise TypeError("Optimizer memerlukan EnergyParameters.")

    current_soc = parameters.validate_current_soc(current_soc_percent)
    initial_usable_range = parameters.usable_range_km(current_soc)
    post_charge_usable_range = parameters.usable_range_km(
        parameters.target_soc_percent
    )
    if not graph.has_origin_to_destination_path():
        return OptimizationResult(
            feasible=False,
            reason="graph_disconnected",
            message="Graf tidak memiliki jalur dari lokasi awal ke tujuan.",
            parameters=parameters,
            initial_usable_range_km=initial_usable_range,
            post_charge_usable_range_km=post_charge_usable_range,
            stats=_empty_stats(),
        )

    discretizer = SocDiscretizer(parameters)
    # SOC awal diketahui dari input dan tidak boleh dibuang ke grid. Membulatkan
    # nilai ini dapat menciptakan surplus SOC kontinu pada station pertama,
    # sehingga DP merencanakan "pengisian" ke level yang ternyata sudah
    # terlampaui kendaraan saat simulasi akhir. Setelah leg pertama, state SOC
    # tetap dikuantisasi turun secara konservatif seperti semula.
    initial_level = current_soc
    objective_mode = _objective_mode(graph)
    states = {
        (ORIGIN_NODE_ID, initial_level): _DpRecord(
            cost=OptimizationCost(0.0, 0, 0.0, 0.0, 0.0),
            predecessor=None,
        )
    }

    processed_states = 0
    evaluated_transitions = 0
    energy_pruned_transitions = 0
    accepted_state_updates = 0

    ordered_nodes = sorted(
        graph.nodes, key=lambda node: (node.route_progress_km, node.node_id)
    )
    for node in ordered_nodes:
        node_states = sorted(
            (
                (state_key, record)
                for state_key, record in states.items()
                if state_key[0] == node.node_id
            ),
            key=lambda item: item[0][1],
        )
        for state_key, record in node_states:
            processed_states += 1
            arrival_level = state_key[1]

            if node.kind == "destination":
                continue
            if node.kind == "origin":
                departure_levels = (arrival_level,)
            else:
                # Setiap station yang dipilih merupakan pemberhentian pengisian.
                departure_levels = discretizer.charging_levels(arrival_level)

            for departure_level in departure_levels:
                charged_soc = max(0.0, departure_level - arrival_level)
                is_charging_stop = node.kind == "station"
                for edge in graph.outgoing_edges(node.node_id):
                    evaluated_transitions += 1
                    continuous_arrival = parameters.arrival_soc_percent(
                        departure_level, edge.energy_distance_km
                    )
                    if (
                        continuous_arrival + SOC_TOLERANCE
                        < parameters.minimum_soc_percent
                    ):
                        energy_pruned_transitions += 1
                        continue

                    arrival_state_level = discretizer.quantize_down(
                        continuous_arrival
                    )
                    target_state = (edge.target_id, arrival_state_level)
                    candidate_cost = _cost_after_transition(
                        record.cost,
                        edge,
                        objective_mode,
                        charged_soc,
                        is_charging_stop,
                    )
                    existing = states.get(target_state)
                    if existing is not None and existing.cost.key() <= candidate_cost.key():
                        continue

                    states[target_state] = _DpRecord(
                        cost=candidate_cost,
                        predecessor=DpTransition(
                            source_state=state_key,
                            edge=edge,
                            source_arrival_soc_level=arrival_level,
                            departure_soc_level=departure_level,
                            target_arrival_soc_level=arrival_state_level,
                        ),
                    )
                    accepted_state_updates += 1

    destination_states = [
        (state_key, record)
        for state_key, record in states.items()
        if state_key[0] == DESTINATION_NODE_ID
    ]
    stats = OptimizationStats(
        processed_states=processed_states,
        evaluated_transitions=evaluated_transitions,
        energy_pruned_transitions=energy_pruned_transitions,
        accepted_state_updates=accepted_state_updates,
        destination_state_count=len(destination_states),
    )
    if not destination_states:
        return OptimizationResult(
            feasible=False,
            reason="soc_infeasible",
            message=(
                "Tidak ada itinerary yang dapat mempertahankan SOC pada atau "
                "di atas batas minimum."
            ),
            parameters=parameters,
            initial_usable_range_km=initial_usable_range,
            post_charge_usable_range_km=post_charge_usable_range,
            stats=stats,
        )

    best_state, best_record = min(
        destination_states,
        key=lambda item: (item[1].cost.key(), -item[0][1]),
    )
    transitions = _reconstruct_transitions(states, best_state)
    itinerary = simulate_itinerary(
        graph,
        transitions,
        parameters,
        current_soc,
        objective_mode,
        best_record.cost.primary_travel_cost,
    )
    if len(itinerary.charging_stops) != best_record.cost.charging_stop_count:
        raise RuntimeError("Jumlah pengisian hasil rekonstruksi tidak konsisten.")

    return OptimizationResult(
        feasible=True,
        reason="feasible",
        message=(
            "Perjalanan feasible tanpa pengisian daya."
            if not itinerary.charging_stops
            else "Itinerary pengisian daya berhasil ditemukan."
        ),
        parameters=parameters,
        initial_usable_range_km=initial_usable_range,
        post_charge_usable_range_km=post_charge_usable_range,
        stats=stats,
        itinerary=itinerary,
    )
