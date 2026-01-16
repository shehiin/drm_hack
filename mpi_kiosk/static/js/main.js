/**
 * MPI Robotic Inspection System - Frontend Logic
 * Handles camera feed, inspection triggers, and UI updates
 */

// =============================================================================
// STATE
// =============================================================================

const state = {
    selectedObject: null,
    isInspecting: false,
    isFrozen: false,
    lastInspection: null,
    robotStatus: null,
    cameraConnected: false
};

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const elements = {
    // Status
    systemStatus: document.getElementById('systemStatus'),
    
    // Component input
    componentInput: document.getElementById('componentInput'),
    btnVoice: document.getElementById('btnVoice'),
    selectedComponent: document.getElementById('selectedComponent'),
    
    // Camera
    cameraInput: document.getElementById('cameraInput'),
    btnCameraConnect: document.getElementById('btnCameraConnect'),
    cameraStatus: document.getElementById('cameraStatus'),
    videoFeed: document.getElementById('videoFeed'),
    inspectionImage: document.getElementById('inspectionImage'),
    cameraOverlay: document.getElementById('cameraOverlay'),
    feedStatus: document.getElementById('feedStatus'),
    
    // Actions
    btnInspect: document.getElementById('btnInspect'),
    btnNewInspection: document.getElementById('btnNewInspection'),
    
    // Robot
    robotState: document.getElementById('robotState'),
    robotObject: document.getElementById('robotObject'),
    
    // Results
    resultsBox: document.getElementById('resultsBox'),
    
    // Log
    logBox: document.getElementById('logBox'),
    btnClearLog: document.getElementById('btnClearLog'),
    
    // Footer
    footerCamera: document.getElementById('footerCamera'),
    footerApi: document.getElementById('footerApi')
};

// =============================================================================
// API CALLS
// =============================================================================

async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(endpoint, options);
        return await response.json();
    } catch (error) {
        console.error(`API error (${endpoint}):`, error);
        return { success: false, error: error.message };
    }
}

// =============================================================================
// UI UPDATES
// =============================================================================

function updateSystemStatus(status, text) {
    elements.systemStatus.className = `status-indicator ${status}`;
    elements.systemStatus.querySelector('.status-text').textContent = text;
}

function updateComponentSelection(objectName) {
    state.selectedObject = objectName;
    
    if (objectName) {
        elements.selectedComponent.textContent = objectName.toUpperCase();
        elements.selectedComponent.classList.add('active');
        elements.componentInput.value = objectName;
    } else {
        elements.selectedComponent.textContent = '--';
        elements.selectedComponent.classList.remove('active');
        elements.componentInput.value = '';
    }
}

// Valid components for matching
const VALID_COMPONENTS = ['knuckle', 'cube', 'gear'];

function parseComponentFromText(text) {
    const lower = text.toLowerCase().trim();
    for (const comp of VALID_COMPONENTS) {
        if (lower.includes(comp)) {
            return comp;
        }
    }
    return null;
}

// Voice recognition setup
let recognition = null;
let isListening = false;

function setupVoiceRecognition() {
    console.log('Setting up voice recognition...');
    
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.error('Speech recognition NOT supported in this browser');
        elements.btnVoice.disabled = true;
        elements.btnVoice.title = 'Voice not supported in this browser';
        elements.btnVoice.querySelector('.voice-icon').textContent = 'N/A';
        return;
    }
    
    console.log('Speech recognition IS supported');
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
        console.log('Voice recognition started');
        isListening = true;
        elements.btnVoice.classList.add('listening');
        elements.btnVoice.querySelector('.voice-icon').textContent = 'REC';
    };
    
    recognition.onend = () => {
        console.log('Voice recognition ended');
        isListening = false;
        elements.btnVoice.classList.remove('listening');
        elements.btnVoice.querySelector('.voice-icon').textContent = 'MIC';
    };
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        console.log('Voice input:', transcript);
        elements.componentInput.value = transcript;
        
        const component = parseComponentFromText(transcript);
        if (component) {
            selectComponent(component);
        }
    };
    
    recognition.onerror = (event) => {
        console.error('Voice recognition error:', event.error, event);
        isListening = false;
        elements.btnVoice.classList.remove('listening');
        elements.btnVoice.querySelector('.voice-icon').textContent = 'ERR';
        
        // Show specific error
        if (event.error === 'not-allowed') {
            alert('Microphone permission denied. Please allow microphone access in browser settings.');
        } else if (event.error === 'no-speech') {
            elements.btnVoice.querySelector('.voice-icon').textContent = 'MIC';
        } else if (event.error === 'network') {
            alert('Network error - Speech recognition requires internet connection');
        }
    };
    
    console.log('Voice recognition setup complete');
}

function toggleVoice() {
    console.log('Toggle voice called, recognition:', recognition, 'isListening:', isListening);
    
    if (!recognition) {
        console.error('Recognition not initialized');
        alert('Voice recognition not available');
        return;
    }
    
    if (isListening) {
        recognition.stop();
    } else {
        try {
            recognition.start();
            console.log('Recognition start called');
        } catch (e) {
            console.error('Error starting recognition:', e);
            alert('Error starting voice: ' + e.message);
        }
    }
}

function updateRobotStatus(status) {
    state.robotStatus = status;
    
    // Update state display
    const stateText = status.state_display || status.state || 'UNKNOWN';
    elements.robotState.textContent = stateText.toUpperCase();
    elements.robotState.className = 'robot-state-value';
    
    if (status.state === 'idle' || status.ready_for_inspection) {
        elements.robotState.classList.add('ready');
    } else if (status.state === 'error') {
        elements.robotState.classList.add('error');
    } else {
        elements.robotState.classList.add('busy');
    }
    
    // Update object display
    elements.robotObject.textContent = status.current_object ? 
        status.current_object.toUpperCase() : '--';
}

function updateCameraStatus(connected, deviceId) {
    state.cameraConnected = connected;
    elements.cameraStatus.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
    elements.footerCamera.textContent = `CAM: ${connected ? deviceId : 'NONE'}`;
}

function showLiveFeed() {
    elements.videoFeed.classList.remove('hidden');
    elements.inspectionImage.classList.add('hidden');
    elements.feedStatus.textContent = 'LIVE';
    elements.feedStatus.classList.remove('frozen');
    state.isFrozen = false;
    
    // Refresh video feed
    elements.videoFeed.src = '/video_feed?' + Date.now();
}

function showFrozenFrame(imageBase64) {
    elements.videoFeed.classList.add('hidden');
    elements.inspectionImage.src = 'data:image/jpeg;base64,' + imageBase64;
    elements.inspectionImage.classList.remove('hidden');
    elements.feedStatus.textContent = 'FROZEN';
    elements.feedStatus.classList.add('frozen');
    state.isFrozen = true;
}

function showAnalyzing(show) {
    if (show) {
        elements.cameraOverlay.classList.remove('hidden');
    } else {
        elements.cameraOverlay.classList.add('hidden');
    }
    state.isInspecting = show;
    elements.btnInspect.disabled = show;
}

function updateResults(data) {
    if (!data || !data.summary) {
        elements.resultsBox.innerHTML = `
            <div class="results-placeholder">
                <span>No inspection performed</span>
                <span class="results-hint">Select a component and click INSPECT</span>
            </div>
        `;
        return;
    }
    
    const summary = data.summary;
    const hasDefects = summary.defects > 0;
    const statusClass = hasDefects ? 'fail' : 'pass';
    const statusText = hasDefects ? 'DEFECTS DETECTED' : 'INSPECTION PASSED';
    
    let objectsHtml = '';
    if (summary.objects && summary.objects.length > 0) {
        objectsHtml = summary.objects.map(obj => {
            const objClass = obj.has_defect ? 'defect' : 'ok';
            const statusText = obj.has_defect ? 
                (obj.name.toLowerCase() === 'gear' ? 'MISSING TEETH' : 'CRACK DETECTED') :
                (obj.name.toLowerCase() === 'gear' ? 'TEETH OK' : 'NO CRACK');
            
            return `
                <div class="result-object ${objClass}">
                    <div class="result-object-name">${obj.name.toUpperCase()}</div>
                    <div class="result-object-status">${statusText} (${obj.confidence})</div>
                    ${obj.description ? `<div class="result-object-desc">${obj.description}</div>` : ''}
                </div>
            `;
        }).join('');
    } else {
        objectsHtml = '<div class="result-object">No objects detected</div>';
    }
    
    elements.resultsBox.innerHTML = `
        <div class="result-summary ${statusClass}">
            <div class="result-status ${statusClass}">${statusText}</div>
            <div class="result-stats">
                <span>Objects: ${summary.total}</span>
                <span>Defects: ${summary.defects}</span>
            </div>
        </div>
        <div class="result-objects">
            ${objectsHtml}
        </div>
    `;
}

function addLogEntry(entry) {
    const levelClass = `log-${entry.level || 'info'}`;
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${levelClass}`;
    logEntry.innerHTML = `
        <span class="log-time">[${entry.timestamp}]</span>
        <span class="log-message">${entry.message}</span>
    `;
    elements.logBox.appendChild(logEntry);
    elements.logBox.scrollTop = elements.logBox.scrollHeight;
}

function clearLog() {
    elements.logBox.innerHTML = '';
}

// =============================================================================
// ACTIONS
// =============================================================================

async function selectComponent(objectName) {
    updateComponentSelection(objectName);
    await apiCall('/api/select', 'POST', { object: objectName });
}

async function runInspection() {
    if (state.isInspecting) return;
    
    showAnalyzing(true);
    
    const result = await apiCall('/api/inspect', 'POST', {
        object: state.selectedObject
    });
    
    showAnalyzing(false);
    
    if (result.success) {
        showFrozenFrame(result.image);
        updateResults(result);
        state.lastInspection = result;
    } else {
        console.error('Inspection failed:', result.error);
    }
}

async function newInspection() {
    showLiveFeed();
    updateResults(null);
    await apiCall('/api/reset', 'POST');
}

async function connectCamera() {
    const deviceId = parseInt(elements.cameraInput.value) || 0;
    elements.btnCameraConnect.disabled = true;
    elements.btnCameraConnect.textContent = '...';
    
    const result = await apiCall('/api/camera/select', 'POST', { device_id: deviceId });
    
    elements.btnCameraConnect.disabled = false;
    elements.btnCameraConnect.textContent = 'CONNECT';
    
    if (result.success) {
        showLiveFeed();
        updateCameraStatus(true, deviceId);
    } else {
        updateCameraStatus(false, deviceId);
    }
}

async function fetchLogs() {
    const result = await apiCall('/api/logs');
    if (result.logs) {
        clearLog();
        result.logs.forEach(entry => addLogEntry(entry));
    }
}

async function fetchState() {
    const result = await apiCall('/api/state');
    
    if (result.selected_object) {
        updateComponentSelection(result.selected_object);
    }
    
    if (result.robot) {
        updateRobotStatus(result.robot);
    }
    
    updateCameraStatus(result.camera_connected, 0);
    
    // Update system status
    if (!result.camera_connected) {
        updateSystemStatus('error', 'NO CAMERA');
    } else if (result.robot && result.robot.state === 'error') {
        updateSystemStatus('error', 'ROBOT ERROR');
    } else if (state.isInspecting) {
        updateSystemStatus('busy', 'INSPECTING');
    } else {
        updateSystemStatus('ready', 'READY');
    }
    
    // Update footer API status
    elements.footerApi.textContent = 'API: OK';
}

// =============================================================================
// POLLING
// =============================================================================

let pollInterval = null;

function startPolling() {
    // Initial fetch
    fetchState();
    fetchLogs();
    
    // Poll every 2 seconds
    pollInterval = setInterval(() => {
        fetchState();
        fetchLogs();
    }, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// =============================================================================
// EVENT LISTENERS
// =============================================================================

function setupEventListeners() {
    // Component text input
    elements.componentInput.addEventListener('input', (e) => {
        const component = parseComponentFromText(e.target.value);
        if (component) {
            selectComponent(component);
        }
    });
    
    elements.componentInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const component = parseComponentFromText(e.target.value);
            if (component) {
                selectComponent(component);
            }
        }
    });
    
    // Voice button
    elements.btnVoice.addEventListener('click', toggleVoice);
    
    // Actions
    elements.btnInspect.addEventListener('click', runInspection);
    elements.btnNewInspection.addEventListener('click', newInspection);
    
    // Camera connect
    elements.btnCameraConnect.addEventListener('click', connectCamera);
    
    // Allow Enter key to connect camera when input is focused
    elements.cameraInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            connectCamera();
        }
    });
    
    // Log clear
    elements.btnClearLog.addEventListener('click', clearLog);
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Don't trigger if typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        switch (e.key.toLowerCase()) {
            case 'enter':
            case ' ':
                if (!state.isInspecting && !state.isFrozen) {
                    runInspection();
                }
                e.preventDefault();
                break;
            case 'escape':
            case 'n':
                newInspection();
                break;
            case 'v':
                toggleVoice();
                break;
        }
    });
}

// =============================================================================
// INITIALIZATION
// =============================================================================

async function init() {
    console.log('MPI Robotic Inspection System initializing...');
    
    setupEventListeners();
    setupVoiceRecognition();
    
    // Auto-connect to camera 3 on startup
    connectCamera();
    
    startPolling();
    
    console.log('System ready');
}

// Start when DOM is loaded
document.addEventListener('DOMContentLoaded', init);
