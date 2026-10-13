import XCTest
@testable import PersonalAICompanion

final class CompanionTests: XCTestCase {
    func testPairRequestEncodesIOSPlatform() throws {
        let data = try JSONEncoder().encode(PairRequest(token:"token",code:"123456",name:"iPhone",platform:"ios"))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])
        XCTAssertEqual(object["platform"] as? String,"ios")
        XCTAssertEqual(object["code"] as? String,"123456")
    }

    func testInsecureTransportHasExplicitSecurityMessage() {
        XCTAssertTrue(CompanionError.insecureTransport.localizedDescription.lowercased().contains("https"))
    }

    func testPairResponseDecodesServerShape() throws {
        let json = #"{"device":{"id":"ios-device"},"bearer_token":"placeholder"}"#.data(using:.utf8)!
        let value = try JSONDecoder().decode(PairResponse.self,from:json)
        XCTAssertEqual(value.device.id,"ios-device")
        XCTAssertEqual(value.bearer_token,"placeholder")
    }

    func testPairingQRParsesAndNormalizesOrigin() throws {
        let token = String(repeating:"a",count:32)
        let raw = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test%2Fignored&token=\(token)&code=123456&expires=9999999999"
        let payload = try PairingPayload.parse(raw,now:Date(timeIntervalSince1970:100))
        XCTAssertEqual(payload.version,1)
        XCTAssertEqual(payload.baseURL,"https://vishnu.example.test")
        XCTAssertEqual(payload.token,token)
        XCTAssertEqual(payload.code,"123456")
    }

    func testZeroConfigQRUsesServiceIdentityAndPinnedCertificate() throws {
        let token=String(repeating:"b",count:32)
        let service="0123456789abcdef0123456789abcdef"
        let pin=String(repeating:"ab",count:32)
        let raw="vishnu://pair?v=2&service=\(service)&fp=\(pin)&token=\(token)&code=654321&expires=9999999999&fallback=https%3A%2F%2Frelay.example.test"
        let payload=try PairingPayload.parse(raw,now:Date(timeIntervalSince1970:100))
        XCTAssertTrue(payload.zeroConfig)
        XCTAssertNil(payload.baseURL)
        XCTAssertEqual(payload.serviceID,service)
        XCTAssertEqual(payload.certSHA256,pin)
        XCTAssertEqual(payload.fallbackURL,"https://relay.example.test")
    }

    func testZeroConfigQRRejectsInvalidTLSFingerprint() {
        let token=String(repeating:"a",count:32)
        let raw="vishnu://pair?v=2&service=0123456789abcdef&fp=bad&token=\(token)&code=123456&expires=9999999999"
        XCTAssertThrowsError(try PairingPayload.parse(raw,now:Date(timeIntervalSince1970:100))) { error in
            XCTAssertEqual(error as? PairingPayloadError,.invalidFingerprint)
        }
    }

    func testPairingQRRejectsExpiredOffer() {
        let token = String(repeating:"a",count:32)
        let raw = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test&token=\(token)&code=123456&expires=100"
        XCTAssertThrowsError(try PairingPayload.parse(raw,now:Date(timeIntervalSince1970:101))) { error in
            XCTAssertEqual(error as? PairingPayloadError,.expired)
        }
    }

    func testPairingOriginRejectsRemotePlainHTTP() {
        XCTAssertThrowsError(try PairingPayload.normalizeOrigin("http://vishnu.example.test")) { error in
            XCTAssertEqual(error as? PairingPayloadError,.insecureURL)
        }
        XCTAssertEqual(try PairingPayload.normalizeOrigin("http://localhost:8766/path",allowLocalHTTP:true),"http://localhost:8766")
    }

    func testMobileDataPlaneStoresOnlyProgressProjection() async throws {
        let store=MobileDataPlaneStore()
        let id="test:\(UUID().uuidString)"
        let result=try await store.put(globalID:id,entityType:"project",version:1,payload:[
            "project_name":"Rudra",
            "status":"active",
            "next_step":"Finish homepage",
            "private_detail":"must not replicate"
        ])
        let payload=try XCTUnwrap(result["payload"] as? [String:Any])
        XCTAssertEqual(payload["project_name"] as? String,"Rudra")
        XCTAssertEqual(payload["next_step"] as? String,"Finish homepage")
        XCTAssertNil(payload["private_detail"])
        let status=await store.status()
        XCTAssertEqual(status["pending_local_events"] as? Int,0)
        XCTAssertEqual(status["raw_file_bytes_stored"] as? Bool,false)
    }

    func testMobileDataPlaneRejectsSecretRawContentAndDivergentSameVersion() async throws {
        let store=MobileDataPlaneStore()
        let id="test:\(UUID().uuidString)"
        do {
            _=try await store.put(globalID:id,entityType:"project",version:1,payload:["status":"active","api_key":"secret"])
            XCTFail("secret-bearing progress must fail closed")
        } catch {
            XCTAssertTrue(error.localizedDescription.lowercased().contains("prohibited"))
        }
        do {
            _=try await store.put(globalID:id,entityType:"project",version:1,payload:["status":"active","file_bytes":"raw"])
            XCTFail("raw file bytes must fail closed")
        } catch {
            XCTAssertTrue(error.localizedDescription.lowercased().contains("prohibited"))
        }
        _=try await store.put(globalID:id,entityType:"project",version:3,payload:["status":"new"])
        let stale=try await store.put(globalID:id,entityType:"project",version:2,payload:["status":"old"])
        XCTAssertEqual(stale["conflict"] as? Bool,true)
        let divergent=try await store.put(globalID:id,entityType:"project",version:3,payload:["status":"different"])
        XCTAssertEqual(divergent["conflict"] as? Bool,true)
    }

    func testLocalOfflineProgressRemainsPendingUntilAcknowledged() async throws {
        let store=MobileDataPlaneStore()
        let id="test-local:\(UUID().uuidString)"
        let result=try await store.putLocal(globalID:id,entityType:"project",payload:[
            "project_name":"Rudra","status":"active","next_step":"Continue on laptop"
        ])
        XCTAssertEqual(result["applied"] as? Bool,true)
        XCTAssertEqual(result["version"] as? Int,1)
        let sourceEventID=try XCTUnwrap(result["source_event_id"] as? String)
        let pending=await store.pending()
        let events=try XCTUnwrap(pending["events"] as? [[String:Any]])
        XCTAssertEqual(events.count,1)
        XCTAssertEqual(events[0]["source_event_id"] as? String,sourceEventID)
        let payload=try XCTUnwrap(events[0]["payload"] as? [String:Any])
        XCTAssertEqual(payload["next_step"] as? String,"Continue on laptop")
        XCTAssertTrue(try await store.acknowledge(sourceEventID:sourceEventID))
        let after=await store.pending()
        XCTAssertEqual((after["events"] as? [[String:Any]])?.count,0)
    }
}
