import AuthenticationServices
import Foundation
import SwiftUI
import UIKit

private struct NativePasskeyChallenge {
    let baseURL: URL
    let deviceID: String
    let bearer: String
    let challengeID: String
    let rpID: String
    let challenge: Data
    let userID: Data
    let userName: String
}

@MainActor
final class NativePasskeyCoordinator: NSObject, ObservableObject,
    ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    @Published var status = "Use Face ID, Touch ID, or your device passcode to create a phishing-resistant owner passkey."
    @Published var isWorking = false

    private weak var store: CompanionStore?
    private var pending: NativePasskeyChallenge?
    private var authorizationController: ASAuthorizationController?

    init(store: CompanionStore) {
        self.store = store
        super.init()
    }

    var configuredDomain: String {
        (Bundle.main.object(forInfoDictionaryKey: "VishnuPasskeyDomain") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    var isConfigured: Bool {
        let domain = configuredDomain
        return !domain.isEmpty && !domain.hasSuffix(".invalid") && !domain.contains("/") && !domain.contains(":")
    }

    func register() {
        guard !isWorking else { return }
        guard isConfigured else {
            status = "Native passkeys are disabled in this build until a signed Vishnu runtime domain is configured in the app's webcredentials entitlement."
            return
        }
        guard let store,
              let deviceID = store.deviceID,
              let bearer = store.bearer,
              bearer.count >= 32,
              let base = URL(string: store.baseURL),
              base.scheme?.lowercased() == "https",
              base.host?.lowercased() == configuredDomain else {
            status = "Connect this iPhone to the configured secure Vishnu runtime before creating a native passkey."
            return
        }
        isWorking = true
        status = "Requesting a one-time passkey challenge from Vishnu…"
        let body: [String: Any] = [
            "device_id": deviceID,
            "device_token": bearer,
            "platform": "ios",
        ]
        Task { await requestChallenge(base: base, deviceID: deviceID, bearer: bearer, body: body) }
    }

    private func requestChallenge(base: URL, deviceID: String, bearer: String, body: [String: Any]) async {
        do {
            let endpoint = base.appending(path: "iphone/api/native/passkeys/register/options")
            let payload = try JSONSerialization.data(withJSONObject: body)
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = payload
            let transport = PinnedTransport.session(fingerprint: store?.tlsPin)
            let (data, response) = try await transport.0.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw CompanionError.badResponse("Vishnu returned no HTTP response.") }
            guard (200..<300).contains(http.statusCode) else {
                if http.statusCode == 409 {
                    throw CompanionError.badResponse("Native passkeys are not enabled for this runtime yet. Configure the signed Apple webcredentials association first.")
                }
                if http.statusCode == 401 || http.statusCode == 403 {
                    throw CompanionError.badResponse("This iPhone is no longer authorized to manage owner security.")
                }
                throw CompanionError.badResponse("Vishnu could not start passkey setup (\(http.statusCode)).")
            }
            guard data.count <= 1_048_576,
                  let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let challengeID = json["challenge_id"] as? String,
                  let rpID = json["rp_id"] as? String,
                  rpID.lowercased() == configuredDomain,
                  let userIDText = json["user_id"] as? String,
                  let userID = Self.base64URLDecode(userIDText),
                  let userName = json["user_name"] as? String,
                  let publicKey = json["public_key"] as? [String: Any],
                  let challengeText = publicKey["challenge"] as? String,
                  let challenge = Self.base64URLDecode(challengeText) else {
                throw CompanionError.badResponse("Vishnu returned an invalid passkey challenge.")
            }
            let record = NativePasskeyChallenge(
                baseURL: base,
                deviceID: deviceID,
                bearer: bearer,
                challengeID: challengeID,
                rpID: rpID,
                challenge: challenge,
                userID: userID,
                userName: userName
            )
            pending = record
            let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(relyingPartyIdentifier: rpID)
            let registration = provider.createCredentialRegistrationRequest(
                challenge: challenge,
                name: userName,
                userID: userID
            )
            registration.displayName = userName
            registration.userVerificationPreference = .required
            let controller = ASAuthorizationController(authorizationRequests: [registration])
            controller.delegate = self
            controller.presentationContextProvider = self
            authorizationController = controller
            status = "Confirm the passkey with Face ID, Touch ID, or your device passcode."
            controller.performRequests()
        } catch {
            finishWithError(error.localizedDescription)
        }
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let registration = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialRegistration,
              let record = pending,
              let attestation = registration.rawAttestationObject else {
            finishWithError("Apple did not return a complete public-key registration response.")
            return
        }
        let identifier = Self.base64URLEncode(registration.credentialID)
        let credential: [String: Any] = [
            "id": identifier,
            "rawId": identifier,
            "type": "public-key",
            "response": [
                "clientDataJSON": Self.base64URLEncode(registration.rawClientDataJSON),
                "attestationObject": Self.base64URLEncode(attestation),
                "transports": ["internal"],
            ],
        ]
        Task { await complete(record: record, credential: credential) }
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        finishWithError("Passkey creation was cancelled or unavailable: \(error.localizedDescription)")
    }

    private func complete(record: NativePasskeyChallenge, credential: [String: Any]) async {
        do {
            status = "Verifying the passkey with Vishnu…"
            let endpoint = record.baseURL.appending(path: "iphone/api/native/passkeys/register/complete")
            let body: [String: Any] = [
                "device_id": record.deviceID,
                "device_token": record.bearer,
                "platform": "ios",
                "challenge_id": record.challengeID,
                "credential": credential,
                "name": "iPhone passkey",
            ]
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let transport = PinnedTransport.session(fingerprint: store?.tlsPin)
            let (data, response) = try await transport.0.data(for: request)
            guard data.count <= 1_048_576,
                  let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode) else {
                throw CompanionError.badResponse("Vishnu rejected the native passkey verification. Start again to register a fresh credential.")
            }
            pending = nil
            authorizationController = nil
            isWorking = false
            status = "Passkey registered. The private key remains protected by Apple Authentication Services and your device security."
        } catch {
            finishWithError(error.localizedDescription)
        }
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        for scene in scenes where scene.activationState == .foregroundActive {
            if let window = scene.windows.first(where: { $0.isKeyWindow }) ?? scene.windows.first {
                return window
            }
        }
        return ASPresentationAnchor()
    }

    private func finishWithError(_ message: String) {
        pending = nil
        authorizationController = nil
        isWorking = false
        status = message
    }

    private static func base64URLEncode(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private static func base64URLDecode(_ text: String) -> Data? {
        var value = text.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        let remainder = value.count % 4
        if remainder != 0 { value += String(repeating: "=", count: 4 - remainder) }
        return Data(base64Encoded: value)
    }
}

struct NativePasskeyView: View {
    @StateObject private var coordinator: NativePasskeyCoordinator

    init(store: CompanionStore) {
        _coordinator = StateObject(wrappedValue: NativePasskeyCoordinator(store: store))
    }

    var body: some View {
        Form {
            Section("Owner passkey") {
                Text("Create a phishing-resistant passkey for the same Vishnu owner identity. Face ID or Touch ID unlocks the credential; Vishnu never receives biometric templates or the private key.")
                    .font(PersonalAITheme.Typography.supporting)
                    .foregroundStyle(.secondary)
                LabeledContent("Relying party", value: coordinator.isConfigured ? coordinator.configuredDomain : "Not configured")
                Button(coordinator.isWorking ? "Creating passkey…" : "Create passkey") {
                    coordinator.register()
                }
                .disabled(coordinator.isWorking || !coordinator.isConfigured)
                Text(coordinator.status)
                    .font(PersonalAITheme.Typography.supporting)
                    .foregroundStyle(.secondary)
            }
            if !coordinator.isConfigured {
                Section("Configuration required") {
                    Text("Internal-testing builds fail closed. A release build must set VISHNU_PASSKEY_DOMAIN and sign the app with the matching webcredentials associated-domain entitlement. The runtime must publish the matching apple-app-site-association file over HTTPS.")
                        .font(PersonalAITheme.Typography.supporting)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Passkey")
        .navigationBarTitleDisplayMode(.inline)
    }
}