import pytest

from app.services.energy import EnergyParameters, SocDiscretizer


def test_usable_range_matches_proposal_formula():
    parameters = EnergyParameters(
        maximum_range_km=300,
        minimum_soc_percent=20,
        target_soc_percent=80,
        safety_factor=0.9,
        soc_step_percent=5,
    )

    assert parameters.effective_full_range_km == pytest.approx(270)
    assert parameters.usable_range_km(60) == pytest.approx(108)
    assert parameters.usable_range_km(80) == pytest.approx(162)


def test_distance_consumption_and_arrival_soc_are_consistent():
    parameters = EnergyParameters(250, 20, 80, safety_factor=1, soc_step_percent=5)

    assert parameters.consumption_percent(100) == pytest.approx(40)
    assert parameters.arrival_soc_percent(60, 100) == pytest.approx(20)


def test_soc_discretization_rounds_down_conservatively():
    parameters = EnergyParameters(300, 20, 83, safety_factor=0.9, soc_step_percent=10)
    discretizer = SocDiscretizer(parameters)

    assert discretizer.quantize_down(79) == 70
    assert discretizer.target_level == 83
    assert discretizer.charging_levels(70) == (80, 83)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"maximum_range_km": 0}, "Jangkauan maksimum"),
        ({"minimum_soc_percent": 100}, "SOC minimum"),
        ({"target_soc_percent": 20}, "Target SOC"),
        ({"safety_factor": 1.1}, "Safety factor"),
        ({"soc_step_percent": 0}, "Interval SOC"),
    ],
)
def test_invalid_energy_parameters_are_rejected(kwargs, message):
    values = {
        "maximum_range_km": 300,
        "minimum_soc_percent": 20,
        "target_soc_percent": 80,
        "safety_factor": 0.9,
        "soc_step_percent": 5,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        EnergyParameters(**values)


def test_current_soc_below_minimum_is_rejected():
    parameters = EnergyParameters(300, 20, 80)

    with pytest.raises(ValueError, match="SOC saat ini"):
        parameters.validate_current_soc(19)

