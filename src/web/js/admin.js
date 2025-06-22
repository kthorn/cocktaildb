import { api } from './api.js';
import { isAuthenticated } from './auth.js';

document.addEventListener('DOMContentLoaded', () => {
    setupAdminPage();
});

function setupAdminPage() {
    const downloadBtn = document.getElementById('download-db-btn');
    
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadDatabase);
    }
    
    // Check authentication and show/hide admin tools accordingly
    updateUIBasedOnAuth();
}

function updateUIBasedOnAuth() {
    const adminTools = document.querySelector('.admin-tools');
    
    if (!isAuthenticated()) {
        adminTools.innerHTML = `
            <div class="card-container">
                <p>Please log in to access admin tools.</p>
            </div>
        `;
        return;
    }
    
    // User is authenticated, show admin tools
    adminTools.style.display = 'block';
}

async function downloadDatabase() {
    const downloadBtn = document.getElementById('download-db-btn');
    const originalText = downloadBtn.textContent;
    
    try {
        // Update button to show loading state
        downloadBtn.textContent = 'Downloading...';
        downloadBtn.disabled = true;
        
        // Make API call to download database
        const response = await fetch(`${api.baseUrl}/admin/database/download`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('id_token')}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Download failed: ${response.status} ${response.statusText}`);
        }
        
        // Get the blob from response
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Generate filename with timestamp
        const now = new Date();
        const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.download = `cocktaildb-backup-${timestamp}.db`;
        
        // Trigger download
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        // Clean up the blob URL
        window.URL.revokeObjectURL(url);
        
        // Show success message
        showMessage('Database downloaded successfully!', 'success');
        
    } catch (error) {
        console.error('Error downloading database:', error);
        showMessage(`Error downloading database: ${error.message}`, 'error');
    } finally {
        // Restore button state
        downloadBtn.textContent = originalText;
        downloadBtn.disabled = false;
    }
}

function showMessage(message, type = 'info') {
    // Create message element using existing notification styles
    const messageDiv = document.createElement('div');
    messageDiv.className = `notification ${type}`;
    messageDiv.textContent = message;
    
    // Insert at top of main section
    const mainSection = document.querySelector('main section');
    mainSection.insertBefore(messageDiv, mainSection.firstChild);
    
    // Remove message after 5 seconds
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 5000);
}