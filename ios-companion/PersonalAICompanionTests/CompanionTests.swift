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
}