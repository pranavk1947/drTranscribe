/**
 * Permissions helper page — triggers the microphone permission prompt.
 *
 * The offscreen document cannot show a permission prompt itself, so when
 * getUserMedia fails there with NotAllowedError the background opens this
 * page. Granting mic access here grants it for the whole extension origin,
 * which the offscreen document then inherits.
 */
const grantBtn = document.getElementById('grant-btn');
const resultOk = document.getElementById('result-ok');
const resultFail = document.getElementById('result-fail');

grantBtn.addEventListener('click', async () => {
    resultOk.classList.remove('ok');
    resultFail.classList.remove('fail');
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Permission granted — we don't need the stream itself.
        stream.getTracks().forEach(track => track.stop());
        resultOk.classList.add('ok');
        grantBtn.disabled = true;
        grantBtn.textContent = 'Access granted';
    } catch (err) {
        console.warn('[Permissions] getUserMedia failed:', err.name, err.message);
        resultFail.classList.add('fail');
    }
});
