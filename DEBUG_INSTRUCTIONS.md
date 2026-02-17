# Debug: Broadcast Channel Not Working

## Check Console Logs

### In EMR Demo Tab:
1. Open emr-demo.html
2. Press F12 (open DevTools)
3. Go to Console tab
4. Fill form and click "Start Consult"
5. Look for: `[EMR Demo] Broadcasted start-consult:`

**Should see:**
```
[EMR Demo] Broadcasted start-consult: {
  type: "start-consult",
  appointmentId: "APT-TEST-001",
  patient: { name: "...", age: 35, gender: "Male", history: "..." }
}
```

### In GMeet Tab:
1. Switch to GMeet tab
2. Press F12 (open DevTools)
3. Go to Console tab
4. Look for: `[drT Broadcast] Appointment data received:`

**Should see:**
```
[drT Broadcast] Appointment data received: {
  type: "start-consult",
  appointmentId: "APT-TEST-001",
  patient: { ... }
}
```

## If No Messages in GMeet Console:

### Possible Issues:

1. **Race Condition** - GMeet opened before broadcast sent
2. **Different Chrome Profiles** - Tabs must be in same profile
3. **Extension Not Loaded** - Verify extension is active
4. **Broadcast Channel Not Supported** - Check browser version

## Quick Fix to Test:

### Option A: Reload GMeet Tab AFTER Starting Consult
1. Fill EMR demo form
2. Click "Start Consult"
3. In the NEW GMeet tab that opens: **Reload the page** (Cmd+R or Ctrl+R)
4. Open extension panel - should now show compact display

### Option B: Open GMeet First, Then Start Consult
1. Open GMeet manually: https://meet.google.com/new
2. Wait for page to load completely
3. NOW fill EMR demo form and click "Start Consult"
4. This won't open a new tab, but check if broadcast reaches existing tab

## Manual Test - Verify Broadcast Channel Works:

In EMR demo tab console, run:
```javascript
const bc = new BroadcastChannel('drTranscribe-channel');
bc.postMessage({ type: 'test', data: 'hello' });
```

In GMeet tab console, run:
```javascript
const bc = new BroadcastChannel('drTranscribe-channel');
bc.onmessage = (e) => console.log('Received:', e.data);
```

Then send test message from EMR tab again. Should see "Received: {type: 'test', ...}" in GMeet console.
