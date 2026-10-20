# Owner usage guide — Screens 11–15 current slice

1. Run the local Vishnu web runtime and open `/web/campaign-demo` to see the isolated Screens 11–15 concept preview.
2. The persistent `TEST / DEMO DATA` strip identifies all illustrative records. Names, counts, attachments and activity are local fixtures based on the approved references; they are not real owner records.
3. You may navigate Home, Conversation, Conversation History, Voice and Global Search. Composed messages stay in memory for that page session only; Voice is simulated and does not request microphone access.
4. The preview mode blocks non-GET/HEAD calls through the app API wrapper. Open `/web/` to return to the ordinary web app.
5. This preview is currently browser/PWA only. It does not qualify or replace the Windows/Linux desktop UI or Android/iOS native companion screens. Reference pixel-diff approval has not been performed.

The installed Windows desktop app, Android app and iOS app do not yet render this same five-screen UI internally. Android/iOS “Open Vishnu” may open a browser surface; this is not integrated native parity. Do not interpret this guide as a release or deployment instruction.
