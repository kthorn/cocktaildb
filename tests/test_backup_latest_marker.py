import os
import subprocess


def test_backup_script_dry_run_mentions_latest_markers():
    env = os.environ.copy()
    env['BACKUP_BUCKET'] = 'example-bucket'
    env['BACKUP_DIR'] = '/tmp/cocktaildb-backups-test'
    result = subprocess.run(
        ['bash', 'infrastructure/scripts/backup-postgres.sh', '--dry-run'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert 'latest.txt' in result.stdout
    assert 'latest.json' in result.stdout
