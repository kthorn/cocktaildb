import subprocess
from pathlib import Path


def test_run_migrations_help():
    script = Path("infrastructure/scripts/run-migrations.sh")
    assert script.exists()
    result = subprocess.run(["bash", str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Usage" in result.stdout
