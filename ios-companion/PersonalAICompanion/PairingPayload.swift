import Foundation

struct PairingPayload: Equatable {
    let version: Int
    let token: String
    let code: String
    let expiresAt: Date
    let baseURL: String?
    let serviceID: String?
    let certSHA256: String?
    let fallbackURL: String?

    var zeroConfig: Bool { version == 2 && serviceID != nil && certSHA256 != nil }

    private static let v1Fields: Set<String> = ["v", "base", "token", "code", "expires"]
    private static let v2Required: Set<String> = ["v", "service", "fp", "token", "code", "expires"]
    private static let v2Fields: Set<String> = v2Required.union(["fallback"])
    private static let localHosts: Set<String> = ["127.0.0.1", "localhost", "::1"]

    static func normalizeOrigin(_ raw: String, allowLocalHTTP: Bool = false) throws -> String {
        guard let components = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = components.scheme?.lowercased(),
              let host = components.host?.lowercased(), !host.isEmpty else {
            throw PairingPayloadError.invalidURL
        }
        if components.user != nil || components.password != nil { throw PairingPayloadError.credentialsInURL }
        if components.fragment != nil { throw PairingPayloadError.fragmentInURL }
        let localHTTP = scheme == "http" && allowLocalHTTP && localHosts.contains(host)
        guard scheme == "https" || localHTTP else { throw PairingPayloadError.insecureURL }
        var origin = URLComponents()
        origin.scheme = scheme
        origin.host = components.host
        origin.port = components.port
        guard let value = origin.url?.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) else {
            throw PairingPayloadError.invalidURL
        }
        return value
    }

    static func parse(_ raw: String, allowLocalHTTP: Bool = false, now: Date = Date()) throws -> PairingPayload {
        guard let components = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
              components.scheme == "vishnu", components.host == "pair",
              components.path.isEmpty || components.path == "/", components.fragment == nil else {
            throw PairingPayloadError.notVishnuPairingCode
        }
        let items = components.queryItems ?? []
        guard let versionRaw = items.first(where: { $0.name == "v" })?.value, let version = Int(versionRaw), [1, 2].contains(version) else {
            throw PairingPayloadError.unsupportedVersion
        }
        let names = Set(items.map(\.name))
        let allowed = version == 1 ? v1Fields : v2Fields
        let required = version == 1 ? v1Fields : v2Required
        guard required.isSubset(of: names), names.isSubset(of: allowed) else { throw PairingPayloadError.invalidFields }
        var values: [String: String] = [:]
        for name in names {
            let matching = items.filter { $0.name == name }
            guard matching.count == 1, let value = matching[0].value else { throw PairingPayloadError.invalidFields }
            values[name] = value
        }
        let token = (values["token"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let code = (values["code"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard (16...256).contains(token.count) else { throw PairingPayloadError.invalidToken }
        guard code.count == 6, code.allSatisfy(\.isNumber) else { throw PairingPayloadError.invalidCode }
        guard let expirySeconds = Double(values["expires"] ?? "") else { throw PairingPayloadError.invalidExpiry }
        let expiry = Date(timeIntervalSince1970: expirySeconds)
        guard expiry > now else { throw PairingPayloadError.expired }
        if version == 1 {
            let base = try normalizeOrigin(values["base"] ?? "", allowLocalHTTP: allowLocalHTTP)
            return PairingPayload(version: 1, token: token, code: code, expiresAt: expiry, baseURL: base, serviceID: nil, certSHA256: nil, fallbackURL: nil)
        }
        let service = (values["service"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let fingerprint = (values["fp"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard service.range(of: "^[A-Za-z0-9_-]{8,64}$", options: .regularExpression) != nil else { throw PairingPayloadError.invalidService }
        guard fingerprint.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else { throw PairingPayloadError.invalidFingerprint }
        let fallback = try values["fallback"].map { try normalizeOrigin($0) }
        return PairingPayload(version: 2, token: token, code: code, expiresAt: expiry, baseURL: nil, serviceID: service, certSHA256: fingerprint, fallbackURL: fallback)
    }
}

enum PairingPayloadError: LocalizedError, Equatable {
    case notVishnuPairingCode
    case invalidFields
    case unsupportedVersion
    case invalidURL
    case credentialsInURL
    case fragmentInURL
    case insecureURL
    case invalidToken
    case invalidCode
    case invalidExpiry
    case invalidService
    case invalidFingerprint
    case expired

    var errorDescription: String? {
        switch self {
        case .notVishnuPairingCode: return "This is not a Vishnu pairing QR code."
        case .invalidFields: return "The Vishnu pairing QR code is malformed."
        case .unsupportedVersion: return "This Vishnu pairing QR version is not supported."
        case .invalidURL: return "The Vishnu address is invalid."
        case .credentialsInURL: return "Do not embed credentials in the Vishnu address."
        case .fragmentInURL: return "The Vishnu address must not contain a fragment."
        case .insecureURL: return "Use HTTPS. Plain HTTP is allowed only for explicitly enabled localhost development."
        case .invalidToken: return "The Vishnu connection key is invalid."
        case .invalidCode: return "The pairing code must contain exactly six digits."
        case .invalidExpiry: return "The pairing expiry is invalid."
        case .invalidService: return "The Vishnu local service identity is invalid."
        case .invalidFingerprint: return "The Vishnu TLS identity is invalid."
        case .expired: return "This pairing QR code has expired. Generate a new one in Vishnu."
        }
    }
}