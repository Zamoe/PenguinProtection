// firebase-config.js

// Firebase configuration object for the Penguard project
const firebaseConfig = {
  apiKey: "AIzaSyBTp7FQ4ylwiwjlpZccXsUKIOl1qCoLbxo", // Auth key for accessing Firebase
  authDomain: "penguin-deterrent.firebaseapp.com",  // Auth domain for Firebase Auth
  databaseURL: "https://penguin-deterrent-64225-default-rtdb.firebaseio.com", // Realtime DB URL
  projectId: "penguin-deterrent", // Firebase project ID
  storageBucket: "penguin-deterrent.appspot.com",  // Cloud Storage bucket (typo fixed)
  messagingSenderId: "551637989224", // Used for FCM (not used here)
  appId: "1:551637989224:web:a720009de9106439b088dd", // Unique app instance ID
  measurementId: "G-WCJ8J3RTPL" // For Google Analytics (optional)
};

// Initialize Firebase with the config above
firebase.initializeApp(firebaseConfig);
