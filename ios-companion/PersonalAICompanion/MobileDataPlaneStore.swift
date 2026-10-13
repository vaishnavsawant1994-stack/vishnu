import Foundation

actor MobileDataPlaneStore {
    private static let progressFields:[String] = [
        "project_id","project_name","status","progress","task_id","task_title","task_status",
        "milestone_id","milestone_title","milestone_status","last_step","next_step",
        "last_activity","allowed_notes","updated_at"
    ]
    private static let blocked:Set<String> = [
        "password","passwd","passphrase","secret","token","access_token","refresh_token",
        "api_key","apikey","authorization","cookie","credential","private_key","session_token",
        "bearer_token","bytes","content_bytes","raw","raw_bytes","raw_content","file_bytes",
        "image_bytes","audio_bytes","video_bytes","document_content"
    ]
    private static let maxBytes = 64 * 1024

    private let url:URL
    private let outboxURL:URL
    private var items:[String:[String:Any]] = [:]
    private var outbox:[[String:Any]] = []

    init() {
        let root = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask).first!
        let directory = root.appendingPathComponent("Vishnu",isDirectory:true)
        try? FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        self.url = directory.appendingPathComponent("data-plane-cache.json")
        self.outboxURL = directory.appendingPathComponent("data-plane-outbox.json")
        if let data=try? Data(contentsOf:self.url),
           let object=try? JSONSerialization.jsonObject(with:data) as? [String:[String:Any]] {
            self.items=object
        }
        if let data=try? Data(contentsOf:self.outboxURL),
           let object=try? JSONSerialization.jsonObject(with:data) as? [[String:Any]] {
            self.outbox=object
        }
    }

    private func normalized(_ value:String)->String {
        value.trimmingCharacters(in:.whitespacesAndNewlines).lowercased().replacingOccurrences(of:"-",with:"_").replacingOccurrences(of:" ",with:"_")
    }

    private func containsBlocked(_ value:Any,depth:Int=0)->Bool {
        if depth > 8 { return true }
        if let dict=value as? [String:Any] {
            for (raw,child) in dict {
                let key=normalized(raw)
                if Self.blocked.contains(key) || key.hasSuffix("_password") || key.hasSuffix("_secret") || key.hasSuffix("_token") || key.hasSuffix("_credential") { return true }
                if containsBlocked(child,depth:depth+1) { return true }
            }
        } else if let array=value as? [Any] {
            return array.contains { containsBlocked($0,depth:depth+1) }
        }
        return false
    }

    private func projection(_ payload:[String:Any]) throws -> [String:Any] {
        if containsBlocked(payload) { throw NSError(domain:"VishnuDataPlane",code:1,userInfo:[NSLocalizedDescriptionKey:"progress payload contains prohibited secret/raw-content fields"]) }
        var result:[String:Any]=[:]
        for key in Self.progressFields where payload[key] != nil { result[key]=payload[key] }
        guard JSONSerialization.isValidJSONObject(result) else { throw NSError(domain:"VishnuDataPlane",code:2,userInfo:[NSLocalizedDescriptionKey:"progress payload is not JSON-safe"]) }
        let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
        if data.count > Self.maxBytes { throw NSError(domain:"VishnuDataPlane",code:3,userInfo:[NSLocalizedDescriptionKey:"progress payload is too large"]) }
        return result
    }

    private func canonical(_ value:[String:Any]) -> Data? {
        guard JSONSerialization.isValidJSONObject(value) else { return nil }
        return try? JSONSerialization.data(withJSONObject:value,options:[.sortedKeys])
    }

    private func persistItems() throws {
        let data=try JSONSerialization.data(withJSONObject:items,options:[.sortedKeys])
        try data.write(to:url,options:[.atomic,.completeFileProtection])
    }

    private func persistOutbox() throws {
        let data=try JSONSerialization.data(withJSONObject:outbox,options:[.sortedKeys])
        try data.write(to:outboxURL,options:[.atomic,.completeFileProtection])
    }

    func put(globalID:String,entityType:String,version:Int,payload:[String:Any]) throws -> [String:Any] {
        let globalID=globalID.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !globalID.isEmpty,globalID.count<=240,!entityType.isEmpty,entityType.count<=120,version>=1 else {
            throw NSError(domain:"VishnuDataPlane",code:4,userInfo:[NSLocalizedDescriptionKey:"invalid data-plane item"])
        }
        let clean=try projection(payload)
        if let current=items[globalID],let localVersion=current["version"] as? Int {
            if version < localVersion {
                return ["applied":false,"conflict":true,"local_version":localVersion]
            }
            if version == localVersion {
                let localPayload=current["payload"] as? [String:Any] ?? [:]
                if canonical(localPayload) != canonical(clean) {
                    return ["applied":false,"conflict":true,"local_version":localVersion]
                }
                if (current["tombstone"] as? Bool) != true {
                    return ["applied":true,"duplicate":true,"global_id":globalID,"version":version,"payload":clean]
                }
            }
        }
        items[globalID]=[
            "global_id":globalID,
            "entity_type":entityType,
            "storage_policy":"progress_only",
            "version":version,
            "payload":clean,
            "tombstone":false,
            "updated_at_ms":Int(Date().timeIntervalSince1970*1000)
        ]
        try persistItems()
        return ["applied":true,"global_id":globalID,"version":version,"payload":clean]
    }

    func putLocal(globalID:String,entityType:String,payload:[String:Any]) throws -> [String:Any] {
        let globalID=globalID.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !globalID.isEmpty,globalID.count<=240,!entityType.isEmpty,entityType.count<=120 else {
            throw NSError(domain:"VishnuDataPlane",code:5,userInfo:[NSLocalizedDescriptionKey:"invalid local data-plane item"])
        }
        let clean=try projection(payload)
        let version=((items[globalID]?["version"] as? Int) ?? 0)+1
        items[globalID]=[
            "global_id":globalID,"entity_type":entityType,"storage_policy":"progress_only",
            "version":version,"payload":clean,"tombstone":false,
            "updated_at_ms":Int(Date().timeIntervalSince1970*1000)
        ]
        let sourceEventID=UUID().uuidString
        outbox.append([
            "source_event_id":sourceEventID,"global_id":globalID,"entity_type":entityType,
            "storage_policy":"progress_only","version":version,"event_kind":"update","payload":clean,
            "created_at_ms":Int(Date().timeIntervalSince1970*1000)
        ])
        try persistItems();try persistOutbox()
        return ["applied":true,"source_event_id":sourceEventID,"global_id":globalID,"version":version,"payload":clean]
    }

    func get(_ globalID:String)->[String:Any]? { items[globalID] }

    func tombstone(globalID:String,version:Int)throws->Bool {
        guard var current=items[globalID],let localVersion=current["version"] as? Int,version>=localVersion else{return false}
        if version == localVersion && (current["tombstone"] as? Bool) != true { return false }
        current["version"]=version;current["tombstone"]=true;current["updated_at_ms"]=Int(Date().timeIntervalSince1970*1000);items[globalID]=current
        try persistItems();return true
    }

    func tombstoneLocal(globalID:String)throws->[String:Any] {
        guard var current=items[globalID],let localVersion=current["version"] as? Int else {
            throw NSError(domain:"VishnuDataPlane",code:6,userInfo:[NSLocalizedDescriptionKey:"data-plane item not found"])
        }
        let version=localVersion+1
        current["version"]=version;current["tombstone"]=true;current["updated_at_ms"]=Int(Date().timeIntervalSince1970*1000);items[globalID]=current
        let sourceEventID=UUID().uuidString
        outbox.append([
            "source_event_id":sourceEventID,"global_id":globalID,
            "entity_type":current["entity_type"] as? String ?? "project",
            "storage_policy":"progress_only","version":version,"event_kind":"delete",
            "payload":["updated_at":Int(Date().timeIntervalSince1970*1000)],
            "created_at_ms":Int(Date().timeIntervalSince1970*1000)
        ])
        try persistItems();try persistOutbox()
        return ["deleted":true,"source_event_id":sourceEventID,"global_id":globalID,"version":version]
    }

    func pending(limit:Int=100)->[String:Any] {
        let bounded=max(1,min(limit,500))
        let ordered=outbox.sorted {
            (($0["created_at_ms"] as? Int) ?? 0) < (($1["created_at_ms"] as? Int) ?? 0)
        }
        return ["events":Array(ordered.prefix(bounded))]
    }

    func acknowledge(sourceEventID:String)throws->Bool {
        guard !sourceEventID.isEmpty else { throw NSError(domain:"VishnuDataPlane",code:7,userInfo:[NSLocalizedDescriptionKey:"source_event_id is required"]) }
        let count=outbox.count
        outbox.removeAll { ($0["source_event_id"] as? String)==sourceEventID }
        if outbox.count != count { try persistOutbox();return true }
        return false
    }

    func status()->[String:Any] {
        let deleted=items.values.filter { ($0["tombstone"] as? Bool)==true }.count
        return ["items":items.count,"tombstones":deleted,"pending_local_events":outbox.count,"raw_file_bytes_stored":false,"secrets_stored":false,"file_protection":"complete"]
    }
}

@MainActor
final class MobileDataPlaneBridge {
    static let shared=MobileDataPlaneBridge()
    private let store=MobileDataPlaneStore()
    private var installed=false

    func install(on socket:DeviceSocket) {
        guard !installed else{return};installed=true
        let previous=socket.commandHandler
        socket.commandHandler={ [store] message in
            let action=message["action"] as? String ?? ""
            let params=message["parameters"] as? [String:Any] ?? [:]
            do {
                switch action {
                case "data_plane_status":
                    return ["ok":true,"result":await store.status()]
                case "data_plane_progress_put":
                    guard let id=params["global_id"] as? String,let version=(params["version"] as? NSNumber)?.intValue else{return["ok":false,"error":"global_id and version are required"]}
                    let entity=params["entity_type"] as? String ?? "project"
                    let payload=params["payload"] as? [String:Any] ?? [:]
                    return ["ok":true,"result":try await store.put(globalID:id,entityType:entity,version:version,payload:payload)]
                case "data_plane_progress_get":
                    guard let id=params["global_id"] as? String else{return["ok":false,"error":"global_id is required"]}
                    return ["ok":true,"result":await store.get(id) ?? ["missing":true]]
                case "data_plane_tombstone":
                    guard let id=params["global_id"] as? String,let version=(params["version"] as? NSNumber)?.intValue else{return["ok":false,"error":"global_id and version are required"]}
                    return ["ok":true,"result":["deleted":try await store.tombstone(globalID:id,version:version)]]
                case "data_plane_progress_pending":
                    return ["ok":true,"result":await store.pending(limit:(params["limit"] as? NSNumber)?.intValue ?? 100)]
                case "data_plane_progress_ack":
                    guard let eventID=params["source_event_id"] as? String else{return["ok":false,"error":"source_event_id is required"]}
                    return ["ok":true,"result":["acknowledged":try await store.acknowledge(sourceEventID:eventID)]]
                default:
                    if let previous { return await previous(message) }
                    return ["ok":false,"error":"Unsupported iOS action: \(action)"]
                }
            } catch { return ["ok":false,"error":error.localizedDescription] }
        }
    }
}
