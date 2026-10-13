import Foundation

@MainActor
final class ManagedByteBridge {
    static let shared = ManagedByteBridge()
    private let store = ManagedByteStore()
    private var installed = false

    func install(on socket: DeviceSocket) {
        guard !installed else { return }
        installed = true
        let previous = socket.commandHandler
        socket.commandHandler = { [store] message in
            let action = message["action"] as? String ?? ""
            guard action == "data_plane_byte_read" else {
                if let previous { return await previous(message) }
                return ["ok": false, "error": "Unsupported iOS action: \(action)"]
            }
            let params = message["parameters"] as? [String: Any] ?? [:]
            guard let sessionID = params["session_id"] as? String,
                  let leaseID = params["lease_id"] as? String,
                  sessionID.count >= 8, sessionID.count <= 200,
                  leaseID.count >= 8, leaseID.count <= 200,
                  let globalID = params["global_id"] as? String,
                  let version = (params["object_version"] as? NSNumber)?.intValue,
                  let offset = (params["offset"] as? NSNumber)?.int64Value,
                  let length = (params["length"] as? NSNumber)?.intValue else {
                return ["ok": false, "error": "complete lease-bound byte-read parameters are required"]
            }
            do {
                let result = try await store.readChunk(
                    globalID: globalID, version: version, offset: offset, length: length
                )
                return ["ok": true, "result": result]
            } catch {
                return ["ok": false, "error": error.localizedDescription]
            }
        }
    }
}
