import Foundation
import SwiftUI
import UIKit

@MainActor
final class NativeForgeV3Store: ObservableObject {
    @Published var status = "Capability Forge V3 is not configured."
    @Published var result = ""
    @Published var capabilityID = ""
    @Published var version = ""
    @Published var providerID = ""
    @Published var targetStage = "limited"
    @Published var approvalID = ""
    @Published var buildID = ""
    @Published var toolName = ""
    @Published var parameters = "{}"
    @Published var ownerPassword = ""

    private let keychain = KeychainStore.shared
    private var host: String {
        (Bundle.main.object(forInfoDictionaryKey: "VishnuCapabilityHost") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private var token: String? { keychain.get("native.capabilities.token") }
    private var expiry: Date {
        Date(timeIntervalSince1970: Double(keychain.get("native.capabilities.expiry") ?? "0") ?? 0)
    }

    func readiness() async { await call("GET", "/owner/forge/v3/readiness") }
    func providers() async { await call("GET", "/owner/forge/v3/oauth/providers") }
    func oauthStatus() async {
        guard let cap = required(capabilityID, "Capability ID") else { return }
        await call("GET", "/owner/forge/v3/oauth/\(path(cap))/status")
    }
    func startOAuth() async {
        guard let cap = required(capabilityID, "Capability ID"), let provider = required(providerID, "Provider ID") else { return }
        await freshOwner {
            if let response = await self.call("POST", "/owner/forge/v3/oauth/\(self.path(cap))/\(self.path(provider))/start", [:]) {
                let raw = (response["url"] as? String) ?? (response["authorization_url"] as? String)
                if let raw, let url = URL(string: raw), url.scheme == "https" {
                    await UIApplication.shared.open(url)
                }
            }
        }
    }
    func revokeOAuth() async {
        guard let cap = required(capabilityID, "Capability ID"), let provider = required(providerID, "Provider ID") else { return }
        await freshOwner { _ = await self.call("POST", "/owner/forge/v3/oauth/\(self.path(cap))/\(self.path(provider))/revoke", [:]) }
    }
    func rollout() async {
        guard let cap = required(capabilityID, "Capability ID"), let ver = required(version, "Version") else { return }
        await call("GET", "/owner/forge/v3/rollout/\(path(cap))/\(path(ver))")
    }
    func canary() async {
        guard let cap = required(capabilityID, "Capability ID"), let ver = required(version, "Version"), let build = required(buildID, "Build ID"), let params = parsedParameters() else { return }
        await freshOwner { _ = await self.call("POST", "/owner/forge/v3/rollout/\(self.path(cap))/\(self.path(ver))/canary", ["build_id": build, "parameters": params]) }
    }
    func requestPromotion() async {
        guard let cap = required(capabilityID, "Capability ID"), let ver = required(version, "Version"), let target = required(targetStage, "Target stage") else { return }
        await freshOwner {
            if let response = await self.call("POST", "/owner/forge/v3/rollout/\(self.path(cap))/\(self.path(ver))/promotion", ["target_stage": target]),
               let ticket = response["approval_id"] as? String { self.approvalID = ticket }
        }
    }
    func commitPromotion() async {
        guard let cap = required(capabilityID, "Capability ID"), let ver = required(version, "Version"), let target = required(targetStage, "Target stage"), let ticket = required(approvalID, "Approved ticket ID") else { return }
        await freshOwner { _ = await self.call("POST", "/owner/forge/v3/rollout/\(self.path(cap))/\(self.path(ver))/promotion", ["target_stage": target, "ticket_id": ticket]) }
    }
    func health() async {
        guard let cap = required(capabilityID, "Capability ID"), let ver = required(version, "Version") else { return }
        await freshOwner { _ = await self.call("POST", "/owner/forge/v3/health/\(self.path(cap))/\(self.path(ver))", [:]) }
    }
    func verifyProvider() async {
        guard let tool = required(toolName, "Verification tool"), let params = parsedParameters() else { return }
        var body: [String: Any] = ["tool_name": tool, "parameters": params]
        if !capabilityID.isEmpty { body["capability_id"] = capabilityID }
        if !version.isEmpty { body["version"] = version }
        await freshOwner { _ = await self.call("POST", "/owner/forge/v3/providers/verify", body) }
    }

    private func freshOwner(_ action: @escaping () async -> Void) async {
        guard !ownerPassword.isEmpty else { status = "Enter the owner password for a fresh verification window."; return }
        let password = ownerPassword
        ownerPassword = ""
        guard await call("POST", "/native/sessions/reauth", ["password": password], show: false) != nil else { return }
        await action()
    }

    @discardableResult
    private func call(_ method: String, _ route: String, _ body: [String: Any]? = nil, show: Bool = true) async -> [String: Any]? {
        guard !host.isEmpty else { status = "Forge V3 is disabled until a non-production Vishnu host is configured."; return nil }
        guard let token, expiry > Date() else { status = "Native owner session expired. Sign in through Universal Capabilities again."; return nil }
        guard let url = URL(string: "https://\(host)/iphone/api\(route)") else { status = "Invalid Vishnu host configuration."; return nil }
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        do {
            let config = URLSessionConfiguration.ephemeral
            let session = URLSession(configuration: config, delegate: ForgeV3RedirectBlocker(), delegateQueue: nil)
            let (data, response) = try await session.data(for: request)
            guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else { throw CompanionError.badResponse("Vishnu returned an invalid or oversized response.") }
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? ["raw": String(data: data.prefix(2048), encoding: .utf8) ?? ""]
            guard (200..<300).contains(http.statusCode) else {
                if http.statusCode == 401 { keychain.remove("native.capabilities.token"); keychain.remove("native.capabilities.expiry") }
                status = http.statusCode == 403 ? "Vishnu denied this Forge action." : "Forge request failed (\(http.statusCode))."
                result = pretty(json)
                return nil
            }
            status = "Forge V3 request completed."
            if show { result = pretty(json) }
            return json
        } catch {
            status = "Vishnu could not complete the Forge request."
            return nil
        }
    }

    private func required(_ value: String, _ label: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { status = "\(label) is required."; return nil }
        return trimmed
    }
    private func parsedParameters() -> [String: Any]? {
        guard let data = parameters.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { status = "Parameters must be a JSON object."; return nil }
        return object
    }
    private func path(_ value: String) -> String { value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#"))) ?? "" }
    private func pretty(_ value: [String: Any]) -> String {
        guard JSONSerialization.isValidJSONObject(value), let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) else { return String(describing: value) }
        return String(data: data, encoding: .utf8) ?? String(describing: value)
    }
}

private final class ForgeV3RedirectBlocker: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

struct NativeForgeV3View: View {
    @StateObject private var store = NativeForgeV3Store()

    var body: some View {
        Form {
            Section("Safety") {
                Text(store.status).font(.footnote).foregroundStyle(.secondary)
                Text("Production activation is not available here. Mutations require fresh owner verification and remain subject to canonical approvals.").font(.footnote).foregroundStyle(.secondary)
                Button("Refresh readiness") { Task { await store.readiness() } }
                Button("OAuth providers") { Task { await store.providers() } }
            }
            Section("Capability") {
                TextField("Capability ID", text: $store.capabilityID).textInputAutocapitalization(.never)
                TextField("Version", text: $store.version).textInputAutocapitalization(.never)
                TextField("OAuth provider ID", text: $store.providerID).textInputAutocapitalization(.never)
                Button("OAuth status") { Task { await store.oauthStatus() } }
                SecureField("Owner password", text: $store.ownerPassword)
                Button("Start capability OAuth") { Task { await store.startOAuth() } }
                Button("Revoke capability OAuth", role: .destructive) { Task { await store.revokeOAuth() } }
            }
            Section("Canary rollout") {
                TextField("Target stage", text: $store.targetStage).textInputAutocapitalization(.never)
                TextField("Approved ticket ID", text: $store.approvalID).textInputAutocapitalization(.never)
                TextField("Qualified build ID", text: $store.buildID).textInputAutocapitalization(.never)
                Button("Inspect rollout") { Task { await store.rollout() } }
                Button("Run canary") { Task { await store.canary() } }
                Button("Request promotion") { Task { await store.requestPromotion() } }
                Button("Commit approved promotion") { Task { await store.commitPromotion() } }
                Button("Evaluate active health") { Task { await store.health() } }
            }
            Section("Provider verification") {
                TextField("Read-only verification tool", text: $store.toolName).textInputAutocapitalization(.never)
                TextEditor(text: $store.parameters).frame(minHeight: 100).font(.caption.monospaced())
                Button("Verify provider") { Task { await store.verifyProvider() } }
            }
            if !store.result.isEmpty {
                Section("Result") { Text(store.result).font(.caption.monospaced()).textSelection(.enabled) }
            }
        }
        .navigationTitle("Capability Forge V3")
        .navigationBarTitleDisplayMode(.inline)
    }
}
