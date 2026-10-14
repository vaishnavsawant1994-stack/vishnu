import Security
import SwiftUI
import UIKit

struct RuntimeProvisioningView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var secret = ""
    @State private var message = "Cloud hosting is optional. Use this only when you do not already have a compatible Vishnu runtime."

    var body: some View {
        Form {
            Section("Create a secure Vishnu runtime") {
                Text("If this iPhone is your only device, you can create an owner-controlled HTTPS Vishnu runtime from your browser. The hosting provider does not become your Vishnu identity and never receives your owner password or recovery codes.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Section("One-time setup code") {
                Text(secret)
                    .font(.system(.footnote, design: .monospaced))
                    .textSelection(.enabled)
                Button("Copy setup code") { copySecret() }
                Button("Generate a new setup code") { regenerate() }
            }
            Section("Secure runtime") {
                Text("Vishnu creates the setup code on this iPhone. Paste it only into PERSONAL_AI_OWNER_BOOTSTRAP_SECRET during provider setup. It is never included in the deployment URL.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button {
                    openDeployment()
                } label: {
                    Label("Open secure runtime setup", systemImage: "server.rack")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section {
                Button("Back to Vishnu setup") { dismiss() }
            }
        }
        .navigationTitle("Vishnu Runtime")
        .navigationBarTitleDisplayMode(.inline)
        .task { loadOrCreateSecret() }
    }

    private func loadOrCreateSecret() {
        if let stored = KeychainStore.shared.get(Self.secretKey), stored.count >= 32 {
            secret = stored
            return
        }
        regenerate()
    }

    private func regenerate() {
        do {
            var bytes = [UInt8](repeating: 0, count: 48)
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
                throw ProvisioningError.randomFailure
            }
            let value = Data(bytes).base64EncodedString()
                .replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "=", with: "")
            try KeychainStore.shared.set(value, for: Self.secretKey)
            secret = value
            message = "A new setup code was generated. Use only this newest code when creating the runtime."
        } catch {
            message = "Vishnu could not generate a secure setup code. Try again."
        }
    }

    private func copySecret() {
        guard secret.count >= 32 else { return }
        UIPasteboard.general.string = secret
        message = "Setup code copied. Treat it like a temporary secret and paste it only into the Vishnu runtime deployment form."
    }

    private func openDeployment() {
        copySecret()
        var components = URLComponents()
        components.scheme = "https"
        components.host = "render.com"
        components.path = "/deploy"
        components.queryItems = [URLQueryItem(name: "repo", value: "https://github.com/vaishnavsawant1994-stack/vishnu")]
        guard let url = components.url else {
            message = "The provider setup link could not be created."
            return
        }
        UIApplication.shared.open(url)
        message = "Setup code copied. In Render, paste it into PERSONAL_AI_OWNER_BOOTSTRAP_SECRET. After deployment is live, copy its HTTPS address, return to Create my Vishnu, and use this same setup code."
    }

    private enum ProvisioningError: Error { case randomFailure }
    static let secretKey = "pending_runtime_bootstrap_secret"
}
