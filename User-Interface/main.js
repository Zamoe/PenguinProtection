
window.onload = function () { 
  const db = firebase.database();
  const TIMEOUT_MS = 60 * 1000; // Timeout after 1 minute

  // DOM elements that show status for each device
  const statusElements = {
    esp32: document.getElementById("esp32-status"),
    raspberry_pi: document.getElementById("pi-status")
  };

  // Stores latest known timestamps from devices
  const lastSeenTimestamps = {
    esp32: null,
    raspberry_pi: null
  };

  // Tracks currently shown state to avoid redundant updates
  const shownStates = {
    esp32: null,
    raspberry_pi: null
  };

  // Force check if device is online or offline based on timestamp
  function forceEvaluateStatus(device) {
    const el = statusElements[device];
    const lastSeenStr = lastSeenTimestamps[device];

    console.log(`⏱ Evaluating ${device} | last_seen: ${lastSeenStr}`);

    if (!lastSeenStr) {
      // No data yet → mark offline
      if (shownStates[device] !== "offline") {
        console.log(`${device} → No last_seen. Marking offline.`);
        el.innerHTML = `<span class="offline">🔴 Offline</span>`;
        shownStates[device] = "offline";
      }
      return;
    }

    const lastSeenTime = Date.parse(lastSeenStr);
    const now = Date.now();
    const age = now - lastSeenTime;

    console.log(`${device} → age: ${age}ms`);

    if (!isNaN(lastSeenTime)) {
      if (age > TIMEOUT_MS && shownStates[device] !== "offline") {
        // Too old → offline
        console.log(`${device} → TIMEOUT. Marking offline.`);
        el.innerHTML = `<span class="offline">🔴 Offline</span> (last seen: ${lastSeenStr})`;
        shownStates[device] = "offline";
      } else if (age <= TIMEOUT_MS && shownStates[device] !== "online") {
        // Recently seen → online
        console.log(`${device} → Recovered. Marking online.`);
        el.innerHTML = `<span class="online">🟢 Online</span> (${lastSeenStr})`;
        shownStates[device] = "online";
      }
    }
  }

  // Mark device online and update UI
  function markOnline(device, timestampStr) {
    lastSeenTimestamps[device] = timestampStr;
    if (shownStates[device] !== "online") {
      shownStates[device] = "online";
      const el = statusElements[device];
      el.innerHTML = `<span class="online">🟢 Online</span> (${timestampStr})`;
    }
  }

  // Realtime listener for device statuses in Firebase
  db.ref("status").on("value", (snapshot) => {
    const data = snapshot.val();

    if (data?.esp32?.last_seen) {
      markOnline("esp32", data.esp32.last_seen);
    }

    if (data?.raspberry_pi?.last_seen) {
      markOnline("raspberry_pi", data.raspberry_pi.last_seen);
    }
  });

  // Re-evaluate status every 5 seconds
  setInterval(() => {
    forceEvaluateStatus("esp32");
    forceEvaluateStatus("raspberry_pi");
  }, 5000);

  // ✅ Manual trigger handler for deterrent (e.g., via button)
  window.triggerDeterrent = function () {
    const confirmTrigger = confirm("⚠️ Are you sure you want to trigger the deterrent?");
    if (!confirmTrigger) return;

    const now = new Date().toISOString();

    // Write trigger command to Firebase
    db.ref("commands/trigger_deterrent").set({ time: now })
      .then(() => alert("✅ Deterrent triggered at " + now))
      .catch((err) => alert("❌ Failed: " + err.message));
  };

  // 🔁 Listen for new deterrent logs being added
  const logsRef = db.ref("Deterrents");

  logsRef.limitToLast(1).on("child_added", (snapshot) => {
    const data = snapshot.val();
    const entryTime = new Date(data.timestamp).getTime();
    const now = Date.now();

    console.log("🔥 New deterrent log added:", data);

    // Only alert if log is recent (within 10s)
    if (now - entryTime < 10000) {
      showNewLogAlert();
    }
  });

  // 🔔 Show new detection alert popup
  function showNewLogAlert() {
    const alertBox = document.getElementById("new-log-alert");
    if (!alertBox) {
      console.warn("⚠️ Alert box not found in DOM.");
      return;
    }
    alertBox.style.display = "block";
    setTimeout(() => {
      alertBox.style.display = "none";
    }, 5000); // Hide after 5s
  }
};
