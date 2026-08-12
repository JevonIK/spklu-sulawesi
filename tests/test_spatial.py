import pytest

from app.config import BASE_DIR
from app.services.dataset import StationNode, StationUnit, load_station_catalog
from app.services.spatial import (
    RouteGeometry,
    StationSpatialIndex,
    find_corridor_candidates,
    find_reachable_forward_candidates,
    haversine_distance_km,
)


def make_node(name, latitude, longitude, connectors=("CCS2",)):
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
    return StationNode(
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


def test_haversine_distance_for_one_degree_latitude():
    assert haversine_distance_km((0, 0), (1, 0)) == pytest.approx(
        111.195, rel=1e-4
    )


def test_route_sampling_preserves_endpoints_and_maximum_step():
    route = RouteGeometry(((0, 0), (0, 1)))
    samples = route.sample(25)

    assert samples[0] == (0.0, 0.0)
    assert samples[-1] == (0.0, 1.0)
    for first, second in zip(samples, samples[1:]):
        assert haversine_distance_km(first, second) <= 25.001


def test_route_projection_returns_distance_and_forward_progress():
    route = RouteGeometry(((0, 0), (0, 1)))
    projection = route.project((0.1, 0.25))

    assert projection.distance_to_route_km == pytest.approx(11.1195, rel=1e-3)
    assert projection.progress_km == pytest.approx(
        route.total_distance_km * 0.25, rel=1e-3
    )
    assert projection.progress_ratio == pytest.approx(0.25, rel=1e-3)


def test_ball_tree_radius_query_returns_all_nodes_inside_radius():
    near = make_node("Dekat", 0, 0.25)
    edge = make_node("Dalam Radius", 0, 0.5)
    far = make_node("Jauh", 0, 1.0)
    index = StationSpatialIndex((near, edge, far))

    matches = index.query_radius((0, 0), 60, connector="ccs 2")

    assert [match.node.name for match in matches] == ["Dekat", "Dalam Radius"]
    assert matches[-1].distance_km == pytest.approx(55.598, rel=1e-3)


def test_ball_tree_connector_filter_excludes_incompatible_nodes():
    ccs = make_node("CCS", 0, 0.1, connectors=("CCS2",))
    type_two = make_node("Type 2", 0, 0.2, connectors=("AC TYPE 2",))
    index = StationSpatialIndex((ccs, type_two))

    matches = index.query_radius((0, 0), 50, connector="AC Type-2")

    assert [match.node.name for match in matches] == ["Type 2"]


def test_corridor_search_filters_distance_and_sorts_by_progress():
    early = make_node("Awal", 0.02, 0.2)
    late = make_node("Akhir", -0.01, 0.8)
    outside = make_node("Di Luar Koridor", 0.2, 0.5)
    index = StationSpatialIndex((late, outside, early))
    route = RouteGeometry(((0, 0), (0, 1)))

    candidates = find_corridor_candidates(
        index,
        route,
        corridor_radius_km=5,
        connector="CCS2",
        sample_step_km=4,
    )

    assert [candidate.node.name for candidate in candidates] == ["Awal", "Akhir"]
    assert candidates[0].distance_to_route_km == pytest.approx(2.224, rel=1e-3)
    assert candidates[1].route_progress_km > candidates[0].route_progress_km


def test_reachable_search_applies_usable_range_and_forward_progress():
    current = make_node("Posisi Saat Ini", 0, 0)
    reachable = make_node("Terjangkau", 0.01, 0.5)
    too_far = make_node("Terlalu Jauh", 0, 0.9)
    index = StationSpatialIndex((current, reachable, too_far))
    route = RouteGeometry(((0, 0), (0, 1)))

    candidates = find_reachable_forward_candidates(
        index,
        route,
        origin=(0, 0),
        usable_range_km=70,
        corridor_radius_km=5,
        connector="CCS2",
    )

    assert [candidate.node.name for candidate in candidates] == ["Terjangkau"]
    assert candidates[0].straight_line_distance_km == pytest.approx(55.609, rel=1e-3)


def test_real_catalog_indexes_logical_nodes_not_duplicate_units():
    catalog = load_station_catalog(BASE_DIR / "dataset_spklu_sulawesi.csv")
    index = StationSpatialIndex(catalog.nodes)
    bolmut = catalog.multi_unit_nodes[0]

    matches = index.query_radius(
        (bolmut.latitude, bolmut.longitude),
        radius_km=0.05,
        connector="AC TYPE 2",
    )

    assert len(index.nodes) == 149
    assert [match.node.node_id for match in matches] == [bolmut.node_id]


def test_ball_tree_real_data_matches_brute_force_radius_result():
    catalog = load_station_catalog(BASE_DIR / "dataset_spklu_sulawesi.csv")
    index = StationSpatialIndex(catalog.nodes)
    center_node = next(node for node in catalog.nodes if node.city == "Makassar")
    center = (center_node.latitude, center_node.longitude)
    radius_km = 150

    ball_tree_ids = {
        match.node.node_id
        for match in index.query_radius(center, radius_km, connector="CCS2")
    }
    brute_force_ids = {
        node.node_id
        for node in catalog.nodes
        if "CCS2" in node.connectors
        and haversine_distance_km(center, (node.latitude, node.longitude))
        <= radius_km
    }

    assert ball_tree_ids == brute_force_ids


@pytest.mark.parametrize(
    "action, message",
    [
        (lambda: RouteGeometry(((0, 0),)), "sedikitnya dua titik"),
        (
            lambda: StationSpatialIndex((make_node("Uji", 0, 0),)).query_radius(
                (0, 0), 0
            ),
            "lebih besar dari nol",
        ),
    ],
)
def test_invalid_spatial_parameters_are_rejected(action, message):
    with pytest.raises(ValueError, match=message):
        action()
