import AVFoundation
import Security
import SwiftUI
import UIKit

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
    @State private var recoveryCodes: [String] = []
    @State private var recoverySaved = false
    @State private var privacyMode = "local_only"
    @State private var modelProvider = "skip"
    @State private var modelName = ""
    @State private var providerKey = ""
    @State private var setupWorking = false
    @State private var setupMessage = ""

    private enum StartChoice: Equatable { case create, join, restore }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("V I S H N U")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .tracking(3)
                    if selection == nil {
                        Text("Welcome to Vishnu")
                            .font(.largeTitle.weight(.semibold))
                        Text("Your Vishnu belongs to you. Create a new identity, connect a device, or recover access.")
                            .font(PersonalAITheme.Typography.body)
                            .foregroundStyle(.secondary)
                        Button { selection = .create } label: {
                            Label("Create my Vishnu", systemImage: "person.crop.circle.badge.plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        Button { selection = .join } label: {
                            Label("I already have Vishnu", systemImage: "qrcode.viewfinder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered).controlSize(.large)
                        Button { selection = .restore } label: {
                            Label("Restore Vishnu", systemImage: "arrow.counterclockwise.icloud")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered).controlSize(.large)
                    } else {
                        Button("‹ Back") { selection = nil; setupMessage = "" }
                            .buttonStyle(.plain)
                        if selection == .create {
                            createForm
                        } else if selection == .restore {
                            restoreForm
                        } else {
                            joinForm
                        }
                    }
                }
                .padding(24)
                .frame(maxWidth: 640, alignment: .leading)
            }
            .background(PersonalAITheme.ColorToken.background)
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
        .onAppear {
            if let saved = KeychainStore.shared.get("pending_first_recovery_codes"),
               let data = saved.data(using: .utf8),
               let codes = try? JSONDecoder().decode([String].self, from: data), !codes.isEmpty {
                recoveryCodes = codes
                selection = .create
                setupMessage = "Resume setup by confirming that you saved the recovery codes."
            }
        }
    }

    @ViewBuilder
    private var createForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Create my Vishnu").font(.largeTitle.weight(.semibold))
            Text("This iPhone will be your first trusted device. The secure runtime holds the canonical identity and data; this app stores only this device's credential in Keychain.")
                .font(.subheadline).foregroundStyle(.secondary)
            TextField("Secure Vishnu runtime URL (https://…)", text: $store.baseURL)
                .textInputAutocapitalization(.never).keyboardType(.URL).textFieldStyle(.roundedBorder)
            SecureField("One-time runtime setup code", text: $bootstrapCode)
                .textInputAutocapitalization(.never).textFieldStyle(.roundedBorder)
            TextField("First name", text: $firstName).textFieldStyle(.roundedBorder)
                .textContentType(.givenName)
            TextField("Last name (optional)", text: $lastName).textFieldStyle(.roundedBorder)
                .textContentType(.familyName)
            TextField("Display name (optional)", text: $displayName).textFieldStyle(.roundedBorder)
                .textContentType(.nickname)
            SecureField("Owner password (12 characters minimum)", text: $ownerPassword)
                .textFieldStyle(.roundedBorder).textContentType(.newPassword)
            SecureField("Confirm owner password", text: $confirmPassword)
                .textFieldStyle(.roundedBorder).textContentType(.newPassword)
            Text("Native passkey registration is not available in this build. This flow uses the owner password and recovery codes; add a passkey later from Vishnu Security.")
                .font(.caption).foregroundStyle(.secondary)

            if recoveryCodes.isEmpty {
                Button {
                    Task { await beginNativeCreation() }
                } label: {
                    if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Create Vishnu on this iPhone").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.borderedProminent).disabled(setupWorking)
            } else {
                Text("Save these one-time recovery codes somewhere outside this iPhone. Each code works once.")
                    .font(.subheadline.weight(.medium))
                Text(recoveryCodes.joined(separator: "\n"))
                    .font(.system(.body, design: .monospaced)).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding()
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                Toggle("I saved these recovery codes", isOn: $recoverySaved)
                Picker("Data privacy", selection: $privacyMode) {
                    Text("Local only").tag("local_only")
                    Text("Local preferred").tag("local_preferred")
                    Text("External providers allowed").tag("external_allowed")
                }
                Picker("AI setup", selection: $modelProvider) {
                    Text("Configure later").tag("skip")
                    Text("Use a local model").tag("local")
                    Text("OpenAI").tag("openai")
                    Text("Gemini").tag("gemini")
                    Text("OpenRouter").tag("openrouter")
                    Text("DeepSeek").tag("deepseek")
                    Text("xAI").tag("xai")
                    Text("Groq").tag("groq")
                    Text("Cerebras").tag("cerebras")
                    Text("Mistral").tag("mistral")
                    Text("Custom provider").tag("custom")
                }
                .pickerStyle(.menu)
                if !["skip", "local"].contains(modelProvider) {
                    TextField("Model name", text: $modelName)
                        .textInputAutocapitalization(.never).textFieldStyle(.roundedBorder)
                    SecureField("Provider API key", text: $providerKey)
                        .textFieldStyle(.roundedBorder)
                }
                Button {
                    Task { await finishNativeCreation() }
                } label: {
                    if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Finish setup").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.borderedProminent).disabled(setupWorking || !recoverySaved)
            }
            if !setupMessage.isEmpty {
                Text(setupMessage).font(.footnote).foregroundStyle(.secondary).accessibilityAddTraits(.updatesFrequently)
            }
        }
    }

    @ViewBuilder
    private var restoreForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Restore Vishnu").font(.largeTitle.weight(.semibold))
            Text("Use a recovery code to trust this iPhone with the runtime that owns your Vishnu. If that runtime was lost, restore its owner-controlled backup first. Data remains under its existing data policy.")
                .font(.subheadline).foregroundStyle(.secondary)
            TextField("Secure Vishnu runtime URL (https://…)", text: $store.baseURL)
                .textInputAutocapitalization(.never).keyboardType(.URL).textFieldStyle(.roundedBorder)
            SecureField("One-time recovery code", text: $recoveryCode)
                .textInputAutocapitalization(.characters).textFieldStyle(.roundedBorder)
            Button {
                Task { await restoreNativeDevice() }
            } label: {
                if setupWorking { ProgressView().frame(maxWidth: .infinity) }
                else { Text("Restore Vishnu on this iPhone").frame(maxWidth: .infinity) }
            }
            .buttonStyle(.borderedProminent).disabled(setupWorking)
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
            .buttonStyle(.borderedProminent).controlSize(.large)
            Button(showManual ? "Hide advanced fallback" : "Advanced manual fallback") {
                withAnimation { showManual.toggle() }
            }
            .buttonStyle(.bordered)
            if showManual {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("https://your-vishnu.example.com", text: $store.baseURL)
                        .textInputAutocapitalization(.never).keyboardType(.URL).textFieldStyle(.roundedBorder)
                    SecureField("Connection key", text: $store.pairingToken)
                        .textInputAutocapitalization(.never).textFieldStyle(.roundedBorder)
                    TextField("6-digit code", text: $store.pairingCode)
                        .keyboardType(.numberPad).textFieldStyle(.roundedBorder)
                    Toggle("Allow insecure localhost development", isOn: $store.allowInsecureDevelopment)
                    Button("Connect this iPhone") { Task { await pairManual() } }
                        .buttonStyle(.borderedProminent)
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
                "device_name": UIDevice.current.name,
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
                "recovery_saved": true, "privacy_mode": privacyMode,
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
