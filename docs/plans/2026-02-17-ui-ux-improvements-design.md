# drTranscribe UI/UX Improvements Design

**Date:** 2026-02-17
**Status:** Approved
**Approach:** Incremental Enhancement (Approach 1)

## Overview

This design implements user feedback to improve the drTranscribe Chrome extension with:
- EMR integration via Broadcast Channel API for cross-tab communication
- Improved recording controls (Start → Pause/Resume → End Session)
- Repositioned floating badge for better visibility
- Streamlined patient data entry workflow
- Export to EMR functionality

## User Feedback Addressed

### Extension UI and Controls
- ✅ Floating icon positioned higher (80px vs 24px) to avoid obstruction
- ✅ Recording controls: Start → Pause → Resume → End Session
- ✅ Start button converts to Pause after clicking
- ✅ Stop renamed to "End Session" for clearer terminology
- ✅ Multiple pause/resume cycles allowed
- ✅ Patient info fields not required for transcription (EMR integration)

### Patient History Integration
- ✅ Patient data auto-populated from EMR webpage via Broadcast Channel
- ✅ Patient History sent to backend with appointmentId
- ✅ Separate tracking of appointmentId for EMR association

## Architecture

### Approach: Incremental Enhancement

Minimal changes to existing working code:
- Add Broadcast Channel listener in content.js
- Conditionally hide patient form when appointmentId received
- Add pause/resume state to existing session state machine
- Create standalone EMR demo page for testing
- Add "Export to EMR" button in post-session view

**Estimated Implementation Time:** 4-6 hours

---

## Design Details

### 1. Broadcast Channel Communication

**Channel Name:** `drTranscribe-channel`

**Message Protocol:**

#### EMR → Extension (Start Consult)
```json
{
  "type": "start-consult",
  "appointmentId": "APT-12345",
  "patient": {
    "name": "John Doe",
    "age": 45,
    "gender": "Male",
    "history": "Previous consultation notes from EMR..."
  }
}
```

#### Extension → EMR (Export Results)
```json
{
  "type": "export-to-emr",
  "appointmentId": "APT-12345",
  "extraction": {
    "chief_complaint": "...",
    "diagnosis": "...",
    "medicine": "...",
    "advice": "...",
    "next_steps": "..."
  },
  "timestamp": "2026-02-17T10:30:00Z"
}
```

**Implementation:**
- Extension listens on Broadcast Channel when content.js loads on Meet/Zoom pages
- EMR page creates channel when "Start Consult" is clicked
- Channel remains open throughout session
- Future enhancement: Real-time extraction updates via Broadcast Channel

---

### 2. EMR Demo Webpage

**File:** `emr-demo.html` (project root)

**UI Structure:**
```
┌─────────────────────────────────────┐
│  drTranscribe - EMR Demo            │
├─────────────────────────────────────┤
│  Appointment ID:  [APT-12345      ] │
│  Patient Name:    [John Doe       ] │
│  Age:             [45             ] │
│  Gender:          [Male ▼         ] │
│  Patient History: [               ] │
│                   [Previous notes ] │
│                   [multiline...   ] │
│  GMeet Link:      [https://meet...] │
│                                     │
│         [Start Consult]             │
├─────────────────────────────────────┤
│  Received Extraction Results:       │
│  (appears after Export to EMR)      │
│  ┌───────────────────────────────┐ │
│  │ Chief Complaint: ...          │ │
│  │ Diagnosis: ...                │ │
│  │ Medicine: ...                 │ │
│  │ Advice: ...                   │ │
│  │ Next Steps: ...               │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

**Functionality:**

**Start Consult Button:**
1. Validates all fields are filled
2. Creates Broadcast Channel (`drTranscribe-channel`)
3. Broadcasts `start-consult` message with appointment data
4. Opens GMeet link in new tab via `window.open(meetLink, '_blank')`
5. Shows "Consult started - waiting for results..." message

**Received Results Section:**
- Initially hidden
- Listens for `export-to-emr` messages on Broadcast Channel
- Displays received extraction results in formatted text
- Shows timestamp and appointmentId for verification

**Styling:** Dark theme consistent with extension (similar to popup.css)

---

### 3. Extension UI Changes

#### 3.1 Badge Position
**File:** `chromeExtension/content.css`

```css
/* Line 10: Update badge position */
.drt-badge {
    bottom: 80px;  /* Changed from 24px */
    right: 24px;
    /* ... rest unchanged */
}
```

#### 3.2 Patient Info Section

**Before (current):**
```
┌─────────────────────────┐
│ drT    Ready      [- ×] │
├─────────────────────────┤
│ PATIENT INFO            │
│ Name: [____________]    │
│ Age: [__] Gender: [▼]   │
│ [Start] [Stop]          │
├─────────────────────────┤
│ Results...              │
└─────────────────────────┘
```

**After (with appointmentId from EMR):**
```
┌─────────────────────────┐
│ drT    Ready      [- ×] │
├─────────────────────────┤
│ Recording for:          │
│ John Doe, 45, Male      │
│ Appt: APT-12345         │
│                         │
│ [Start Session]         │
├─────────────────────────┤
│ Results...              │
└─────────────────────────┘
```

**During Recording:**
```
┌─────────────────────────┐
│ drT  Recording... [- ×] │
├─────────────────────────┤
│ John Doe, 45, Male      │
│                         │
│ [Pause] [End Session]   │
├─────────────────────────┤
│ Chief Complaint: ...    │
│ Diagnosis: ...          │
└─────────────────────────┘
```

**When Paused:**
```
│ [Resume] [End Session]  │
```

#### 3.3 Recording Controls State Flow

```
Start Session → Pause → Resume → Pause → ... → End Session
     ↓           ↓         ↓                      ↓
  (recording) (paused) (recording)           (post-session)
```

**Button Behavior:**
- **Start Session**: Green button, starts recording, converts to "Pause"
- **Pause**: Blue button, stops audio capture, changes to "Resume"
- **Resume**: Green button, restarts audio capture, changes back to "Pause"
- **End Session**: Red button, always visible, stops session → post-session view

**Implementation:**
- Conditionally render patient form vs compact patient display
- Add state variable: `appointmentData` to store received data
- Update button rendering based on `isPaused` flag

---

### 4. Audio State Management

**State Variables (content.js):**
```javascript
let sessionPhase = 'pre';        // 'pre' | 'recording' | 'paused' | 'post'
let isPaused = false;            // Track pause state
let appointmentData = null;      // Store received appointment/patient data
```

**State Transitions:**

#### Start Session
- Set `sessionPhase = 'recording'`
- Set `isPaused = false`
- Call `startMicCapture()` - begins audio capture
- Start sending audio chunks to backend
- Send WebSocket message: `start-session` with appointmentId + patient data
- Update UI: button changes to "Pause"

#### Pause
- Set `isPaused = true`
- Set `sessionPhase = 'paused'`
- Call `stopMicCapture()` - **completely stops audio capture**
- Stop sending audio chunks to backend
- Update UI: button changes to "Resume", status shows "Paused"

#### Resume
- Set `isPaused = false`
- Set `sessionPhase = 'recording'`
- Call `startMicCapture()` again - restarts audio capture
- Resume sending audio chunks
- Update UI: button changes back to "Pause", status shows "Recording"

#### End Session
- Call `stopMicCapture()`
- Send WebSocket message: `stop-session`
- Set `sessionPhase = 'post'`
- Transition to post-session view (editable textareas + export options)

**Key Difference from Current:**
- Current: "Stop" button ends session immediately
- New: "Pause" is temporary/reversible, "End Session" is final

---

### 5. Export to EMR

**Location:** Post-session export bar

**Current Export Bar:**
```html
<div class="drt-export-actions">
  <button id="drt-export-pdf">Export PDF</button>
  <button id="drt-export-email">Open in Gmail</button>
  <button id="drt-export-clipboard">Copy to Clipboard</button>
  <button id="drt-export-txt">Download TXT</button>
</div>
```

**Updated Export Bar:**
```html
<div class="drt-export-actions">
  <button id="drt-export-emr" class="drt-btn-export-primary">
    Export to EMR
  </button>
  <button id="drt-export-pdf">Export PDF</button>
  <button id="drt-export-email">Open in Gmail</button>
  <button id="drt-export-clipboard">Copy to Clipboard</button>
  <button id="drt-export-txt">Download TXT</button>
</div>
```

**Export to EMR Implementation:**
```javascript
document.getElementById('drt-export-emr').addEventListener('click', () => {
  // Gather edited extraction data from textareas
  const extraction = {
    chief_complaint: document.getElementById('drt-edit-chief_complaint').value,
    diagnosis: document.getElementById('drt-edit-diagnosis').value,
    medicine: document.getElementById('drt-edit-medicine').value,
    advice: document.getElementById('drt-edit-advice').value,
    next_steps: document.getElementById('drt-edit-next_steps').value
  };

  // Broadcast to EMR page
  if (broadcastChannel) {
    broadcastChannel.postMessage({
      type: 'export-to-emr',
      appointmentId: appointmentData.appointmentId,
      extraction: extraction,
      timestamp: new Date().toISOString()
    });
    showToast('Exported to EMR successfully!');
  } else {
    showToast('EMR connection not available. Use other export options.');
  }
});
```

**Styling:** Primary button (blue/prominent) to emphasize main export action

---

### 6. End-to-End Data Flow

```
┌─────────────────┐
│   EMR Webpage   │
│  (emr-demo.html)│
└────────┬────────┘
         │ 1. Doctor fills form & clicks "Start Consult"
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Broadcast Channel: "drTranscribe-channel"              │
│ Message: { type: 'start-consult', appointmentId,       │
│            patient: { name, age, gender, history } }    │
└────────┬────────────────────────────────────────────────┘
         │ 2. Opens GMeet in new tab (window.open)
         │
         ▼
┌─────────────────┐
│  Google Meet    │
│   + Extension   │
│  (content.js)   │
└────────┬────────┘
         │ 3. Receives appointmentId + patient data
         │    Displays: "Recording for: John Doe"
         │    Shows: [Start Session] button
         │
         │ 4. Doctor clicks "Start Session"
         │
         ▼
┌─────────────────┐
│  Audio Capture  │  5. Captures mic audio
│  (mic + tab)    │     Sends chunks every 7 seconds
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Backend      │  6. Transcribes (Groq Whisper)
│   (WebSocket)   │     Extracts (GPT-4)
└────────┬────────┘     Stores with appointmentId
         │
         │ 7. Sends extraction updates
         │
         ▼
┌─────────────────┐
│   Extension     │  8. Displays results in cards
│   (content.js)  │     Chief Complaint, Diagnosis, etc.
└────────┬────────┘
         │
         │ 9. Doctor clicks "End Session"
         │
         ▼
┌─────────────────┐
│  Post-Session   │ 10. Shows editable textareas
│      View       │     + Export options
└────────┬────────┘
         │
         │ 11. Doctor reviews/edits, clicks "Export to EMR"
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Broadcast Channel: "drTranscribe-channel"              │
│ Message: { type: 'export-to-emr', appointmentId,       │
│            extraction: { ... }, timestamp }             │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│   EMR Webpage   │ 12. Receives extraction results
│                 │     Displays in "Received Results"
└─────────────────┘
```

**Key Points:**
- Backend associates all data with appointmentId (for future retrieval via API)
- Patient History sent to backend but NOT displayed in extension UI
- Extension remains functional even if EMR page is closed
- Multiple pause/resume cycles supported throughout recording phase

---

### 7. Error Handling

#### Scenario 1: No Broadcast Channel Data Received
- **Situation:** Extension loads on Meet/Zoom but no EMR data
- **Behavior:** Show original patient info form as fallback
- **UI Message:** "No appointment data received. Enter patient info manually or start from EMR page."

#### Scenario 2: Broadcast Channel Not Supported
- **Situation:** Old browser doesn't support Broadcast Channel API
- **Behavior:** Graceful degradation to manual entry mode
- **Detection:** `if (!window.BroadcastChannel) { /* show form */ }`

#### Scenario 3: GMeet Opens Before Broadcast Sent
- **Situation:** Race condition - tab opens before broadcast message
- **Behavior:** Extension waits 3 seconds for broadcast, then shows fallback form
- **Implementation:** Timeout listener for delayed broadcast messages

#### Scenario 4: Backend Connection Fails
- **Situation:** WebSocket connection to backend fails during session
- **Current Behavior:** Already handled with status "Error" and reconnection logic
- **No Changes Needed**

#### Scenario 5: EMR Page Closed During Session
- **Situation:** Doctor closes EMR demo page while recording
- **Behavior:** Extension continues normally, "Export to EMR" will show warning
- **UI Toast:** "EMR page closed. Use other export options."

#### Scenario 6: Export to EMR When EMR Page Not Listening
- **Situation:** Click "Export to EMR" but EMR page is closed/not listening
- **Behavior:** postMessage succeeds (no error thrown), show warning toast
- **UI Toast:** "Export sent. If EMR page is closed, data is still available via other exports."

---

## Implementation Checklist

### Phase 1: EMR Demo Page
- [ ] Create `emr-demo.html` with form fields
- [ ] Add Broadcast Channel sender logic
- [ ] Implement `window.open()` for GMeet launch
- [ ] Add listener for `export-to-emr` messages
- [ ] Style with dark theme (consistent with extension)

### Phase 2: Extension - Broadcast Channel
- [ ] Add Broadcast Channel listener in content.js
- [ ] Store `appointmentData` when `start-consult` received
- [ ] Implement fallback timeout (3 seconds) for race condition

### Phase 3: Extension - UI Changes
- [ ] Update badge position: `bottom: 80px` in content.css
- [ ] Add compact patient display component
- [ ] Conditionally hide patient form when appointmentData exists
- [ ] Update Start button to "Start Session"
- [ ] Rename Stop button to "End Session"

### Phase 4: Extension - Pause/Resume
- [ ] Add `isPaused` state variable
- [ ] Add "Pause" button (shown during recording)
- [ ] Add "Resume" button (shown when paused)
- [ ] Update `startMicCapture()` / `stopMicCapture()` calls
- [ ] Update status display ("Recording" / "Paused")

### Phase 5: Extension - Export to EMR
- [ ] Add "Export to EMR" button in post-session export bar
- [ ] Style as primary button
- [ ] Implement click handler with Broadcast Channel postMessage
- [ ] Add success/error toast notifications
- [ ] Test with EMR page open/closed scenarios

### Phase 6: Backend Changes (if needed)
- [ ] Update WebSocket handler to accept appointmentId
- [ ] Store appointmentId with transcription data
- [ ] Include patient history in session metadata

### Phase 7: Testing
- [ ] Test EMR → Extension data flow
- [ ] Test pause/resume cycles (multiple times)
- [ ] Test Extension → EMR export flow
- [ ] Test error scenarios (no broadcast, EMR closed, etc.)
- [ ] Test badge positioning on Meet/Zoom
- [ ] Test fallback to manual entry mode

---

## Backend API Changes

### WebSocket Message Updates

#### Client → Server (Start Session)
```json
{
  "type": "start_session",
  "appointmentId": "APT-12345",
  "patient": {
    "name": "John Doe",
    "age": 45,
    "gender": "Male",
    "history": "Previous consultation notes..."
  }
}
```

**Changes:**
- Add `appointmentId` field (required)
- Add `history` field in patient object (optional)
- Backend stores appointmentId with session for future API retrieval

#### Server → Client (No Changes)
- Extraction updates remain unchanged
- Error messages remain unchanged

---

## Future Enhancements

1. **Real-time Extraction Broadcasting**
   - Broadcast extraction updates to EMR page in real-time (not just on export)
   - EMR page shows live extraction as consultation progresses

2. **Bidirectional EMR Sync**
   - EMR page can send updates to extension during session
   - Support for EMR-initiated session termination

3. **Offline Mode**
   - Cache appointmentId and extraction locally if backend unavailable
   - Sync when connection restored

4. **Session Resume**
   - Allow resuming incomplete sessions from EMR page
   - Fetch previous appointmentId session data from backend API

5. **Multi-Appointment Support**
   - Handle multiple concurrent consultations
   - Track multiple appointmentIds in extension

---

## Testing Strategy

### Unit Tests
- Broadcast Channel message parsing
- State machine transitions (pre → recording → paused → post)
- Audio capture start/stop logic

### Integration Tests
- EMR page → Extension communication
- Extension → Backend WebSocket flow
- Extension → EMR page export flow

### Manual Testing Scenarios
1. Happy path: EMR → Meet → Record → Export → EMR receives
2. Pause/Resume multiple times during session
3. Close EMR page mid-session, continue recording
4. Open Meet directly (no EMR), test manual entry fallback
5. Test on old browser without Broadcast Channel support
6. Rapid clicks on Start/Pause/Resume buttons (debouncing)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Race condition: Meet opens before broadcast | 3-second timeout listener |
| Broadcast Channel not supported | Feature detection + fallback to manual entry |
| EMR page closed during session | Extension continues, shows warning on export |
| Multiple concurrent sessions | Future enhancement - not in MVP scope |
| Patient data privacy in Broadcast Channel | Data only in memory, not persisted in browser |

---

## Success Metrics

- ✅ Badge visible at all times (not obstructed)
- ✅ Doctors can pause/resume without losing data
- ✅ No manual patient entry when starting from EMR
- ✅ Extraction results successfully exported to EMR page
- ✅ Graceful degradation when EMR integration unavailable

---

## Conclusion

This incremental enhancement approach delivers all requested UX improvements while maintaining the stability of the existing working extension. The Broadcast Channel API enables seamless EMR integration without complex backend changes, and the improved recording controls give doctors better session management.

**Total Estimated Implementation Time:** 4-6 hours

**Next Steps:** Move to implementation planning with writing-plans skill.
