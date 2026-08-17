import pytest

from app.services.dataset import StationNode, StationUnit
from app.services.graph import (
    DESTINATION_NODE_ID,
    ORIGIN_NODE_ID,
    build_travel_graph,
)
from app.services.road_metrics import (
    RoadMetricBatch,
    RoadMetricResult,
)
from app.services.spatial import (
    CorridorCandidate,
    RouteGeometry,
    haversine_distance_km,
)


def make_candidate(name, longitude, connectors=("CCS2",), latitude=0.0):
    unit = StationUnit(
        source_row=2,
        province="Sulawesi Selatan",
        city="Kota Uji",
        name=name,
        address="Alamat Uji",
        latitude=latitude,
        longitude=longitude,
        maps_url="https://maps.app.goo.gl/uji",
        connectors=tuple(connectors),
    )
    node_id = name.lower().replace(" ", "-")
    node = StationNode(
        node_id=node_id,
        name=name,
        province=unit.province,
        city=unit.city,
        address=unit.address,
        latitude=latitude,
        longitude=longitude,
        maps_url=unit.maps_url,
        connectors=tuple(connectors),
        units=(unit,),
    )
    progress = haversine_distance_km((0, 0), (0, longitude))
    return CorridorCandidate(
        node=node,
        distance_to_route_km=haversine_distance_km(
            (latitude, longitude), (0, longitude)
        ),
        route_progress_km=progress,
        route_progress_ratio=longitude,
    )


class RecordingRoadMetricProvider:
    def __init__(self, *, factor=1.05, overrides=None, omitted=None):
        self.factor = factor
        self.overrides = overrides or {}
        self.omitted = set(omitted or ())
        self.requests = ()

    def fetch(self, requests):
        self.requests = requests
        results = []
        for request in requests:
            if request.request_id in self.omitted:
                continue
            distance = self.overrides.get(
                request.request_id,
                request.geodesic_distance_km * self.factor,
            )
            results.append(
                RoadMetricResult(
                    request_id=request.request_id,
                    distance_km=distance,
                    duration_minutes=distance,
                )
            )
        return RoadMetricBatch(
            results=tuple(results),
            external_request_count=1 if requests else 0,
        )


def build_simple_graph(provider, **overrides):
    route = RouteGeometry(((0, 0), (0, 1)))
    parameters = {
        "origin": (0, 0),
        "destination": (0, 1),
        "route": route,
        "candidates": (
            make_candidate("Station A", 0.3),
            make_candidate("Station B", 0.6),
        ),
        "connector": "CCS2",
        "initial_usable_range_km": 50,
        "post_charge_usable_range_km": 50,
        "road_metric_provider": provider,
    }
    parameters.update(overrides)
    return build_travel_graph(**parameters)


def test_graph_prunes_geodesic_pairs_before_provider_and_builds_path():
    provider = RecordingRoadMetricProvider()
    graph = build_simple_graph(provider)

    assert [edge.source_id + "->" + edge.target_id for edge in graph.edges] == [
        "origin->station-a",
        "station-a->station-b",
        "station-b->destination",
    ]
    assert graph.stats.possible_forward_pairs == 6
    assert graph.stats.geodesic_pruned_pairs == 3
    assert graph.stats.road_metric_pairs == 3
    assert len(provider.requests) == 3
    assert graph.stats.accepted_edges == 3
    assert graph.stats.external_request_count == 1
    assert graph.has_origin_to_destination_path() is True


def test_incompatible_station_is_excluded_from_graph_nodes():
    provider = RecordingRoadMetricProvider(factor=1.0)
    graph = build_travel_graph(
        origin=(0, 0),
        destination=(0, 1),
        route=((0, 0), (0, 1)),
        candidates=(
            make_candidate("Compatible", 0.3, connectors=("CCS2",)),
            make_candidate("Incompatible", 0.4, connectors=("AC TYPE 2",)),
        ),
        connector="CCS2",
        initial_usable_range_km=200,
        post_charge_usable_range_km=200,
        road_metric_provider=provider,
    )

    assert graph.stats.input_candidate_nodes == 2
    assert graph.stats.compatible_station_nodes == 1
    assert {node.name for node in graph.nodes} == {
        "Lokasi awal",
        "Compatible",
        "Lokasi tujuan",
    }


def test_graph_accepts_station_matching_any_selected_connector():
    provider = RecordingRoadMetricProvider(factor=1.0)
    graph = build_travel_graph(
        origin=(0, 0),
        destination=(0, 1),
        route=((0, 0), (0, 1)),
        candidates=(
            make_candidate("Type 2", 0.3, connectors=("AC TYPE 2",)),
            make_candidate("CHAdeMO", 0.4, connectors=("CHADEMO",)),
            make_candidate("GB/T", 0.5, connectors=("GB/T",)),
        ),
        connector=("AC TYPE 2", "CHADEMO"),
        initial_usable_range_km=200,
        post_charge_usable_range_km=200,
        road_metric_provider=provider,
    )

    assert graph.stats.compatible_station_nodes == 2
    assert {node.name for node in graph.nodes if node.kind == "station"} == {
        "Type 2",
        "CHAdeMO",
    }


def test_edge_is_removed_when_road_distance_exceeds_usable_range():
    provider = RecordingRoadMetricProvider(
        overrides={"station-b->destination": 60}
    )
    graph = build_simple_graph(provider)

    assert graph.stats.road_distance_pruned_pairs == 1
    assert graph.stats.accepted_edges == 2
    assert graph.has_origin_to_destination_path() is False


def test_unavailable_road_result_is_recorded_and_removed():
    provider = RecordingRoadMetricProvider(
        omitted={"station-b->destination"}
    )
    graph = build_simple_graph(provider)

    assert graph.stats.unavailable_road_pairs == 1
    assert graph.stats.accepted_edges == 2
    assert DESTINATION_NODE_ID not in graph.reachable_node_ids()


def test_optional_detour_limit_prunes_edges():
    provider = RecordingRoadMetricProvider(factor=1.2)
    graph = build_simple_graph(provider, max_edge_detour_km=3)

    assert graph.stats.road_distance_pruned_pairs == 1
    assert graph.stats.detour_pruned_pairs == 2
    assert graph.stats.accepted_edges == 0


def test_provider_result_shorter_than_geodesic_is_rejected():
    provider = RecordingRoadMetricProvider(overrides={"origin->station-a": 20})

    with pytest.raises(ValueError, match="lebih pendek daripada jarak geodesik"):
        build_simple_graph(provider)


def test_graph_does_not_call_provider_when_every_pair_is_pruned():
    class FailingProvider:
        def fetch(self, requests):
            raise AssertionError("Provider tidak boleh dipanggil")

    graph = build_simple_graph(
        FailingProvider(),
        initial_usable_range_km=1,
        post_charge_usable_range_km=1,
    )

    assert graph.edges == ()
    assert graph.stats.road_metric_pairs == 0
    assert graph.stats.external_request_count == 0


def test_graph_accessors_return_expected_nodes_and_edges():
    graph = build_simple_graph(RecordingRoadMetricProvider())

    assert graph.node(ORIGIN_NODE_ID).kind == "origin"
    assert len(graph.outgoing_edges("station-a")) == 1
    assert graph.to_dict()["has_origin_to_destination_path"] is True


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"initial_usable_range_km": 0}, "Initial usable range"),
        ({"post_charge_usable_range_km": -1}, "Post-charge usable range"),
        ({"max_edge_detour_km": 0}, "Batas detour edge"),
    ],
)
def test_invalid_graph_ranges_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_simple_graph(RecordingRoadMetricProvider(), **kwargs)


def test_invalid_road_metric_is_rejected():
    with pytest.raises(ValueError, match="Jarak jalan"):
        RoadMetricResult(request_id="uji", distance_km=-1)
