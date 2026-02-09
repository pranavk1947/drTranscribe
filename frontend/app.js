import AudioRecorder from './audio-recorder.js';

let audioRecorder = null;
let websocket = null;
let isRecording = false;
let audioConfig = null; // Will be loaded from /api/config

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusEl = document.getElementById('status');

const patientNameInput = document.getElementById('patientName');
const patientAgeInput = document.getElementById('patientAge');
const patientGenderInput = document.getElementById('patientGender');

const sections = {
    chief_complaint: document.getElementById('chiefComplaint'),
    diagnosis: document.getElementById('diagnosis'),
    medicine: document.getElementById('medicine'),
    advice: document.getElementById('advice'),
    next_steps: document.getElementById('nextSteps')
};

startBtn.addEventListener('click', startRecording);
stopBtn.addEventListener('click', stopRecording);

// Load audio configuration from backend
async function loadAudioConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) {
            throw new Error(`Failed to load config: ${response.status}`);
        }
        audioConfig = await response.json();
        console.log('✅ Loaded audio config:', audioConfig);
        return audioConfig;
    } catch (error) {
        console.error('❌ Failed to load audio config:', error);
        // Fallback to defaults
        audioConfig = {
            audio: {
                chunk_duration_seconds: 5,
                sample_rate: 16000,
                channels: 1
            }
        };
        console.log('⚠️ Using default audio config:', audioConfig);
        return audioConfig;
    }
}

async function startRecording() {
    // Load audio config if not already loaded
    if (!audioConfig) {
        console.log('Loading audio config...');
        await loadAudioConfig();
    }

    // Validate patient information
    const patientName = patientNameInput.value.trim();
    const patientAge = parseInt(patientAgeInput.value);
    const patientGender = patientGenderInput.value.trim();

    if (!patientName || !patientAge || !patientGender) {
        alert('Please fill in all patient information fields');
        return;
    }

    if (patientAge < 0 || patientAge > 150) {
        alert('Please enter a valid age');
        return;
    }

    try {
        // Request microphone permission
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // Connect WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        websocket = new WebSocket(wsUrl);
        
        websocket.onopen = () => {
            console.log('WebSocket connected');
            
            // Send start session message
            const startMessage = {
                type: 'start_session',
                patient: {
                    name: patientName,
                    age: patientAge,
                    gender: patientGender
                }
            };
            websocket.send(JSON.stringify(startMessage));

            // Create AudioRecorder instead of MediaRecorder
            audioRecorder = new AudioRecorder(
                stream,
                audioConfig.audio,
                (wavBlob) => {
                    // Callback when WAV chunk is ready
                    if (websocket && websocket.readyState === WebSocket.OPEN) {
                        sendAudioChunk(wavBlob);
                    }
                }
            );

            // Start recording
            audioRecorder.start().then(() => {
                isRecording = true;
                updateUI();
                console.log('✅ AudioRecorder started with AudioWorklet');
            }).catch((error) => {
                console.error('Failed to start AudioRecorder:', error);
                alert('Failed to start recording: ' + error.message);
                stopRecording();
            });
        };
        
        websocket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        };
        
        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            alert('Connection error. Please try again.');
            stopRecording();
        };
        
        websocket.onclose = () => {
            console.log('WebSocket closed');
            if (isRecording) {
                stopRecording();
            }
        };
        
    } catch (error) {
        console.error('Failed to start recording:', error);
        alert('Failed to access microphone. Please check permissions.');
    }
}

function stopRecording() {
    if (audioRecorder && audioRecorder.isRecording()) {
        audioRecorder.stop();
    }

    if (websocket && websocket.readyState === WebSocket.OPEN) {
        const stopMessage = { type: 'stop_session' };
        websocket.send(JSON.stringify(stopMessage));
        websocket.close();
    }

    isRecording = false;
    updateUI();
}

function sendAudioChunk(blob) {
    console.log(`📤 Sending audio chunk: ${blob.size} bytes, type: ${blob.type}`);
    const reader = new FileReader();
    reader.onloadend = () => {
        const base64Data = reader.result.split(',')[1];
        const message = {
            type: 'audio_chunk',
            audio_data: base64Data
        };
        websocket.send(JSON.stringify(message));
        console.log(`✅ Sent audio chunk: ${blob.size} bytes (${base64Data.length} chars base64)`);
    };
    reader.onerror = (error) => {
        console.error('❌ FileReader error:', error);
    };
    reader.readAsDataURL(blob);
}

function handleWebSocketMessage(message) {
    console.log('Received message:', message.type);
    
    if (message.type === 'extraction_update') {
        updateExtractionSections(message.extraction);
    } else if (message.type === 'error') {
        console.error('Server error:', message.message);
        alert(`Error: ${message.message}`);
    }
}

function updateExtractionSections(extraction) {
    for (const [key, element] of Object.entries(sections)) {
        const value = extraction[key];
        if (value && value.trim()) {
            element.textContent = value;
            element.classList.remove('empty');
        } else {
            element.textContent = 'No data yet...';
            element.classList.add('empty');
        }
    }
}

function updateUI() {
    if (isRecording) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        statusEl.textContent = 'Recording...';
        statusEl.classList.add('recording');
        
        patientNameInput.disabled = true;
        patientAgeInput.disabled = true;
        patientGenderInput.disabled = true;
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        statusEl.textContent = 'Ready';
        statusEl.classList.remove('recording');
        
        patientNameInput.disabled = false;
        patientAgeInput.disabled = false;
        patientGenderInput.disabled = false;
    }
}

// Initialize UI and load config
updateUI();
loadAudioConfig();
