const DEFAULT_SERVER_URL = 'http://localhost:8000';

const serverUrlInput = document.getElementById('server-url');
const doctorNameInput = document.getElementById('doctor-name');
const clinicNameInput = document.getElementById('clinic-name');
const saveBtn = document.getElementById('save-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const sessionStatus = document.getElementById('session-status');
// Load saved settings
chrome.storage.local.get(['serverUrl', 'doctorName', 'clinicName'], (result) => {
    serverUrlInput.value = result.serverUrl || DEFAULT_SERVER_URL;
    doctorNameInput.value = result.doctorName || '';
    clinicNameInput.value = result.clinicName || '';
    checkHealth();
});

// Check session status
chrome.runtime.sendMessage({ type: 'get-status' }, (response) => {
    if (response && response.isSessionActive) {
        sessionStatus.textContent = 'Session active';
        sessionStatus.style.color = '#a6e3a1';
    }
});

// Save all settings
saveBtn.addEventListener('click', () => {
    const url = serverUrlInput.value.trim().replace(/\/+$/, ''); // Remove trailing slash
    if (!url) {
        serverUrlInput.value = DEFAULT_SERVER_URL;
        return;
    }
    chrome.storage.local.set({
        serverUrl: url,
        doctorName: doctorNameInput.value.trim(),
        clinicName: clinicNameInput.value.trim()
    }, () => {
        saveBtn.textContent = 'Saved!';
        setTimeout(() => { saveBtn.textContent = 'Save'; }, 1500);
        checkHealth();
    });
});

// Health check
function checkHealth() {
    const url = serverUrlInput.value.trim().replace(/\/+$/, '');
    setHealthStatus('checking', 'Checking...');

    chrome.runtime.sendMessage({
        type: 'health-check',
        serverUrl: url
    }, (response) => {
        if (chrome.runtime.lastError) {
            setHealthStatus('error', 'Extension error');
            return;
        }
        if (response && response.ok) {
            setHealthStatus('ok', 'Connected');
        } else {
            setHealthStatus('error', response ? response.error : 'Unreachable');
        }
    });
}

function setHealthStatus(state, text) {
    statusText.textContent = text;
    statusDot.className = 'popup-status-dot';
    statusDot.classList.add('popup-status-' + state);
}
