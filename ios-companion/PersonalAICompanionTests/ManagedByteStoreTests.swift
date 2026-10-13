import XCTest
@testable import PersonalAICompanion

final class ManagedByteStoreTests: XCTestCase {
    func testManagedObjectReadIsIdentityAddressedProtectedAndBounded() async throws {
        let store = ManagedByteStore()
        let id = "file:ios:\(UUID().uuidString)"
        let payload = Data("hello private ios bytes".utf8)
        try await store.putForLocalUse(globalID: id, version: 1, data: payload)
        defer { Task { _ = try? await store.delete(globalID: id, version: 1) } }

        let first = try await store.readChunk(globalID: id, version: 1, offset: 0, length: 5)
        let firstB64 = try XCTUnwrap(first["bytes_b64"] as? String)
        XCTAssertEqual(String(data: try XCTUnwrap(Data(base64Encoded: firstB64)), encoding: .utf8), "hello")
        XCTAssertEqual(first["eof"] as? Bool, false)
        XCTAssertEqual(first["cache_policy"] as? String, "no_store")
        XCTAssertEqual(first["backup_allowed"] as? Bool, false)

        let rest = try await store.readChunk(globalID: id, version: 1, offset: 5, length: 1024)
        XCTAssertEqual(rest["eof"] as? Bool, true)

        do {
            _ = try await store.readChunk(globalID: id, version: 1, offset: -1, length: 8)
            XCTFail("negative offset must fail closed")
        } catch {}
        do {
            _ = try await store.readChunk(globalID: id, version: 1, offset: 0, length: ManagedByteStore.maxChunkBytes + 1)
            XCTFail("oversized chunk must fail closed")
        } catch {}
    }

    func testPathLikeGlobalIdCannotEscapeManagedObjectDirectory() async throws {
        let store = ManagedByteStore()
        let id = "../../private/system/file"
        try await store.putForLocalUse(globalID: id, version: 1, data: Data("managed only".utf8))
        defer { Task { _ = try? await store.delete(globalID: id, version: 1) } }
        let result = try await store.readChunk(globalID: id, version: 1, offset: 0, length: 1024)
        XCTAssertNil(result["path"])
        let encoded = try XCTUnwrap(result["bytes_b64"] as? String)
        XCTAssertEqual(String(data: try XCTUnwrap(Data(base64Encoded: encoded)), encoding: .utf8), "managed only")
    }
}
