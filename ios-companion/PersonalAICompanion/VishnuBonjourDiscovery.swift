import Foundation

final class VishnuBonjourDiscovery: NSObject, NetServiceBrowserDelegate, NetServiceDelegate {
    private static var active: [UUID: VishnuBonjourDiscovery] = [:]
    private static let lock = NSLock()

    private let id = UUID()
    private let expectedName: String
    private let completion: (Result<String, Error>) -> Void
    private let browser = NetServiceBrowser()
    private var resolving: NetService?
    private var finished = false

    private init(serviceID: String, completion: @escaping (Result<String, Error>) -> Void) {
        self.expectedName = "Vishnu-\(serviceID)"
        self.completion = completion
        super.init()
    }

    static func discover(serviceID: String, timeout: TimeInterval = 8, completion: @escaping (Result<String, Error>) -> Void) {
        let discovery = VishnuBonjourDiscovery(serviceID: serviceID, completion: completion)
        lock.lock(); active[discovery.id] = discovery; lock.unlock()
        discovery.start(timeout: timeout)
    }

    private func start(timeout: TimeInterval) {
        browser.delegate = self
        browser.searchForServices(ofType: "_vishnu._tcp.", inDomain: "local.")
        DispatchQueue.main.asyncAfter(deadline: .now() + min(max(timeout, 1), 30)) { [weak self] in
            self?.finish(.failure(CompanionError.badResponse("Could not find this Vishnu on the local network.")))
        }
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        guard !finished, service.name == expectedName else { return }
        browser.stop()
        resolving = service
        service.delegate = self
        service.resolve(withTimeout: 5)
    }

    func netServiceDidResolveAddress(_ sender: NetService) {
        guard let host = sender.hostName?.trimmingCharacters(in: CharacterSet(charactersIn: ".")),
              !host.isEmpty, sender.port > 0 else {
            finish(.failure(CompanionError.badResponse("Vishnu discovery returned an invalid endpoint.")))
            return
        }
        finish(.success("https://\(host):\(sender.port)"))
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String : NSNumber]) {
        finish(.failure(CompanionError.badResponse("Vishnu was found but could not be resolved.")))
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String : NSNumber]) {
        finish(.failure(CompanionError.badResponse("Vishnu local discovery could not start.")))
    }

    private func finish(_ result: Result<String, Error>) {
        guard !finished else { return }
        finished = true
        browser.stop()
        resolving?.stop()
        resolving = nil
        Self.lock.lock(); Self.active.removeValue(forKey: id); Self.lock.unlock()
        DispatchQueue.main.async { self.completion(result) }
    }
}