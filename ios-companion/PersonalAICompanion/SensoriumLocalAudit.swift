import Foundation

@MainActor
final class SensoriumLocalAudit: ObservableObject {
    struct Entry: Identifiable {
        let id = UUID()
        let createdAt: Date
        let action: String
        let sensor: String
        let resourceID: String
        let reason: String
    }

    static let shared = SensoriumLocalAudit()
    @Published private(set) var entries: [Entry] = []

    private init() {}

    func record(_ action: String, sensor: String, resourceID: String = "*", reason: String) {
        entries.append(
            Entry(
                createdAt: Date(),
                action: String(action.prefix(40)),
                sensor: String(sensor.prefix(40)),
                resourceID: String(resourceID.prefix(240)),
                reason: String(reason.prefix(240))
            )
        )
        if entries.count > 100 { entries.removeFirst(entries.count - 100) }
    }

    func recent(_ limit: Int = 12) -> [Entry] {
        Array(entries.suffix(max(1, min(limit, 100))).reversed())
    }
}
