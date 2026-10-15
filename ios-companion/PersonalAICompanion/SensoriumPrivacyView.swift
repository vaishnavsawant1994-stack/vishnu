import SwiftUI

@MainActor
struct SensoriumPrivacyView: View {
    @ObservedObject var store: CompanionStore
    @ObservedObject private var sensorium = SensoriumContext.shared
    @ObservedObject private var localAudit = SensoriumLocalAudit.shared
    @State private var actionStatus = ""

    private let sensors: [(String, String, String)] = [
        ("microphone", "Microphone / environmental audio", "waveform"),
        ("screen", "Screen understanding", "rectangle.on.rectangle"),
        ("location", "Location + compass", "location"),
        ("motion", "Motion + orientation + barometer", "gyroscope"),
        ("environment", "Proximity + battery + thermal", "thermometer.medium"),
        ("network", "Network state", "network"),
        ("clipboard", "Clipboard context", "doc.on.clipboard"),
        ("wearable", "Apple Watch / earbuds / wearable context", "watch.analog"),
        ("document", "Local OCR / barcode", "doc.text.viewfinder"),
        ("spatial", "ARKit spatial / depth", "cube.transparent"),
    ]

    var body: some View {
        Form {
            Section("Sensorium Privacy") {
                Text("No sensor has a permanent silent allow mode. Remote Vishnu may request access, but only this iPhone can create the temporary local session.")
                    .font(.footnote).foregroundStyle(.secondary)
                LabeledContent("Camera", value: store.visionActive ? "SESSION" : "OFF")
                LabeledContent("Voice", value: store.voiceActive ? "SESSION" : "OFF")
                ForEach(sensors, id: \.0) { sensor in sensorRow(sensor.0, label: sensor.1, icon: sensor.2) }
                if !actionStatus.isEmpty { Text(actionStatus).font(.footnote).foregroundStyle(.secondary) }
            }
            Section("Active sessions") {
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    let rows = sensorium.activeGrants()
                    if rows.isEmpty && !store.visionActive && !store.voiceActive {
                        Text("Camera OFF · Microphone OFF · Screen OFF · Location OFF · Motion OFF · Environment OFF · Network OFF · Clipboard OFF · Wearable OFF · Spatial OFF")
                            .font(.footnote).foregroundStyle(.secondary)
                    } else {
                        ForEach(rows) { grant in
                            let remaining = max(0, Int(grant.expiresAt.timeIntervalSinceNow.rounded(.up)))
                            VStack(alignment: .leading, spacing: 3) {
                                Text("\(grant.sensor.uppercased()) · SESSION · \(remaining)s")
                                Text(grant.reason).font(.caption).foregroundStyle(.secondary)
                                Text("Authority: explicit local owner consent on this iPhone")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            Section("Wearables") {
                let inventory = SensoriumWearableRelay.shared.inventory()
                if let watch = inventory["apple_watch"] as? [String: Any] {
                    LabeledContent("Apple Watch", value: (watch["paired"] as? Bool ?? false) ? "PAIRED" : "NOT PAIRED")
                    LabeledContent("Watch reachable", value: (watch["reachable"] as? Bool ?? false) ? "YES" : "NO")
                }
                let earbuds = inventory["earbuds"] as? [[String: Any]] ?? []
                LabeledContent("Earbud/headphone routes", value: "\(earbuds.count)")
                Text("WatchConnectivity and earbud-route metadata provide semantic context only. Raw watch/glasses camera or microphone media must use the separate governed camera/microphone Sensorium paths.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Retention") {
                Text("Raw camera/screen frames are not retained by Sensorium. Continuous environmental audio is not retained. Clipboard reads are not retained. Wearable relay observations are semantic-only. Exact mobile location is not written to the semantic World Model by default. Semantic summaries follow the selected memory mode; selected media is saved only when explicitly chosen and privacy-processed.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Recent local sensor audit") {
                let rows = localAudit.recent(12)
                if rows.isEmpty {
                    Text("No local Sensorium session events yet.").font(.footnote).foregroundStyle(.secondary)
                } else {
                    ForEach(rows) { row in
                        VStack(alignment: .leading, spacing: 3) {
                            Text("\(row.action) · \(row.sensor.uppercased())")
                            Text("\(row.createdAt.formatted(date: .omitted, time: .standard)) · \(row.resourceID)")
                                .font(.caption).foregroundStyle(.secondary)
                            Text(row.reason).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                Text("The Vishnu server also keeps the persistent per-device permission audit, including the authenticated requesting device. This section is the current app-process audit.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Section("Emergency privacy control") {
                Button("STOP ALL SENSING", role: .destructive) { stopAll() }
                    .fontWeight(.semibold)
                Text("Stops Vishnu Vision, voice, ReplayKit, ARKit, wearable relay observations, environmental audio, location/motion updates and every temporary Sensorium grant. This does not delete existing memories; retention remains separately controlled.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Boundaries") {
                Text("Seeing, hearing, locating or sensing never authorizes Vishnu to click, type, control a device, change an IoT device or execute a tool. Those actions still use the existing policy and approval authorities.")
                    .font(.footnote).foregroundStyle(.secondary)
                Text("iOS does not expose a public ambient-light lux API to third-party apps. Vishnu reports that sensor as unavailable rather than inventing a value.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Sensorium Privacy")
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func sensorRow(_ sensor: String, label: String, icon: String) -> some View {
        let resource = sensor == "screen" ? "mobile:screen" : sensor == "spatial" ? "mobile:spatial" : "*"
        let active = sensorium.current(sensor, resourceID: resource) != nil
        HStack {
            Label(label, systemImage: icon)
            Spacer()
            Text(active ? "SESSION" : "OFF").foregroundStyle(active ? .green : .secondary)
            Button(active ? "Stop" : "Allow this session") {
                Task {
                    if active {
                        sensorium.revoke(sensor, resourceID: resource)
                        if sensor == "screen" { SensoriumScreenSession.shared.stop() }
                        if sensor == "spatial" { SensoriumSpatialSession.shared.stop() }
                        if sensor == "microphone" { SensoriumAudioFeatures.shared.stop() }
                        if sensor == "wearable" { SensoriumWearableRelay.shared.clear() }
                        localAudit.record("session_revoked", sensor: sensor, resourceID: resource, reason: "Owner stopped \(label) from Sensorium Privacy")
                        actionStatus = "\(label) stopped."
                    } else {
                        do {
                            let reason = "Owner enabled \(label) from Sensorium Privacy"
                            try await sensorium.activateByOwner(sensor, reason: reason)
                            localAudit.record("session_granted", sensor: sensor, resourceID: resource, reason: reason)
                            actionStatus = "\(label) allowed for this session."
                        } catch {
                            localAudit.record("session_denied", sensor: sensor, resourceID: resource, reason: error.localizedDescription)
                            actionStatus = error.localizedDescription
                        }
                    }
                }
            }.buttonStyle(.borderless)
        }
    }

    private func stopAll() {
        sensorium.stopAll(); SensoriumAudioFeatures.shared.stop(); SensoriumWearableRelay.shared.clear()
        store.vision.stop(); store.visionActive = false
        store.voice.deactivate(); store.voiceActive = false
        localAudit.record("stop_all", sensor: "all", reason: "Owner stopped all sensing from Sensorium Privacy")
        actionStatus = "All Vishnu sensing stopped."
    }
}
