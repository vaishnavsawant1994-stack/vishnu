import AVFoundation
import Security
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct ConnectOnboardingView: View {
    @ObservedObject var store: CompanionStore
    @State private var showScanner = false
    @State private var showManual = false
    @State private var selection: StartChoice?
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var displayName = ""
    @State private var bootstrapCode = ""
    @State private var ownerPassword = ""
    @State private var confirmPassword = ""
    @State private var recoveryCode = ""
    @State private var deviceName = UIDevice.current.name
    @State private var recoveryCodes: [String] = []
    @State private var recoverySaved = false
    @State private var showRecoveryExport = false
    @State private var privacyMode = "local_only"
    @State private var dataPolicy = "device_only"
    @State private var genesisStep = 1
    @State private var modelProvider = "skip"
    @State private var modelName = ""
    @State private var providerKey = ""
    @State private var setupWorking = false
    @State private var setupMessage = ""

    private enum StartChoice: Equatable { case create, join, restore }

    var body: some View {
        NavigationStack {
            ZStack {
                VishnuGenesisBackground()
                ScrollView {
                VStack(alignment: .center, spacing: 18) {
                    VishnuGenesisWordmark()
                    if selection == .create && genesisStep > 1 {
                        Text("Create Vishnu · Step \(genesisStep) of 4").font(.caption).foregroundStyle(PersonalAITheme.ColorToken.secondaryText)
                        HStack(spacing: 6) { ForEach(1...4, id: \.self) { step in Circle().fill(step <= genesisStep ? PersonalAITheme.ColorToken.brightAccent : PersonalAITheme.ColorToken.mutedText).frame(width: 7, height: 7) } }
                    }
                    VishnuGenesisCore(state: selection == nil ? "initializing" : "Genesis step \(genesisStep)", size: selection == nil ? 260 : 175)
                    if selection == nil {
                        Text("Welcome to Vishnu")
                            .font(.largeTitle.weight(.light))
                        Text("Your personal intelligence. Your data. Your world.")
                            .font(PersonalAITheme.Typography.body)
                            .foregroundStyle(PersonalAITheme.ColorToken.secondaryText)
                        Button { selection = .create; genesisStep = recoveryCodes.isEmpty ? 2 : 4 } label: {
                            Label("Create my Vishnu", systemImage: "person.crop.circle.badge.plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(VishnuGenesisButtonStyle(primary: true))
                        Button { selection = .join } label: {
                            Label("I already have Vishnu", systemImage: "qrcode.viewfinder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(VishnuGenesisButtonStyle())
                        Button { selection = .restore } label: {
                            Label("Restore Vishnu", systemImage: "arrow.counterclockwise.icloud")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(VishnuGenesisButtonStyle())
                    } else {
                        Button("‹ Back") { if selection == .create && genesisStep > 2 && recoveryCodes.isEmpty { genesisStep -= 1 } else { selection = nil }; setupMessage = "" }
                            .buttonStyle(VishnuGenesisButtonStyle())
                        if selection == .create {
                            createForm
                        } else if selection == .restore {
                            restoreForm
                        } else {
                            joinForm
                        }
                    }
                    Text("Privacy     |     Accessibility")
                        .font(PersonalAITheme.Typography.metadata)
                        .foregroundStyle(PersonalAITheme.ColorToken.mutedText)
                        .padding(.top, 12)
                }
                .padding(24)
                .frame(maxWidth: 640, alignment: .leading)
                }
            }
            .tint(PersonalAITheme.ColorToken.accent)
            .sheet(isPresented: $showScanner) {
                NavigationStack {
                    QRScannerView { raw in
                        showScanner = false
                        acceptScannedPayload(raw)
                    }
                    .ignoresSafeArea(edges: .bottom)
                    .navigationTitle("Scan Vishnu QR")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Cancel") { showScanner = false }
                        }
                    }
                }
            }
        }
        .preferredColorScheme(.dark)
        .fileExporter(
            isPresented: $showRecoveryExport,
            document: VishnuRecoveryCodesDocument(text: recoveryCodes.joined(separator: "\n")),
            contentType: .plainText,
            defaultFilename: "Vishnu-Recovery-Codes"
        ) { result in
            switch result {
            case .success:
                setupMessage = "Codes exported. Move the file to a private safe location; Files providers may sync it."
            case .failure:
                setupMessage = "Could not export recovery codes. Please choose another secure destination."
            }
        }
        .onAppear {
            if let saved = KeychainStore.shared.get("pending_first_recovery_codes"),
               let data = saved.data(using: .utf8),
               let codes = try? JSONDecoder().decode([String].self, from: data), !codes.isEmpty {
                recoveryCodes = codes
                selection = .create
                genesisStep = 4
                setupMessage = "Resume setup by confirming that you saved the recovery codes."
            }
        }
    }

    @ViewBuilder
    private var createForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            if genesisStep == 2 {
                genesisHeading("What should Vishnu call you?", "Tell Vishnu your name. You can personalize everything else later.")
                TextField("First name", text: $firstName)
                    .textContentType(.givenName).vishnuGenesisInput()
                TextField("Last name (optional)", text: $lastName)
                    .textContentType(.familyName).vishnuGenesisInput()
                TextField("Display name (optional)", text: $displayName)
                    .textContentType(.nickname).vishnuGenesisInput()
                genesisContinue("Continue") {
                    guard !firstName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                        setupMessage = "Enter a name so Vishnu knows what to call you."
                        return
                    }
                    genesisStep = 3
                }
            } else if genesisStep == 3 {
                genesisHeading("Secure Your Vishnu", "Protect your Vishnu with a password and recognize your first device.")
                TextField("Secure Vishnu runtime URL (https://…)", text: $store.baseURL)
                    .textInputAutocapitalization(.never).keyboardType(.URL).vishnuGenesisInput()
                SecureField("One-time runtime setup code", text: $bootstrapCode)
                    .vishnuGenesisInput()
                SecureField("Owner password (12 characters minimum)", text: $ownerPassword)
                    .textContentType(.newPassword).vishnuGenesisInput()
                SecureField("Confirm owner password", text: $confirmPassword)
                    .textContentType(.newPassword).vishnuGenesisInput()
                TextField("Name this device", text: $deviceName)
                    .vishnuGenesisInput()
                Text("Your password protects this Vishnu. Passkeys or Face ID / Touch ID can be configured later, when supported by this runtime.")
                    .font(.footnote).foregroundStyle(PersonalAITheme.ColorToken.secondaryText)
                Button {
                    Task { await beginNativeCreation() }
                } label: {
                    if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Secure Vishnu →").frame(maxWidth: .infinity) }
                }
                .buttonStyle(VishnuGenesisButtonStyle(primary: true))
                .disabled(setupWorking)
            } else {
                genesisHeading("Save Your Recovery Codes", "These one-time codes regain owner access. They are not a data backup.")
                Text(recoveryCodes.isEmpty ? "Awaiting the authorized recovery codes…" : recoveryCodes.joined(separator: "\n"))
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .vishnuGenesisCard()
                    .accessibilityLabel("One-time owner recovery codes")
                Button("Save Recovery Codes as File") {
                    guard recoveryCodes.count >= 4 else {
                        setupMessage = "Recovery codes are not available. Retry secure setup."
                        return
                    }
                    showRecoveryExport = true
                }
                .buttonStyle(VishnuGenesisButtonStyle())
                .disabled(recoveryCodes.isEmpty)
                Button("Copy all recovery codes") {
                    UIPasteboard.general.string = recoveryCodes.joined(separator: "\n")
                    setupMessage = "Codes copied. Save them securely away from this phone, then clear your clipboard."
                }
                .buttonStyle(VishnuGenesisButtonStyle())
                .disabled(recoveryCodes.isEmpty)
                Toggle("I have saved these codes privately", isOn: $recoverySaved)
                VStack(alignment: .leading, spacing: 8) {
                    Text("Quick review").font(.headline)
                    Text("Owner: \(displayName.isEmpty ? firstName : displayName)")
                    Text("Sign-in: owner password")
                    Text("First device: \(deviceName)")
                    Text("Data: local to the selected Vishnu runtime (no automatic sync)")
                    Text("AI providers: configure later in Settings")
                    Text("Privacy: local-only by default; ask before important actions")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .vishnuGenesisCard()
                Button {
                    Task { await finishNativeCreation() }
                } label: {
                    if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Create My Vishnu →").frame(maxWidth: .infinity) }
                }
                .buttonStyle(VishnuGenesisButtonStyle(primary: true))
                .disabled(setupWorking || !recoverySaved || recoveryCodes.isEmpty)
            }
            if !setupMessage.isEmpty {
                Text(setupMessage).font(.footnote)
                    .foregroundStyle(PersonalAITheme.ColorToken.secondaryText)
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
    }

    private func genesisHeading(_ title: String, _ subtitle: String) -> some View {
        VStack(alignment: .center, spacing: 7) { Text(title).font(.largeTitle.weight(.light)).multilineTextAlignment(.center); Text(subtitle).foregroundStyle(PersonalAITheme.ColorToken.secondaryText).multilineTextAlignment(.center) }.frame(maxWidth: .infinity)
    }

    private func genesisContinue(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Text("\(label) →").frame(maxWidth: .infinity) }.buttonStyle(VishnuGenesisButtonStyle(primary: true))
    }

    @ViewBuilder
    private var restoreForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Restore Vishnu").font(.largeTitle.weight(.semibold))
            Text("Use a recovery code to trust this iPhone with the runtime that owns your Vishnu. If that runtime was lost, restore its owner-controlled backup first. Data remains under its existing data policy.")
                .font(.subheadline).foregroundStyle(.secondary)
            TextField("Secure Vishnu runtime URL (https://…)", text: $store.baseURL)
                .textInputAutocapitalization(.never).keyboardType(.URL).vishnuGenesisInput()
            SecureField("One-time recovery code", text: $recoveryCode)
                .textInputAutocapitalization(.characters).vishnuGenesisInput()
            Button {
                Task { await restoreNativeDevice() }
            } label: {
                if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                else { Text("Recover owner access on this iPhone").frame(maxWidth: .infinity) }
            }
            .buttonStyle(VishnuGenesisButtonStyle(primary: true)).disabled(setupWorking)
            if !setupMessage.isEmpty {
                Text(setupMessage).font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var joinForm: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("I already have Vishnu").font(.largeTitle.weight(.semibold))
            Text("Scan the one-time QR shown by your existing Vishnu. This iPhone verifies its TLS identity before sending any pairing secret.")
                .font(PersonalAITheme.Typography.body).foregroundStyle(.secondary)
            Button { showScanner = true } label: {
                Label("Scan Vishnu QR", systemImage: "qrcode.viewfinder").frame(maxWidth: .infinity)
            }
            .buttonStyle(VishnuGenesisButtonStyle(primary: true))
            Button(showManual ? "Hide advanced fallback" : "Advanced manual fallback") {
                withAnimation { showManual.toggle() }
            }
            .buttonStyle(VishnuGenesisButtonStyle())
            if showManual {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("https://your-vishnu.example.com", text: $store.baseURL)
                        .textInputAutocapitalization(.never).keyboardType(.URL).vishnuGenesisInput()
                    SecureField("Connection key", text: $store.pairingToken)
                        .textInputAutocapitalization(.never).vishnuGenesisInput()
                    TextField("6-digit code", text: $store.pairingCode)
                        .keyboardType(.numberPad).vishnuGenesisInput()
                    Toggle("Allow insecure localhost development", isOn: $store.allowInsecureDevelopment)
                    Button("Connect this iPhone") { Task { await pairManual() } }
                        .buttonStyle(VishnuGenesisButtonStyle(primary: true))
                }
                .padding(16).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
            }
            VStack(alignment: .leading, spacing: 8) {
                Label(store.status, systemImage: store.connected ? "checkmark.circle.fill" : "lock.shield")
                    .font(.subheadline)
                Text("Pairing offers expire and can be used once. Device credentials stay in Keychain.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @MainActor
    private func beginNativeCreation() async {
        do {
            let origin = try PairingPayload.normalizeOrigin(store.baseURL, allowLocalHTTP: false)
            guard !firstName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw NativeSetupError.message("Enter your first name.")
            }
            guard !deviceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw NativeSetupError.message("Name this device before continuing.")
            }
            guard bootstrapCode.count >= 32 else {
                throw NativeSetupError.message("Enter the one-time setup code provided for this runtime.")
            }
            guard ownerPassword.count >= 12 else {
                throw NativeSetupError.message("Use an owner password with at least 12 characters.")
            }
            guard ownerPassword == confirmPassword else {
                throw NativeSetupError.message("The passwords did not match.")
            }
            let keychain = KeychainStore.shared
            let claim: String
            if let savedClaim = keychain.get("pending_setup_claim") { claim = savedClaim }
            else { claim = try secureRandomText() }
            let deviceID = keychain.get("pending_first_device") ?? UUID().uuidString.lowercased()
            let token: String
            if let savedToken = keychain.get("pending_first_bearer") { token = savedToken }
            else { token = try secureRandomText() }
            try keychain.set(claim, for: "pending_setup_claim")
            try keychain.set(deviceID, for: "pending_first_device")
            try keychain.set(token, for: "pending_first_bearer")
            try keychain.set(origin, for: "pending_first_base")
            setupWorking = true
            setupMessage = "Creating your owner identity and first trusted device…"
            let result = try await postNativeJSON(path: "/iphone/api/first-run/native/create", body: [
                "bootstrap_secret": bootstrapCode,
                "setup_claim": claim,
                "first_name": firstName.trimmingCharacters(in: .whitespacesAndNewlines),
                "last_name": lastName.trimmingCharacters(in: .whitespacesAndNewlines),
                "display_name": displayName.trimmingCharacters(in: .whitespacesAndNewlines),
                "password": ownerPassword,
                "device_id": deviceID,
                "device_token": token,
                "device_name": deviceName.trimmingCharacters(in: .whitespacesAndNewlines),
                "platform": "ios",
            ])
            if result["status"] as? String == "ready" {
                try activatePendingFirstDevice()
                KeychainStore.shared.remove("pending_first_recovery_codes")
                setupMessage = "Vishnu is ready on this iPhone."
                setupWorking = false
                return
            }
            guard let codes = result["recovery_codes"] as? [String], codes.count >= 4 else {
                throw NativeSetupError.message("The runtime did not return recovery codes. Retry setup to create a fresh set.")
            }
            recoveryCodes = codes
            genesisStep = 4
            if let data = try? JSONEncoder().encode(codes),
               let encoded = String(data: data, encoding: .utf8) {
                try KeychainStore.shared.set(encoded, for: "pending_first_recovery_codes")
            }
            recoverySaved = false
            bootstrapCode = ""
            ownerPassword = ""
            confirmPassword = ""
            setupMessage = "Save your recovery codes before continuing."
        } catch {
            setupMessage = error.localizedDescription
        }
        setupWorking = false
    }

    @MainActor
    private func finishNativeCreation() async {
        guard recoverySaved else { setupMessage = "Confirm that you saved the recovery codes."; return }
        if !["skip", "local"].contains(modelProvider) {
            guard !modelName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                setupMessage = "Enter the model name for the selected provider."; return
            }
            guard providerKey.count >= 16 else {
                setupMessage = "Enter the provider API key, or choose Configure later."; return
            }
        }
        guard let claim = KeychainStore.shared.get("pending_setup_claim"),
              let deviceID = KeychainStore.shared.get("pending_first_device"),
              let token = KeychainStore.shared.get("pending_first_bearer") else {
            setupMessage = "The secure setup session is unavailable. Start the creation ceremony again."
            return
        }
        setupWorking = true
        setupMessage = "Saving your AI choice and verifying setup…"
        do {
            let modelBody: [String: Any] = [
                "setup_claim": claim, "device_id": deviceID, "device_token": token,
                "provider_id": modelProvider,
                "model": modelName.trimmingCharacters(in: .whitespacesAndNewlines),
                "api_key": providerKey,
            ]
            let modelResult = try await postNativeJSON(path: "/iphone/api/first-run/native/model", body: modelBody)
            guard modelResult["ok"] as? Bool == true else {
                throw NativeSetupError.message("Vishnu did not confirm the AI setup choice.")
            }
            let result = try await postNativeJSON(path: "/iphone/api/first-run/native/complete", body: [
                "setup_claim": claim, "device_id": deviceID, "device_token": token,
                "recovery_saved": true, "privacy_mode": privacyMode, "data_policy": dataPolicy,
                "model_choice": modelProvider == "skip" ? "configure_later" : "configured",
            ])
            guard result["status"] as? String == "ready" else {
                throw NativeSetupError.message("The runtime did not confirm setup completion. Retry safely.")
            }
            try activatePendingFirstDevice()
            KeychainStore.shared.remove("pending_first_recovery_codes")
            providerKey = ""
            setupMessage = "Vishnu is ready on this iPhone."
        } catch {
            setupMessage = error.localizedDescription
        }
        setupWorking = false
    }

    @MainActor
    private func restoreNativeDevice() async {
        do {
            let origin = try PairingPayload.normalizeOrigin(store.baseURL, allowLocalHTTP: false)
            guard recoveryCode.trimmingCharacters(in: .whitespacesAndNewlines).count >= 8 else {
                throw NativeSetupError.message("Enter one of your saved recovery codes.")
            }
            let keychain = KeychainStore.shared
            let deviceID = keychain.get("pending_restore_device") ?? UUID().uuidString.lowercased()
            let token: String
            if let savedToken = keychain.get("pending_restore_bearer") { token = savedToken }
            else { token = try secureRandomText() }
            try keychain.set(deviceID, for: "pending_restore_device")
            try keychain.set(token, for: "pending_restore_bearer")
            try keychain.set(origin, for: "pending_restore_base")
            setupWorking = true
            setupMessage = "Verifying recovery and trusting this iPhone…"
            let result = try await postNativeJSON(path: "/iphone/api/access/native/recovery", body: [
                "recovery_code": recoveryCode.trimmingCharacters(in: .whitespacesAndNewlines),
                "device_id": deviceID, "device_token": token,
                "device_name": UIDevice.current.name, "platform": "ios",
            ])
            guard result["status"] as? String == "ready" else {
                throw NativeSetupError.message("The runtime did not confirm device recovery. Retry safely.")
            }
            try store.activateRecoveredDevice(base: origin, deviceID: deviceID, bearer: token)
            keychain.remove("pending_restore_device")
            keychain.remove("pending_restore_bearer")
            keychain.remove("pending_restore_base")
            recoveryCode = ""
            setupMessage = "Vishnu is restored on this iPhone."
        } catch {
            setupMessage = error.localizedDescription
        }
        setupWorking = false
    }

    private func activatePendingFirstDevice() throws {
        let keychain = KeychainStore.shared
        guard let base = keychain.get("pending_first_base"),
              let deviceID = keychain.get("pending_first_device"),
              let token = keychain.get("pending_first_bearer") else {
            throw NativeSetupError.message("The secure first-device credential is missing.")
        }
        try store.activateRecoveredDevice(base: base, deviceID: deviceID, bearer: token)
        ["pending_setup_claim", "pending_first_device", "pending_first_bearer", "pending_first_base"]
            .forEach { keychain.remove($0) }
    }

    private func postNativeJSON(path: String, body: [String: Any]) async throws -> [String: Any] {
        let origin = try PairingPayload.normalizeOrigin(store.baseURL, allowLocalHTTP: false)
        guard let url = URL(string: origin + path) else { throw NativeSetupError.message("The secure runtime URL is invalid.") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let delegate = NoRedirectSessionDelegate()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieStorage = nil
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576 else { throw NativeSetupError.message("The Vishnu runtime returned an oversized response.") }
        guard let http = response as? HTTPURLResponse else { throw NativeSetupError.message("The Vishnu runtime response was invalid.") }
        guard (200..<300).contains(http.statusCode) else {
            throw NativeSetupError.message(http.statusCode == 409
                ? "Vishnu is initialized or another setup is already in progress. Connect to the existing Vishnu."
                : "Vishnu could not complete the secure setup (\(http.statusCode)). Check the runtime and retry.")
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NativeSetupError.message("The Vishnu runtime returned an invalid setup response.")
        }
        return object
    }

    private func secureRandomText() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        guard status == errSecSuccess else { throw NativeSetupError.message("Secure random generation failed. Try again.") }
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private enum NativeSetupError: LocalizedError {
        case message(String)
        var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
    }

    @MainActor
    private func pairManual() async {
        do {
            store.baseURL = try PairingPayload.normalizeOrigin(store.baseURL, allowLocalHTTP: store.allowInsecureDevelopment)
            let token = store.pairingToken.trimmingCharacters(in: .whitespacesAndNewlines)
            let code = store.pairingCode.trimmingCharacters(in: .whitespacesAndNewlines)
            guard (16...256).contains(token.count) else { throw PairingPayloadError.invalidToken }
            guard code.count == 6, code.allSatisfy(\.isNumber) else { throw PairingPayloadError.invalidCode }
            store.pairingToken = token
            store.pairingCode = code
            store.pairingTLSFingerprint = ""
            store.pairingServiceID = ""
            await store.pair()
        } catch {
            store.status = (error as? LocalizedError)?.errorDescription ?? "The connection details are invalid."
        }
    }

    private func acceptScannedPayload(_ raw: String) {
        do {
            let payload = try PairingPayload.parse(raw, allowLocalHTTP: store.allowInsecureDevelopment)
            store.pairingToken = payload.token
            store.pairingCode = payload.code
            if payload.zeroConfig, let service = payload.serviceID, let fingerprint = payload.certSHA256 {
                store.pairingTLSFingerprint = fingerprint
                store.pairingServiceID = service
                store.status = "Finding your Vishnu automatically…"
                VishnuBonjourDiscovery.discover(serviceID: service) { result in
                    Task { @MainActor in
                        switch result {
                        case .success(let origin):
                            store.baseURL = origin
                            store.status = "Vishnu discovered. Verifying its secure identity…"
                            await store.pair()
                        case .failure:
                            if let fallback = payload.fallbackURL {
                                store.baseURL = fallback
                                store.pairingTLSFingerprint = ""
                                store.pairingServiceID = ""
                                store.status = "Local discovery unavailable. Trying the configured secure Vishnu endpoint…"
                                await store.pair()
                            } else {
                                store.status = "Could not find this Vishnu on the local network. Make sure both devices are on the same Wi‑Fi, then scan a new QR."
                            }
                        }
                    }
                }
            } else if let base = payload.baseURL {
                store.baseURL = base
                store.pairingTLSFingerprint = ""
                store.pairingServiceID = ""
                store.status = "Vishnu found. Connecting this iPhone…"
                Task { await store.pair() }
            } else {
                store.status = "This Vishnu connection offer is incomplete."
            }
        } catch {
            store.status = (error as? LocalizedError)?.errorDescription ?? "That QR code is not a valid Vishnu connection offer."
        }
    }
}

struct QRScannerView: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeUIViewController(context: Context) -> QRScannerViewController {
        let controller = QRScannerViewController()
        controller.onCode = onCode
        return controller
    }

    func updateUIViewController(_ uiViewController: QRScannerViewController, context: Context) {}
}

final class QRScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onCode: ((String) -> Void)?
    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var configured = false
    private let message = UILabel()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        message.textColor = .white
        message.textAlignment = .center
        message.numberOfLines = 0
        message.text = "Point the camera at the one-time QR shown by Vishnu."
        message.backgroundColor = UIColor.black.withAlphaComponent(0.65)
        message.layer.cornerRadius = 12
        message.layer.masksToBounds = true
        message.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(message)
        NSLayoutConstraint.activate([
            message.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            message.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            message.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -24),
            message.heightAnchor.constraint(greaterThanOrEqualToConstant: 56),
        ])
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        prepareCamera()
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        session.stopRunning()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    private func prepareCamera() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configureAndStart()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    if granted { self?.configureAndStart() }
                    else { self?.message.text = "Camera access is required to scan the Vishnu QR. You can use manual connection instead." }
                }
            }
        default:
            message.text = "Camera access is unavailable. Use manual connection instead or enable Camera for Vishnu in Settings."
        }
    }

    private func configureAndStart() {
        if !configured {
            guard let camera = AVCaptureDevice.default(for: .video),
                  let input = try? AVCaptureDeviceInput(device: camera),
                  session.canAddInput(input) else {
                message.text = "The camera could not be opened. Use manual connection instead."
                return
            }
            session.addInput(input)
            let output = AVCaptureMetadataOutput()
            guard session.canAddOutput(output) else {
                message.text = "QR scanning is unavailable on this device. Use manual connection instead."
                return
            }
            session.addOutput(output)
            output.setMetadataObjectsDelegate(self, queue: .main)
            output.metadataObjectTypes = [.qr]
            let preview = AVCaptureVideoPreviewLayer(session: session)
            preview.videoGravity = .resizeAspectFill
            preview.frame = view.bounds
            view.layer.insertSublayer(preview, at: 0)
            previewLayer = preview
            configured = true
        }
        if !session.isRunning {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in self?.session.startRunning() }
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              object.type == .qr, let value = object.stringValue else { return }
        session.stopRunning()
        onCode?(value)
    }
}


/// Owner-controlled export of one-time recovery codes. Never written to shared
/// caches or uploaded by the companion. Warn that third-party Files providers
/// may synchronize user-selected storage automatically.
struct VishnuRecoveryCodesDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.plainText] }
    var text: String

    init(text: String) {
        self.text = text
    }

    init(configuration: ReadConfiguration) throws {
        let data = configuration.file.regularFileContents ?? Data()
        text = String(data: data, encoding: .utf8) ?? ""
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: Data(text.utf8))
    }
}
