import AVFoundation
import SwiftUI
import UIKit

struct ConnectOnboardingView: View {
    @ObservedObject var store: CompanionStore
    @State private var showScanner = false
    @State private var showManual = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("V I S H N U")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .tracking(3)
                    Text("Connect to my Vishnu")
                        .font(.largeTitle.weight(.semibold))
                    Text("Scan the one-time QR shown by your primary Vishnu. This iPhone finds the computer automatically on the local network and verifies its TLS identity before sending any pairing secret. No IP address or port is required.")
                        .font(PersonalAITheme.Typography.body)
                        .foregroundStyle(.secondary)

                    Button {
                        showScanner = true
                    } label: {
                        Label("Scan Vishnu QR", systemImage: "qrcode.viewfinder")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button(showManual ? "Hide advanced fallback" : "Advanced manual fallback") {
                        withAnimation { showManual.toggle() }
                    }
                    .buttonStyle(.bordered)

                    if showManual {
                        VStack(alignment: .leading, spacing: 12) {
                            TextField("https://your-vishnu.example.com", text: $store.baseURL)
                                .textInputAutocapitalization(.never)
                                .keyboardType(.URL)
                                .textFieldStyle(.roundedBorder)
                            SecureField("Connection key", text: $store.pairingToken)
                                .textInputAutocapitalization(.never)
                                .textFieldStyle(.roundedBorder)
                            TextField("6-digit code", text: $store.pairingCode)
                                .keyboardType(.numberPad)
                                .textFieldStyle(.roundedBorder)
                            Toggle("Allow insecure localhost development", isOn: $store.allowInsecureDevelopment)
                            if store.allowInsecureDevelopment {
                                Text("Development only. Plain HTTP is accepted only for localhost/loopback addresses.")
                                    .font(.caption)
                                    .foregroundStyle(.orange)
                            }
                            Button("Connect this iPhone") {
                                Task { await pairManual() }
                            }
                            .buttonStyle(.borderedProminent)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(16)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Label(store.status, systemImage: store.connected ? "checkmark.circle.fill" : "lock.shield")
                            .font(.subheadline)
                        Text("The QR is one-use and expires automatically. Bonjour discovery exposes no owner password, model key, memory, or device bearer credential.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 8)
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