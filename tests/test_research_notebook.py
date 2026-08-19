import json
from pathlib import Path


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
