import CryptoKit
import Foundation

actor ManagedByteStore {
    static let maxChunkBytes = 256 * 1024
    private let root: URL

    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let directory = support.appendingPathComponent("Vishnu/managed-objects", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutable = directory
        try? mutable.setResourceValues(values)
        self.root = directory
    }

    private func validate(globalID: String, version: Int) throws {
        guard !globalID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              globalID.count <= 240,
              version >= 1 else {
            throw NSError(domain: "VishnuManagedByteStore", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "invalid managed object identity"])
        }
    }

    private func objectURL(globalID: String, version: Int) throws -> URL {
        try validate(globalID: globalID, version: version)
        let digest = SHA256.hash(data: Data(globalID.utf8)).map { String(format: "%02x", $0) }.joined()
        let directory = root.appendingPathComponent(digest, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutable = directory
        try? mutable.setResourceValues(values)
        return directory.appendingPathComponent("v\(version).bin")
    }

    /// Internal app workflow only. It is intentionally not exposed as a remote write command.
    func putForLocalUse(globalID: String, version: Int, data: Data) throws {
        let destination = try objectURL(globalID: globalID, version: version)
        try data.write(to: destination, options: [.atomic, .completeFileProtection])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutable = destination
        try? mutable.setResourceValues(values)
    }

    func readChunk(globalID: String, version: Int, offset: Int64, length: Int) throws -> [String: Any] {
        try validate(globalID: globalID, version: version)
        guard offset >= 0 else {
            throw NSError(domain: "VishnuManagedByteStore", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "offset must be non-negative"])
        }
        guard (1...Self.maxChunkBytes).contains(length) else {
            throw NSError(domain: "VishnuManagedByteStore", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "length exceeds governed chunk limit"])
        }
        let url = try objectURL(globalID: globalID, version: version)
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw NSError(domain: "VishnuManagedByteStore", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "managed Vishnu object is unavailable"])
        }
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        let size = (attributes[.size] as? NSNumber)?.int64Value ?? 0
        guard offset <= size else {
            throw NSError(domain: "VishnuManagedByteStore", code: 5,
                          userInfo: [NSLocalizedDescriptionKey: "offset exceeds object size"])
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(offset))
        let remaining = max(0, size - offset)
        let wanted = min(length, Int(remaining))
        let data = try handle.read(upToCount: wanted) ?? Data()
        return [
            "bytes_b64": data.base64EncodedString(),
            "bytes_read": data.count,
            "offset": offset,
            "object_size": size,
            "eof": offset + Int64(data.count) >= size,
            "cache_policy": "no_store",
            "backup_allowed": false,
        ]
    }

    func delete(globalID: String, version: Int) throws -> Bool {
        let url = try objectURL(globalID: globalID, version: version)
        guard FileManager.default.fileExists(atPath: url.path) else { return true }
        try FileManager.default.removeItem(at: url)
        return true
    }
}
