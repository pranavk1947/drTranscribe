/**
 * Permissions helper page — triggers the microphone permission prompt once.
 *
 * The offscreen document cannot show a permission prompt itself, so mic access
 * must be granted from a visible page. Granting it here grants it for the whole
 * extension origin (chrome-extension://<id>), which the offscreen document then
 * inherits — permanently. This page therefore needs to be used only once.
 *
 * Flow: on load we check the current permission state. If already granted, we
 * say so and close shortly. If not, we auto-attempt getUserMedia (which shows
 * Chrome's prompt); the "Allow microphone access" button is the manual fallback
 * if the browser requires an explicit click.
 */
const grantBtn = document.getElementById('grant-btn');
const resultOk = document.getElementById('result-ok');
const resultFail = document.getElementById('result-fail');

async function requestMic() {
    resultOk.classList.remove('ok');
    resultFail.classList.remove('fail');
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(track => track.stop()); // we only needed the grant
        // Ground-truth signal: a real getUserMedia just succeeded. The popup
        // can't rely on navigator.permissions.query (it keeps returning 'prompt'
        // for extension origins even after a grant), so we persist this flag and
        // the popup trusts it. Background clears it again if capture ever fails.
        try { await chrome.storage.local.set({ micGranted: true }); } catch { /* storage unavailable */ }
        resultOk.classList.add('ok');
        grantBtn.disabled = true;
        grantBtn.textContent = 'Access granted';
        // The grant persists for the extension origin — this tab is done.
        setTimeout(() => { window.close(); }, 1500);
        return true;
    } catch (err) {
        console.warn('[Permissions] getUserMedia failed:', err.name, err.message);
        resultFail.classList.add('fail');
        return false;
    }
}

grantBtn.addEventListener('click', requestMic);

// On load: if already granted, confirm and close; otherwise auto-attempt the
// prompt (button remains as a fallback if the auto-attempt is suppressed).
(async function init() {
    try {
        const status = await navigator.permissions.query({ name: 'microphone' });
        if (status.state === 'granted') {
            try { await chrome.storage.local.set({ micGranted: true }); } catch { /* storage unavailable */ }
            resultOk.classList.add('ok');
            grantBtn.disabled = true;
            grantBtn.textContent = 'Access granted';
            setTimeout(() => { window.close(); }, 1200);
            return;
        }
    } catch { /* Permissions API unavailable — fall through to a request */ }
    requestMic(); // auto-prompt; harmless if the browser needs the manual click
})();
