import random

import pytest

from app.services.dataset import StationNode, StationUnit
from app.services.energy import EnergyParameters, SOC_TOLERANCE, SocDiscretizer
from app.services.graph import (
    DESTINATION_NODE_ID,
    ORIGIN_NODE_ID,
    GraphBuildStats,
    GraphEdge,
    GraphNode,
    TravelGraph,
    build_travel_graph,
)
from app.services.optimizer import optimize_itinerary
from app.services.road_metrics import RoadMetricBatch, RoadMetricResult
from app.services.spatial import CorridorCandidate, RouteGeometry


def empty_graph_stats(edge_count):
    return GraphBuildStats(
        input_candidate_nodes=0,
        compatible_station_nodes=0,
        possible_forward_pairs=edge_count,
        geodesic_pruned_pairs=0,
        road_metric_pairs=edge_count,
        unavailable_road_pairs=0,
        road_distance_pruned_pairs=0,
        detour_pruned_pairs=0,
        accepted_edges=edge_count,
        external_request_count=0,
    )


def graph_node(node_id, kind, progress):
    names = {
        "origin": "Lokasi awal",
        "destination": "Lokasi tujuan",
    }
    return GraphNode(
        node_id=node_id,
        kind=kind,
        name=names.get(kind, node_id),
        coordinate=(0, progress / 100),
        route_progress_km=progress,
    )


def graph_edge(
    source,
    target,
    distance,
    duration=None,
    detour=0,
):
    return GraphEdge(
        source_id=source,
        target_id=target,
        geodesic_distance_km=distance * 0.9,
        road_distance_km=distance,
        road_duration_minutes=duration,
        route_progress_delta_km=max(0, distance - detour),
        estimated_detour_km=detour,
        usable_range_limit_km=1000,
    )


def travel_graph(nodes, edges):
    return TravelGraph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        stats=empty_graph_stats(len(edges)),
    )


def default_parameters(**overrides):
    values = {
        "maximum_range_km": 250,
        "minimum_soc_percent": 20,
        "target_soc_percent": 80,
        "safety_factor": 1,
        "soc_step_percent": 5,
    }
    values.update(overrides)
    return EnergyParameters(**values)


def _rounded_oracle_cost(cost):
    """Menyamakan presisi pembanding publik tanpa memakai implementasi DP."""

    return (
        round(cost[0], 8),
        cost[1],
        round(cost[2], 8),
        round(cost[3], 8),
        round(cost[4], 8),
    )


def _exhaustive_oracle(graph, current_soc_percent, parameters):
    """Enumerasi semua itinerary dan keputusan pengisian pada DAG kecil."""

    discretizer = SocDiscretizer(parameters)
    initial_level = parameters.validate_current_soc(current_soc_percent)
    use_duration = bool(graph.edges) and all(
        edge.road_duration_minutes is not None for edge in graph.edges
    )
    destination_candidates = []

    def visit(node_id, arrival_level, cost):
        if node_id == DESTINATION_NODE_ID:
            destination_candidates.append(
                (_rounded_oracle_cost(cost), -arrival_level)
            )
            return

        node = graph.node(node_id)
        departure_levels = (
            (arrival_level,)
            if node.kind == "origin"
            else discretizer.charging_levels(arrival_level)
        )
        for departure_level in departure_levels:
            charged_soc = max(0.0, departure_level - arrival_level)
            for edge in graph.outgoing_edges(node_id):
                continuous_arrival = parameters.arrival_soc_percent(
                    departure_level, edge.road_distance_km
                )
                if (
                    continuous_arrival + SOC_TOLERANCE
                    < parameters.minimum_soc_percent
                ):
                    continue

                primary_edge_cost = (
                    float(edge.road_duration_minutes)
                    if use_duration
                    else edge.road_distance_km
                )
                visit(
                    edge.target_id,
                    discretizer.quantize_down(continuous_arrival),
                    (
                        cost[0] + primary_edge_cost,
                        cost[1] + int(node.kind == "station"),
                        cost[2] + edge.estimated_detour_km,
                        cost[3] + charged_soc,
                        cost[4] + edge.road_distance_km,
                    ),
                )

    visit(ORIGIN_NODE_ID, initial_level, (0.0, 0, 0.0, 0.0, 0.0))
    return min(destination_candidates) if destination_candidates else None


def _optimizer_selection_key(result, current_soc_percent, parameters):
    """Turunkan kembali key DP dari itinerary publik untuk dibandingkan oracle."""

    itinerary = result.itinerary
    discretizer = SocDiscretizer(parameters)
    arrival_level = parameters.validate_current_soc(current_soc_percent)
    discretized_charged_soc = 0.0
    charging_stops = iter(itinerary.charging_stops)
    for leg in itinerary.legs:
        if leg.source_id == ORIGIN_NODE_ID:
            departure_level = arrival_level
        else:
            stop = next(charging_stops)
            assert stop.node_id == leg.source_id
            departure_level = stop.departure_soc_percent
            discretized_charged_soc += departure_level - arrival_level
        arrival_level = discretizer.quantize_down(
            parameters.arrival_soc_percent(
                departure_level, leg.road_distance_km
            )
        )
    cost = _rounded_oracle_cost(
        (
            itinerary.objective_value,
            len(itinerary.charging_stops),
            itinerary.total_detour_km,
            discretized_charged_soc,
            itinerary.total_road_distance_km,
        )
    )
    return cost, -arrival_level


def test_direct_trip_requires_no_charging_stop():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node(DESTINATION_NODE_ID, "destination", 60),
        ),
        (graph_edge(ORIGIN_NODE_ID, DESTINATION_NODE_ID, 60, duration=75),),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert result.feasible is True
    assert result.reason == "feasible"
    assert result.itinerary.charging_stops == ()
    assert result.itinerary.final_soc_percent == pytest.approx(30)
    assert result.itinerary.objective_mode == "driving_duration_minutes"
    assert result.itinerary.objective_value == pytest.approx(75)


def test_multistop_itinerary_charges_only_as_much_as_needed_for_tie():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 100),
            graph_node(DESTINATION_NODE_ID, "destination", 200),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, "station-a", 100, duration=100),
            graph_edge("station-a", DESTINATION_NODE_ID, 100, duration=100),
        ),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=default_parameters(),
    )

    assert result.feasible is True
    assert len(result.itinerary.charging_stops) == 1
    stop = result.itinerary.charging_stops[0]
    assert stop.arrival_soc_percent == pytest.approx(20)
    assert stop.departure_soc_percent == pytest.approx(60)
    assert stop.charged_soc_percent == pytest.approx(40)
    assert result.itinerary.final_soc_percent == pytest.approx(20)
    assert result.itinerary.minimum_observed_soc_percent >= 20


def test_initial_soc_outside_grid_still_plans_a_real_charge_at_first_station():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 10),
            graph_node(DESTINATION_NODE_ID, "destination", 20),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, "station-a", 10),
            graph_edge("station-a", DESTINATION_NODE_ID, 10),
        ),
    )
    parameters = default_parameters(
        maximum_range_km=160,
        target_soc_percent=100,
        soc_step_percent=25,
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=80,
        parameters=parameters,
    )

    assert result.feasible is True
    assert len(result.itinerary.charging_stops) == 1
    stop = result.itinerary.charging_stops[0]
    assert stop.arrival_soc_percent == pytest.approx(73.75)
    assert stop.departure_soc_percent == pytest.approx(95)
    assert stop.charged_soc_percent == pytest.approx(21.25)


def test_driving_duration_is_primary_objective():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 40),
            graph_node("station-b", "station", 50),
            graph_node(DESTINATION_NODE_ID, "destination", 100),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, "station-a", 40, duration=40),
            graph_edge("station-a", DESTINATION_NODE_ID, 60, duration=40),
            graph_edge(ORIGIN_NODE_ID, "station-b", 50, duration=20),
            graph_edge("station-b", DESTINATION_NODE_ID, 50, duration=20),
        ),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=50,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert [stop.node_id for stop in result.itinerary.charging_stops] == [
        "station-b"
    ]
    assert result.itinerary.objective_value == pytest.approx(40)


def test_fewer_charging_stops_wins_when_travel_time_is_equal():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 50),
            graph_node(DESTINATION_NODE_ID, "destination", 100),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, DESTINATION_NODE_ID, 100, duration=40),
            graph_edge(ORIGIN_NODE_ID, "station-a", 50, duration=20),
            graph_edge("station-a", DESTINATION_NODE_ID, 50, duration=20),
        ),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=80,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert result.itinerary.charging_stops == ()
    assert len(result.itinerary.legs) == 1


def test_lower_detour_wins_after_time_and_stop_count():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 40),
            graph_node("station-b", "station", 50),
            graph_node(DESTINATION_NODE_ID, "destination", 100),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, "station-a", 45, duration=30, detour=5),
            graph_edge("station-a", DESTINATION_NODE_ID, 65, duration=30, detour=5),
            graph_edge(ORIGIN_NODE_ID, "station-b", 52, duration=30, detour=2),
            graph_edge("station-b", DESTINATION_NODE_ID, 52, duration=30, detour=2),
        ),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=50,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert [stop.node_id for stop in result.itinerary.charging_stops] == [
        "station-b"
    ]
    assert result.itinerary.total_detour_km == pytest.approx(4)


def test_distance_is_used_when_duration_is_not_available():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node(DESTINATION_NODE_ID, "destination", 50),
        ),
        (graph_edge(ORIGIN_NODE_ID, DESTINATION_NODE_ID, 50),),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert result.itinerary.objective_mode == "road_distance_km"
    assert result.itinerary.objective_value == pytest.approx(50)
    assert result.itinerary.total_driving_duration_minutes is None


def test_structurally_disconnected_graph_has_specific_reason():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node(DESTINATION_NODE_ID, "destination", 100),
        ),
        (),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=default_parameters(),
    )

    assert result.feasible is False
    assert result.reason == "graph_disconnected"
    assert result.itinerary is None


def test_soc_infeasible_graph_has_no_destination_state():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node("station-a", "station", 50),
            graph_node(DESTINATION_NODE_ID, "destination", 250),
        ),
        (
            graph_edge(ORIGIN_NODE_ID, "station-a", 50, duration=50),
            graph_edge("station-a", DESTINATION_NODE_ID, 200, duration=200),
        ),
    )

    result = optimize_itinerary(
        graph,
        current_soc_percent=50,
        parameters=default_parameters(maximum_range_km=200),
    )

    assert result.feasible is False
    assert result.reason == "soc_infeasible"
    assert result.stats.energy_pruned_transitions > 0


def test_dynamic_programming_matches_exhaustive_oracle_on_seeded_small_dags():
    """DP harus identik dengan brute force pada banyak DAG kecil deterministik."""

    seed = 20260819
    rng = random.Random(seed)
    feasible_case_count = 0
    infeasible_case_count = 0

    for case_index in range(96):
        parameters = EnergyParameters(
            maximum_range_km=rng.choice((100, 120, 160)),
            minimum_soc_percent=20,
            target_soc_percent=rng.choice((60, 80, 100)),
            safety_factor=rng.choice((0.8, 0.9, 1.0)),
            soc_step_percent=rng.choice((20, 25)),
        )
        current_soc = rng.choice((40, 60, 80, 100))
        station_count = rng.randint(0, 4)
        station_ids = [f"station-{index}" for index in range(station_count)]
        ordered_ids = [ORIGIN_NODE_ID, *station_ids, DESTINATION_NODE_ID]
        nodes = [graph_node(ORIGIN_NODE_ID, "origin", 0)]
        nodes.extend(
            graph_node(node_id, "station", (index + 1) * 20)
            for index, node_id in enumerate(station_ids)
        )
        nodes.append(
            graph_node(
                DESTINATION_NODE_ID,
                "destination",
                (station_count + 1) * 20,
            )
        )

        duration_profile = case_index % 3
        edges = []
        for source_index, source_id in enumerate(ordered_ids[:-1]):
            for target_index in range(source_index + 1, len(ordered_ids)):
                if rng.random() >= 0.62:
                    continue
                target_id = ordered_ids[target_index]
                distance = rng.choice(
                    (10, 20, 30, 40, 50, 60, 70, 80, 90)
                )
                duration = rng.choice((12, 18, 25, 35, 50, 70, 95))
                if duration_profile == 1:
                    duration = None
                elif duration_profile == 2 and (
                    source_index + target_index + case_index
                ) % 3 == 0:
                    duration = None
                edges.append(
                    graph_edge(
                        source_id,
                        target_id,
                        distance,
                        duration=duration,
                        detour=rng.choice((0, 1, 2, 4, 7)),
                    )
                )

        graph = travel_graph(nodes, edges)
        oracle_key = _exhaustive_oracle(graph, current_soc, parameters)
        result = optimize_itinerary(
            graph,
            current_soc_percent=current_soc,
            parameters=parameters,
        )
        diagnostic = f"seed={seed}, case={case_index}"

        assert result.feasible is (oracle_key is not None), diagnostic
        if oracle_key is None:
            infeasible_case_count += 1
            assert result.itinerary is None, diagnostic
            continue

        feasible_case_count += 1
        assert (
            _optimizer_selection_key(result, current_soc, parameters)
            == oracle_key
        ), diagnostic

    assert feasible_case_count > 0
    assert infeasible_case_count > 0


def test_result_serialization_contains_leg_soc_and_parameters():
    graph = travel_graph(
        (
            graph_node(ORIGIN_NODE_ID, "origin", 0),
            graph_node(DESTINATION_NODE_ID, "destination", 60),
        ),
        (graph_edge(ORIGIN_NODE_ID, DESTINATION_NODE_ID, 60, duration=75),),
    )

    payload = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=default_parameters(maximum_range_km=200),
    ).to_dict()

    assert payload["feasible"] is True
    assert payload["parameters"]["minimum_soc_percent"] == 20
    assert payload["itinerary"]["legs"][0]["arrival_soc_percent"] == 30


def test_spatial_candidate_graph_and_optimizer_work_as_one_pipeline():
    unit = StationUnit(
        source_row=2,
        province="Sulawesi Selatan",
        city="Kota Uji",
        name="SPKLU Tengah",
        address="Alamat Uji",
        latitude=0,
        longitude=0.3,
        maps_url="https://maps.app.goo.gl/uji",
        connectors=("CCS2",),
    )
    station = StationNode(
        node_id="station-tengah",
        name=unit.name,
        province=unit.province,
        city=unit.city,
        address=unit.address,
        latitude=unit.latitude,
        longitude=unit.longitude,
        maps_url=unit.maps_url,
        connectors=unit.connectors,
        units=(unit,),
    )
    route = RouteGeometry(((0, 0), (0, 0.6)))
    candidate = CorridorCandidate(
        node=station,
        distance_to_route_km=0,
        route_progress_km=route.total_distance_km / 2,
        route_progress_ratio=0.5,
    )

    class ExactRoadMetricProvider:
        def fetch(self, requests):
            return RoadMetricBatch(
                results=tuple(
                    RoadMetricResult(
                        request_id=request.request_id,
                        distance_km=request.geodesic_distance_km,
                        duration_minutes=request.geodesic_distance_km,
                    )
                    for request in requests
                ),
                external_request_count=1,
            )

    parameters = EnergyParameters(
        maximum_range_km=100,
        minimum_soc_percent=20,
        target_soc_percent=80,
        safety_factor=1,
        soc_step_percent=5,
    )
    graph = build_travel_graph(
        origin=(0, 0),
        destination=(0, 0.6),
        route=route,
        candidates=(candidate,),
        connector="CCS2",
        initial_usable_range_km=parameters.usable_range_km(60),
        post_charge_usable_range_km=parameters.usable_range_km(80),
        road_metric_provider=ExactRoadMetricProvider(),
    )
    result = optimize_itinerary(
        graph,
        current_soc_percent=60,
        parameters=parameters,
    )

    assert graph.stats.geodesic_pruned_pairs == 1
    assert result.feasible is True
    assert [stop.node_id for stop in result.itinerary.charging_stops] == [
        "station-tengah"
    ]
    assert result.itinerary.minimum_observed_soc_percent >= 20
