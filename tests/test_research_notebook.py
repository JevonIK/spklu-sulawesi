import json
import socket
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.build_research_snapshots import build_snapshots


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = (
    PROJECT_ROOT / "notebooks" / "analisis_sistem_spklu_sulawesi.ipynb"
)


def test_research_notebook_runs_all_code_cells_offline(monkeypatch):
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    assert notebook["nbformat"] == 4
    assert notebook["nbformat_minor"] >= 5
    assert any(cell["cell_type"] == "markdown" for cell in notebook["cells"])

    monkeypatch.chdir(PROJECT_ROOT)
    def reject_network(*args, **kwargs):
        raise AssertionError("Notebook penelitian tidak boleh mengakses jaringan.")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    namespace = {"__name__": "__main__"}
    code_cells = [
        cell for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]

    for cell in code_cells:
        source = "".join(cell["source"])
        exec(
            compile(source, f"notebook:{cell['id']}", "exec"),
            namespace,
        )

    validation = namespace["final_validation"]
    assert validation["mode"] == "offline"
    assert validation["google_api_requests_from_notebook"] == 0
    assert validation["dataset_sha256_valid"] is True
    assert validation["baseline_rows"] == 6
    assert validation["sensitivity_rows"] == 7
    assert validation["baseline_error_count"] == 0
    assert validation["sensitivity_error_count"] == 0
    assert validation["charging_time_included"] is False
    assert validation["analysis_application_version"] == "0.15.0"
    assert validation["baseline_source_application_version"] == "0.9.2"
    assert validation["sensitivity_source_application_version"] == "0.10.0"

    sample_svg = namespace["horizontal_bar_svg"](
        ["Uji"],
        [1],
        "Validasi SVG",
    )
    assert ET.fromstring(sample_svg).tag.endswith("svg")


def test_research_snapshots_are_deterministically_derived(tmp_path):
    baseline_source = (
        PROJECT_ROOT
        / "reports"
        / "generated"
        / "baseline-live-20260813-detailed.json"
    )
    sensitivity_source = (
        PROJECT_ROOT
        / "reports"
        / "generated"
        / "sensitivitas-live-20260813-rerun1.json"
    )
    if not baseline_source.is_file() or not sensitivity_source.is_file():
        return

    generated = build_snapshots(
        baseline_source,
        sensitivity_source,
        tmp_path,
    )

    for path in generated:
        expected = PROJECT_ROOT / "notebooks" / "data" / path.name
        assert path.read_bytes() == expected.read_bytes(), path.name
