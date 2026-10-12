import AuthenticationServices
import CryptoKit
import Foundation
import Security
import SwiftUI
import UIKit

private struct NativeSessionResponse: Decodable {
    let access_token: String
    let expires_in: Int
    let session_id: String
}

private struct CapabilityEnvelope: Decodable {
    let capabilities: [Capability]
    struct Capability: Decodable, Identifiable {
        let id: String
        let name: String?
        let type: String?
        let method: String?
        let summary: String?
        let description: String?
        let risk: String?
        let approved_risk: String?
        let execution_supported: Bool?
        let connection: Connection?
        struct Connection: Decodable {
            let status: String?
            let auth_type: String?
        }
    }
}

@MainActor
final class NativeCapabilitiesStore: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    static let shared = NativeCapabilitiesStore()
    private let host = "personal-ai-runtime-production.up.railway.app"
    private let clientID = "ai.personal.companion.ios"
    private let redirectPath = "/iphone/native/callback/ios"
    private let keychain = KeychainStore.shared
    @Published var capabilities: [CapabilityEnvelope.Capability] = []
    @Published var status = "Sign in to manage approved Vishnu capabilities."
    @Published var signedIn = false
    @Published var searchText = ""
    private var authSession: ASWebAuthenticationSession?
    private var expiry: Date = .distantPast
    private var token: String? { keychain.get("native.capabilities.token") }

    override init() {
        super.init()
        expiry = Date(timeIntervalSince1970: Double(keychain.get("native.capabilities.expiry") ?? "0") ?? 0)
        signedIn = token != nil && expiry > Date()
        if signedIn { Task { await reload() } }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows).first(where: \.isKeyWindow) ?? UIWindow()
    }

    func authorize() {
        do {
            let verifier = Self.randomURLSafe(count: 48)
            let state = Self.randomURLSafe(count: 32)
            try keychain.set(verifier, for: "native.capabilities.pending.verifier")
            try keychain.set(state, for: "native.capabilities.pending.state")
            let challenge = Self.base64URL(SHA256Digest.hash(Data(verifier.utf8)))
            var components = URLComponents()
            components.scheme = "https"
            components.host = host
            components.path = "/iphone/native/authorize"
            components.queryItems = [
                URLQueryItem(name: "client_id", value: clientID),
                URLQueryItem(name: "redirect_uri", value: "https://\(host)\(redirectPath)"),
                URLQueryItem(name: "code_challenge", value: challenge),
                URLQueryItem(name: "state", value: state)
            ]
            guard let url = components.url else { throw CompanionError.invalidBase }
            status = "Waiting for explicit owner authorization in the secure browser…"
            let session = ASWebAuthenticationSession(url: url, callback: .https(host: host, path: redirectPath)) { [weak self] callback, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let error { self.status = "Sign-in cancelled or unavailable: \(error.localizedDescription)"; return }
                    guard let callback, let parts = URLComponents(url: callback, resolvingAgainstBaseURL: false) else {
                        self.status = "Vishnu returned an invalid authorization link."; return
                    }
                    guard callback.scheme == "https", callback.host == self.host, callback.path == self.redirectPath else {
                        self.clearPending(); self.status = "Vishnu returned an unexpected authorization address."; return
                    }
                    let values = Dictionary(parts.queryItems?.map { ($0.name, $0.value ?? "") } ?? [], uniquingKeysWith: { first, _ in first })
                    guard let code = values["code"], let returnedState = values["state"],
                          let savedState = self.keychain.get("native.capabilities.pending.state"),
                          let verifier = self.keychain.get("native.capabilities.pending.verifier"),
                          Self.constantTimeEqual(returnedState, savedState) else {
                        self.clearPending(); self.status = "Sign-in state validation failed."; return
                    }
                    await self.exchange(code: code, verifier: verifier)
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            authSession = session
            guard session.start() else { throw CompanionError.badResponse("Could not start secure browser authorization.") }
        } catch { status = error.localizedDescription }
    }

    func reload() async {
        do {
            let query = searchText.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
            let result: CapabilityEnvelope = try await api("GET", "/apps-tools/capabilities?query=\(query)&limit=100", as: CapabilityEnvelope.self)
            capabilities = result.capabilities
            status = "\(capabilities.count) capabilities · permissions are rechecked by Vishnu on every request."
        } catch { status = safe(error) }
    }

    func importOpenAPI(_ text: String) async throws {
        guard let data = text.data(using: .utf8), let document = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CompanionError.badResponse("OpenAPI document must be a JSON object.")
        }
        _ = try await request("POST", "/apps-tools/capabilities/openapi", ["document": document])
        await reload()
    }

    func addMCP(_ text: String) async throws {
        guard let data = text.data(using: .utf8), let descriptor = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CompanionError.badResponse("MCP descriptor must be a JSON object.")
        }
        _ = try await request("POST", "/apps-tools/mcp/servers", descriptor)
        await reload()
    }

    func connect(_ item: CapabilityEnvelope.Capability, serverURL: String, authType: String, secret: String) async throws {
        if item.type == "mcp_tool" {
            throw CompanionError.badResponse("Review MCP tools through the server's discovered tool list.")
        }
        if item.type == "mcp_server" {
            _ = try await request("POST", "/apps-tools/mcp/servers/\(path(item.id))/discover", ["auth_type": authType, "api_key": secret])
        } else {
            _ = try await request("POST", "/apps-tools/capabilities/\(path(item.id))/connect", ["server_url": serverURL, "auth_type": authType, "api_key": secret])
        }
        await reload()
    }

    func approveMCP(_ item: CapabilityEnvelope.Capability, risk: String) async throws {
        _ = try await request("POST", "/apps-tools/mcp/capabilities/\(path(item.id))/approve",
            ["risk": risk, "reviewed": true, "read_only_attested": risk == "read"])
        await reload()
    }

    func execute(_ item: CapabilityEnvelope.Capability, parameters: [String: Any], confirmWrite: Bool) async throws -> [String: Any] {
        let isWrite = (item.method ?? "GET").uppercased() != "GET" || ["write", "destructive"].contains(item.approved_risk ?? "")
        var payload: [String: Any] = ["parameters": parameters]
        if isWrite {
            guard confirmWrite else { throw CompanionError.badResponse("Write requires explicit confirmation.") }
            let ticket: [String: Any] = try await request("POST", "/apps-tools/capabilities/\(path(item.id))/execution-approvals", ["parameters": parameters])
            guard let approval = ticket["approval_id"] as? String else { throw CompanionError.badResponse("Vishnu did not create an approval.") }
            _ = try await request("POST", "/apps-tools/capabilities/\(path(item.id))/execution-approvals/\(path(approval))/approve", ["parameters": parameters])
            payload["approval_id"] = approval
        }
        return try await request("POST", "/apps-tools/capabilities/\(path(item.id))/execute", payload)
    }

    func audit(_ item: CapabilityEnvelope.Capability, kind: String) async throws -> [String: Any] {
        try await request("GET", "/apps-tools/capabilities/\(path(item.id))/\(kind)?limit=50", nil)
    }

    func rotate(_ item: CapabilityEnvelope.Capability, authType: String, secret: String) async throws {
        _ = try await request("POST", "/apps-tools/capabilities/\(path(item.id))/credentials/rotate", ["auth_type": authType, "api_key": secret])
    }

    func disconnect(_ item: CapabilityEnvelope.Capability) async throws {
        let endpoint = item.type == "mcp_server" ? "/apps-tools/mcp/servers/\(path(item.id))/disconnect" : "/apps-tools/capabilities/\(path(item.id))/disconnect"
        _ = try await request("POST", endpoint, [:])
        await reload()
    }

    func reauthenticate(password: String) async throws {
        _ = try await request("POST", "/native/sessions/reauth", ["password": password])
    }

    func rotateSession() async throws {
        let result: NativeSessionResponse = try await api("POST", "/native/sessions/rotate", as: NativeSessionResponse.self)
        try save(result)
    }

    func logout() async {
        do { _ = try await request("POST", "/native/sessions/logout", [:]) } catch { }
        clearSession()
    }

    private func exchange(code: String, verifier: String) async {
        do {
            let result: NativeSessionResponse = try await api("POST", "/native/sessions/exchange", as: NativeSessionResponse.self,
                body: ["client_id": clientID, "redirect_uri": "https://\(host)\(redirectPath)", "code": code, "code_verifier": verifier], authorized: false)
            try save(result)
            clearPending()
            signedIn = true
            status = "Owner session connected securely."
            await reload()
        } catch { clearPending(); status = safe(error) }
    }

    private func save(_ result: NativeSessionResponse) throws {
        guard result.expires_in > 0, !result.access_token.isEmpty else { throw CompanionError.badResponse("Invalid native session response.") }
        try keychain.set(result.access_token, for: "native.capabilities.token")
        expiry = Date().addingTimeInterval(TimeInterval(result.expires_in))
        try keychain.set(String(Int(expiry.timeIntervalSince1970)), for: "native.capabilities.expiry")
        signedIn = true
    }

    private func api<T: Decodable>(_ method: String, _ path: String, as type: T.Type, body: [String: Any]? = nil, authorized: Bool = true) async throws -> T {
        let data = try await dataRequest(method, path, body: body, authorized: authorized)
        do { return try JSONDecoder().decode(type, from: data) }
        catch { throw CompanionError.badResponse("Vishnu returned an invalid response.") }
    }

    private func dataRequest(_ method: String, _ path: String, body: [String: Any]? = nil, authorized: Bool = true) async throws -> Data {
        let url = URL(string: "https://\(host)/iphone/api\(path)")!
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body { request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        if authorized {
            guard let token, expiry > Date() else { clearSession(); throw CompanionError.badResponse("Owner session expired. Sign in again.") }
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let session = URLSession(configuration: .ephemeral, delegate: RedirectBlocker(), delegateQueue: nil)
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else { throw CompanionError.badResponse("Vishnu returned an invalid or oversized response.") }
        guard (200..<300).contains(http.statusCode) else {
            if http.statusCode == 401 { clearSession() }
            throw CompanionError.badResponse(http.statusCode == 403 ? "Vishnu denied this action." : "Vishnu request failed (\(http.statusCode)).")
        }
        return data
    }

    private func request(_ method: String, _ path: String, _ body: [String: Any]?) async throws -> [String: Any] {
        let data = try await dataRequest(method, path, body: body)
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CompanionError.badResponse("Vishnu returned an invalid response.")
        }
        return result
    }

    private func clearPending() {
        keychain.remove("native.capabilities.pending.verifier")
        keychain.remove("native.capabilities.pending.state")
    }

    private func clearSession() {
        keychain.remove("native.capabilities.token")
        keychain.remove("native.capabilities.expiry")
        expiry = .distantPast
        signedIn = false
        capabilities = []
        status = "Signed out."
    }

    private func safe(_ error: Error) -> String {
        if let error = error as? CompanionError { return error.localizedDescription }
        return "Vishnu could not complete the request. Check the connection and retry."
    }

    private func path(_ value: String) -> String { value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#"))) ?? "" }
    private static func randomURLSafe(count: Int) -> String {
        var bytes = [UInt8](repeating: 0, count: count)
        _ = SecRandomCopyBytes(kSecRandomDefault, count, &bytes)
        return base64URL(Data(bytes))
    }
    private static func base64URL(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    private static func constantTimeEqual(_ left: String, _ right: String) -> Bool {
        let a = Array(left.utf8), b = Array(right.utf8)
        guard a.count == b.count else { return false }
        return zip(a, b).reduce(UInt8(0)) { $0 | ($1.0 ^ $1.1) } == 0
    }
}

private final class RedirectBlocker: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

private enum SHA256Digest {
    static func hash(_ data: Data) -> Data {
        Data(SHA256.hash(data: data))
    }
}

struct NativeCapabilitiesView: View {
    @StateObject private var store = NativeCapabilitiesStore.shared
    @State private var showOpenAPI = false
    @State private var showMCP = false
    @State private var documentText = ""
    @State private var mcpText = ""

    var body: some View {
        List {
            Section {
                Text(store.status).font(.footnote).foregroundStyle(.secondary)
                if store.signedIn {
                    Button("Refresh capabilities") { Task { await store.reload() } }
                    Button("Rotate native session") { Task { do { try await store.rotateSession(); store.status = "Session rotated." } catch { store.status = error.localizedDescription } } }
                    Button("Sign out and revoke", role: .destructive) { Task { await store.logout() } }
                } else {
                    Button("Sign in securely") { store.authorize() }
                }
            } header: { Text("Owner session") }
            if store.signedIn {
                Section("Discover") {
                    Button("Import OpenAPI JSON") { showOpenAPI = true }
                    Button("Add MCP server") { showMCP = true }
                }
                Section("Capabilities") {
                    ForEach(filtered, id: \.id) { item in
                        NavigationLink {
                            NativeCapabilityDetailView(item: item, store: store)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.name ?? item.id).font(.headline)
                                Text("\(item.method ?? item.type ?? "Tool") · \(item.risk ?? "review") · \(item.connection?.status ?? "not connected")")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .searchable(text: $store.searchText, prompt: "Search capabilities")
        .navigationTitle("Universal Capabilities")
        .task { if store.signedIn { await store.reload() } }
        .sheet(isPresented: $showOpenAPI) {
            NavigationStack { Form { TextEditor(text: $documentText).frame(minHeight: 280) }
                .navigationTitle("OpenAPI import")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Discover") { Task { do { try await store.importOpenAPI(documentText); showOpenAPI = false; documentText = "" } catch { store.status = error.localizedDescription } } } } }
            }
        }
        .sheet(isPresented: $showMCP) {
            NavigationStack { Form { TextEditor(text: $mcpText).frame(minHeight: 240) }
                .navigationTitle("MCP server")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Discover") { Task { do { try await store.addMCP(mcpText); showMCP = false; mcpText = "" } catch { store.status = error.localizedDescription } } } } }
            }
        }
    }

    private var filtered: [CapabilityEnvelope.Capability] {
        guard !store.searchText.isEmpty else { return store.capabilities }
        return store.capabilities.filter { ($0.name ?? "").localizedCaseInsensitiveContains(store.searchText) || $0.id.localizedCaseInsensitiveContains(store.searchText) }
    }
}

private struct NativeCapabilityDetailView: View {
    let item: CapabilityEnvelope.Capability
    @ObservedObject var store: NativeCapabilitiesStore
    @State private var serverURL = ""
    @State private var authType = "none"
    @State private var secret = ""
    @State private var risk = "read"
    @State private var parameters = "{}"
    @State private var result = ""
    @State private var password = ""
    @State private var showReauth = false
    @State private var showExecution = false
    @State private var ownerVerified = false

    var body: some View {
        Form {
            Section("Details and permissions") {
                LabeledContent("Operation", value: "\(item.method ?? item.type ?? "Tool")")
                LabeledContent("Risk", value: item.risk ?? item.approved_risk ?? "Review required")
                Text(item.description ?? item.summary ?? "No description provided.")
                if item.execution_supported == false { Text("This operation is blocked because its schema is unsupported.").foregroundStyle(.orange) }
            }
            if item.type == "mcp_tool" {
                Section("Owner risk review") {
                    Picker("Classification", selection: $risk) { Text("Read only (attest)").tag("read"); Text("Write").tag("write"); Text("Destructive").tag("destructive") }
                    Button("Approve classification") { Task { await withReauth { try await store.approveMCP(item, risk: risk) } } }
                }
            } else if item.connection?.status == "connected" {
                Section("Connection") {
                    TextField("Operation parameters JSON", text: $parameters, axis: .vertical).lineLimit(3...8)
                    Button("Test / execute") { showExecution = true }
                    Button("Rotate bearer credential") { Task { await withReauth { try await store.rotate(item, authType: "bearer_token", secret: secret) }; secret = "" } }
                    SecureField("Replacement credential", text: $secret)
                    Button("History") { Task { do { result = try await store.audit(item, kind: "history").description } catch { result = error.localizedDescription } } }
                    Button("Audit log") { Task { do { result = try await store.audit(item, kind: "audit").description } catch { result = error.localizedDescription } } }
                    Button("Disconnect", role: .destructive) { Task { await withReauth { try await store.disconnect(item) } } }
                }
            } else {
                Section("Secure connection") {
                    TextField("HTTPS API server URL", text: $serverURL).textInputAutocapitalization(.never).keyboardType(.URL)
                    Picker("Authentication", selection: $authType) { Text("None").tag("none"); Text("Bearer token").tag("bearer_token"); Text("API key header").tag("api_key_header") }
                    if authType != "none" { SecureField("Secret (sent only to Vishnu vault)", text: $secret) }
                    Button("Connect and approve") { Task { await withReauth { try await store.connect(item, serverURL: serverURL, authType: authType, secret: secret) }; secret = "" } }
                }
            }
            if !result.isEmpty { Section("Result / audit") { Text(result).font(.caption.monospaced()).textSelection(.enabled) } }
            if showReauth {
                Section("Recent owner verification") {
                    SecureField("Owner password", text: $password)
                    Button("Verify owner") { Task { do { try await store.reauthenticate(password: password); showReauth = false; ownerVerified = true; store.status = "Owner verified. Repeat the requested action to continue." } catch { store.status = error.localizedDescription } } }
                }
            }
        }
        .navigationTitle(item.name ?? "Capability")
        .confirmationDialog("Confirm a one-time provider operation", isPresented: $showExecution) {
            Button("Execute once", role: .destructive) {
                Task { do {
                    let raw = parameters.data(using: .utf8) ?? Data("{}".utf8)
                    guard let params = try JSONSerialization.jsonObject(with: raw) as? [String: Any] else { throw CompanionError.badResponse("Parameters must be a JSON object.") }
                    let write = (item.method ?? "GET").uppercased() != "GET" || ["write", "destructive"].contains(item.approved_risk ?? "")
                    if write {
                        await withReauth {
                            let response = try await store.execute(item, parameters: params, confirmWrite: true)
                            result = String(data: try JSONSerialization.data(withJSONObject: response, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? "Operation completed."
                        }
                    } else {
                        let response = try await store.execute(item, parameters: params, confirmWrite: false)
                        result = String(data: try JSONSerialization.data(withJSONObject: response, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? "Operation completed."
                    }
                } catch { result = error.localizedDescription } }
            }
            Button("Cancel", role: .cancel) { }
        } message: { Text("Vishnu enforces the current permission and approval at dispatch. Provider acceptance is not independent state verification.") }
    }

    private func withReauth(_ action: @escaping () async throws -> Void) async {
        guard ownerVerified else { showReauth = true; return }
        ownerVerified = false
        guard !password.isEmpty else { showReauth = true; return }
        do { try await store.reauthenticate(password: password); password = ""; try await action() }
        catch { store.status = error.localizedDescription }
    }
}
