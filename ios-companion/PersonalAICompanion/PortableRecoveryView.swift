import Foundation
import Security
import SwiftUI
import UIKit
import UniformTypeIdentifiers

@MainActor
struct PortableRecoveryView: View {
    @ObservedObject var store: CompanionStore
    @State private var baseURL = KeychainStore.shared.get("portable_restore_base") ?? ""
    @State private var bootstrap = ""
    @State private var passphrase = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var privacyMode = "local_preferred"
    @State private var archiveURL: URL?
    @State private var keyURL: URL?
    @State private var chooseArchive = false
    @State private var chooseKey = false
    @State private var status = "Choose the recovery package and its separately encrypted recovery-key file."
    @State private var isWorking = false
    @State private var recoveryCodes = KeychainStore.shared.get("portable_restore_codes") ?? ""
    @State private var recoverySaved = false

    private let keychain = KeychainStore.shared

    var body: some View {
        Form {
            Section("Portable recovery") {
                TextField("Fresh Vishnu runtime URL (https://…)", text: $baseURL)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                SecureField("One-time runtime setup code", text: $bootstrap)
                SecureField("Recovery-key passphrase", text: $passphrase)
                Button(archiveURL == nil ? "Choose .vdr recovery package" : "Recovery package selected") { chooseArchive = true }
                Button(keyURL == nil ? "Choose encrypted recovery key" : "Recovery key selected") { chooseKey = true }
                Button(isWorking ? "Working…" : "Validate and schedule restore") {
                    Task { await scheduleRestore() }
                }
                .disabled(isWorking)
                Text("The files are streamed from temporary local copies to the fresh HTTPS runtime. The recovery passphrase is not written to Keychain or user defaults.")
                    .font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
            }

            Section("After the runtime restarts") {
                SecureField("New owner password", text: $newPassword)
                SecureField("Confirm new owner password", text: $confirmPassword)
                Button(isWorking ? "Working…" : "Create fresh owner security") {
                    Task { await createRestoredOwnerSecurity() }
                }
                .disabled(isWorking)
                if !recoveryCodes.isEmpty {
                    Text(recoveryCodes).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                    Toggle("I saved these new recovery codes somewhere separate from this iPhone", isOn: $recoverySaved)
                    Picker("Privacy default", selection: $privacyMode) {
                        Text("Local preferred").tag("local_preferred")
                        Text("Local only").tag("local_only")
                        Text("External allowed").tag("external_allowed")
                    }
                    Button(isWorking ? "Working…" : "Finish restored Vishnu") {
                        Task { await finishRestoredSetup() }
                    }
                    .disabled(isWorking || !recoverySaved)
                }
                Text("Old passwords, passkeys, sessions, and device bearer tokens are intentionally not restored. This iPhone receives a new independent device credential for the same restored Vishnu identity.")
                    .font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
            }

            Section("Status") { Text(status).font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary) }
        }
        .navigationTitle("Restore Vishnu")
        .navigationBarTitleDisplayMode(.inline)
        .fileImporter(isPresented: $chooseArchive, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            archiveURL = try? result.get().first
        }
        .fileImporter(isPresented: $chooseKey, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            keyURL = try? result.get().first
        }
    }

    private func secureBase() throws -> URL {
        let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: trimmed), url.scheme?.lowercased() == "https", url.host != nil else {
            throw CompanionError.badResponse("Portable recovery requires a valid HTTPS Vishnu runtime URL.")
        }
        return url
    }

    private func scheduleRestore() async {
        do {
            guard bootstrap.count >= 32, passphrase.count >= 12, let archiveURL, let keyURL else {
                throw CompanionError.badResponse("Enter the setup code and recovery passphrase, and choose both recovery files.")
            }
            let base = try secureBase()
            isWorking = true; status = "Preparing the encrypted recovery package…"
            let archiveCopy = try temporaryCopy(of: archiveURL, suffix: ".vdr")
            let keyCopy = try temporaryCopy(of: keyURL, suffix: ".vrk")
            defer { try? FileManager.default.removeItem(at: archiveCopy); try? FileManager.default.removeItem(at: keyCopy) }

            status = "Uploading the encrypted recovery package…"
            let first = try await upload(file: archiveCopy, to: base.appending(path: "iphone/api/native/recovery-package/archive"), bootstrap: bootstrap)
            guard let session = first["session_id"] as? String, !session.isEmpty else {
                throw CompanionError.badResponse("Vishnu did not return a recovery upload session.")
            }
            status = "Uploading the separate encrypted recovery key…"
            var keyComponents = URLComponents(url: base.appending(path: "iphone/api/native/recovery-package/key"), resolvingAgainstBaseURL: false)!
            keyComponents.queryItems = [URLQueryItem(name: "session_id", value: session)]
            _ = try await upload(file: keyCopy, to: keyComponents.url!, bootstrap: bootstrap)

            status = "Authenticating the recovery package…"
            let schedule: [String: Any] = ["session_id": session, "bootstrap_secret": bootstrap, "passphrase": passphrase]
            _ = try await postJSON(schedule, to: base.appending(path: "iphone/api/native/recovery-package/schedule"))
            try keychain.set(base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), for: "portable_restore_base")
            passphrase = ""
            status = "Recovery package authenticated and scheduled. Restart that fresh Vishnu runtime. After it comes back, return here and create fresh owner security."
        } catch {
            status = error.localizedDescription
        }
        isWorking = false
    }

    private func createRestoredOwnerSecurity() async {
        do {
            let base = try secureBase()
            guard bootstrap.count >= 32, newPassword.count >= 12, newPassword == confirmPassword else {
                throw CompanionError.badResponse("Enter the same runtime setup code and matching new owner password.")
            }
            let deviceID = try pendingSecret(key: "portable_restore_device", generator: { UUID().uuidString.lowercased() })
            let bearer = try pendingSecret(key: "portable_restore_bearer", generator: { Self.randomSecret(bytes: 48) })
            let claim = try pendingSecret(key: "portable_restore_claim", generator: { Self.randomSecret(bytes: 48) })
            isWorking = true; status = "Creating fresh owner security on the restored Vishnu…"
            let payload: [String: Any] = [
                "bootstrap_secret": bootstrap, "setup_claim": claim, "password": newPassword,
                "device_id": deviceID, "device_token": bearer,
                "device_name": UIDevice.current.name, "platform": "ios",
            ]
            let result = try await postJSON(payload, to: base.appending(path: "iphone/api/native/recovery-package/owner"))
            guard let codes = result["recovery_codes"] as? [String], !codes.isEmpty else {
                throw CompanionError.badResponse("Vishnu did not return new recovery codes.")
            }
            recoveryCodes = codes.joined(separator: "\n")
            try keychain.set(recoveryCodes, for: "portable_restore_codes")
            try keychain.set(base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), for: "portable_restore_base")
            newPassword = ""; confirmPassword = ""
            status = "Fresh security created. Save the new recovery codes before finishing."
        } catch {
            status = error.localizedDescription
        }
        isWorking = false
    }

    private func finishRestoredSetup() async {
        do {
            guard recoverySaved else { throw CompanionError.badResponse("Save the new recovery codes before finishing.") }
            let base = try secureBase()
            guard let device = keychain.get("portable_restore_device"),
                  let bearer = keychain.get("portable_restore_bearer"),
                  let claim = keychain.get("portable_restore_claim") else {
                throw CompanionError.badResponse("The restored setup session is missing. Create fresh owner security again.")
            }
            isWorking = true; status = "Finishing the restored Vishnu…"
            let payload: [String: Any] = [
                "setup_claim": claim, "device_id": device, "device_token": bearer,
                "recovery_saved": true, "privacy_mode": privacyMode, "model_choice": "configure_later",
            ]
            _ = try await postJSON(payload, to: base.appending(path: "iphone/api/first-run/native/complete"))
            try store.activateRecoveredDevice(base: base.absoluteString, deviceID: device, bearer: bearer)
            for key in ["portable_restore_device", "portable_restore_bearer", "portable_restore_claim", "portable_restore_codes", "portable_restore_base"] {
                keychain.remove(key)
            }
            recoveryCodes = ""
            status = "Restore complete. This iPhone is now a trusted owner device for the same Vishnu identity."
        } catch {
            status = error.localizedDescription
        }
        isWorking = false
    }

    private func upload(file: URL, to endpoint: URL, bootstrap: String) async throws -> [String: Any] {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(bootstrap, forHTTPHeaderField: "X-Vishnu-Bootstrap")
        let session = PinnedTransport.session(fingerprint: nil).0
        let (data, response) = try await session.upload(for: request, fromFile: file)
        return try decode(data: data, response: response)
    }

    private func postJSON(_ payload: [String: Any], to endpoint: URL) async throws -> [String: Any] {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let session = PinnedTransport.session(fingerprint: nil).0
        let (data, response) = try await session.data(for: request)
        return try decode(data: data, response: response)
    }

    private func decode(data: Data, response: URLResponse) throws -> [String: Any] {
        guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else {
            throw CompanionError.badResponse("Vishnu returned an invalid recovery response.")
        }
        guard (200..<300).contains(http.statusCode) else {
            let message: String
            switch http.statusCode {
            case 401: message = "The runtime setup code or recovery authorization was rejected."
            case 409: message = "This runtime is not in the required recovery stage."
            case 413: message = "The selected recovery file is larger than this recovery endpoint allows."
            case 422: message = "The recovery package, encrypted key, passphrase, or setup data could not be authenticated."
            default: message = "Vishnu recovery request failed (\(http.statusCode))."
            }
            throw CompanionError.badResponse(message)
        }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CompanionError.badResponse("Vishnu returned invalid recovery JSON.")
        }
        return json
    }

    private func temporaryCopy(of source: URL, suffix: String) throws -> URL {
        let accessing = source.startAccessingSecurityScopedResource()
        defer { if accessing { source.stopAccessingSecurityScopedResource() } }
        let target = FileManager.default.temporaryDirectory.appending(path: "vishnu-recovery-\(UUID().uuidString)\(suffix)")
        try FileManager.default.copyItem(at: source, to: target)
        return target
    }

    private func pendingSecret(key: String, generator: () -> String) throws -> String {
        if let existing = keychain.get(key), !existing.isEmpty { return existing }
        let value = generator(); try keychain.set(value, for: key); return value
    }

    private static func randomSecret(bytes: Int) -> String {
        var data = Data(count: bytes)
        let result = data.withUnsafeMutableBytes { buffer in
            SecRandomCopyBytes(kSecRandomDefault, bytes, buffer.baseAddress!)
        }
        precondition(result == errSecSuccess)
        return data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}