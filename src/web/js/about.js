// About page functionality
const BACKUP_BUCKET = 'cocktaildbbackups-732940910135-prod';
const MARKER_URL = `https://${BACKUP_BUCKET}.s3.amazonaws.com/latest.txt`;

async function setLatestBackupLink() {
    const link = document.getElementById('backup-download-link');
    const status = document.getElementById('backup-download-status');
    if (!link || !status) {
        return;
    }

    try {
        const response = await fetch(MARKER_URL, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const filename = (await response.text()).trim();
        if (!filename) {
            throw new Error('Empty latest marker');
        }

        link.href = `https://${BACKUP_BUCKET}.s3.amazonaws.com/${filename}`;
        link.setAttribute('download', filename);
        link.removeAttribute('aria-disabled');
        status.textContent = '';
    } catch (error) {
        console.error('Failed to load latest backup link:', error);
        link.href = '#';
        link.setAttribute('aria-disabled', 'true');
        status.textContent = 'Backup download unavailable.';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    setLatestBackupLink();
});
