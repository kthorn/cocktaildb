from pathlib import Path


def test_debounce_script_and_units_exist():
    assert Path("infrastructure/scripts/analytics-debounce-check.sh").exists()
    assert Path("infrastructure/systemd/cocktaildb-analytics-debounce.service").exists()
    assert Path("infrastructure/systemd/cocktaildb-analytics-debounce.timer").exists()
