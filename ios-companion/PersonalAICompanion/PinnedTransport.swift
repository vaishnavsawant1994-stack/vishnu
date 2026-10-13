import CryptoKit
import Foundation
import Security

final class PinnedSessionDelegate: NSObject, URLSessionDelegate {
    private let expectedFingerprint: String?

    init(expectedFingerprint: String?) {
        let clean = expectedFingerprint?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        self.expectedFingerprint = clean?.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil ? clean : nil
        super.init()
    }

    static func fingerprint(_ certificate: SecCertificate) -> String {
        let data = SecCertificateCopyData(certificate) as Data
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        guard let pin = expectedFingerprint else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        guard let leaf = SecTrustGetCertificateAtIndex(trust, 0), Self.fingerprint(leaf) == pin else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}

struct PinnedTransport {
    static func session(fingerprint: String?) -> (URLSession, PinnedSessionDelegate?) {
        guard let fingerprint, !fingerprint.isEmpty else { return (URLSession.shared, nil) }
        let delegate = PinnedSessionDelegate(expectedFingerprint: fingerprint)
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 20
        return (URLSession(configuration: config, delegate: delegate, delegateQueue: nil), delegate)
    }
}