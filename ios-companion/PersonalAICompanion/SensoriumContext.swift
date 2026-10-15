import Foundation
import CoreLocation
import CoreMotion
import Network
import UIKit
import AVFoundation

struct SensoriumGrant: Identifiable {
    let id: String
    let sensor: String
    let resourceID: String
    let expiresAt: Date
    let reason: String

    var active: Bool { expiresAt > Date() }
    var proof: [String: Any] {
        [
            "sensor": sensor,
            "resource_id": resourceID,
            "sensor_session_id": id,
            "expires_at_epoch": expiresAt.timeIntervalSince1970,
            "local_consent": true,
            "reason": reason,
        ]
    }
}

@MainActor
final class SensoriumContext: NSObject, ObservableObject, CLLocationManagerDelegate {
    static let shared = SensoriumContext()
    @Published private(set) var grants: [String: SensoriumGrant] = [:]
    @Published private(set) var lastStatus = "All sensors off"

    private let locationManager = CLLocationManager()
    private let motion = CMMotionManager()
    private let altimeter = CMAltimeter()
    private let network = NWPathMonitor()
    private let networkQueue = DispatchQueue(label: "vishnu.sensorium.network")
    private var latestLocation: CLLocation?
    private var latestHeading: CLHeading?
    private var latestAltitude: CMAltitudeData?
    private var latestPath: NWPath?

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
        network.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in self?.latestPath = path }
        }
        network.start(queue: networkQueue)
        UIDevice.current.isBatteryMonitoringEnabled = true
    }

    deinit { network.cancel() }

    private func key(_ sensor: String, _ resource: String = "*") -> String { "\(sensor.lowercased())|\(resource)" }

    func grant(_ sensor: String, resourceID: String = "*", reason: String, ttl: TimeInterval = 300) -> SensoriumGrant {
        let kind = sensor.lowercased()
        let bounded = min(max(ttl, 30), 30 * 60)
        let value = SensoriumGrant(id: UUID().uuidString, sensor: kind, resourceID: resourceID, expiresAt: Date().addingTimeInterval(bounded), reason: String(reason.prefix(240)))
        grants[key(kind, resourceID)] = value
        lastStatus = "\(kind) allowed for this session"
        return value
    }

    func current(_ sensor: String, resourceID: String = "*") -> SensoriumGrant? {
        let kind = sensor.lowercased()
        let exact = grants[key(kind, resourceID)] ?? (resourceID == "*" ? nil : grants[key(kind, "*")])
        guard let exact else { return nil }
        if !exact.active { grants.removeValue(forKey: key(exact.sensor, exact.resourceID)); return nil }
        return exact
    }

    func require(_ sensor: String, resourceID: String = "*") throws -> SensoriumGrant {
        guard let value = current(sensor, resourceID: resourceID) else {
            throw CompanionError.badResponse("Open Vishnu and allow \(sensor) for this session first.")
        }
        return value
    }

    func revoke(_ sensor: String, resourceID: String = "*") {
        let kind = sensor.lowercased()
        grants.removeValue(forKey: key(kind, resourceID))
        if resourceID == "*" {
            grants.keys.filter { $0.hasPrefix("\(kind)|") }.forEach { grants.removeValue(forKey: $0) }
        }
        if kind == "location" { locationManager.stopUpdatingLocation(); locationManager.stopUpdatingHeading() }
        if kind == "motion" { motion.stopAccelerometerUpdates(); motion.stopGyroUpdates(); motion.stopDeviceMotionUpdates(); altimeter.stopRelativeAltitudeUpdates() }
    }

    func stopAll() {
        grants.removeAll()
        locationManager.stopUpdatingLocation(); locationManager.stopUpdatingHeading()
        motion.stopAccelerometerUpdates(); motion.stopGyroUpdates(); motion.stopDeviceMotionUpdates(); altimeter.stopRelativeAltitudeUpdates()
        SensoriumScreenSession.shared.stop()
        SensoriumSpatialSession.shared.stop()
        lastStatus = "All sensors off"
    }

    func activeGrants() -> [SensoriumGrant] {
        let now = Date()
        grants = grants.filter { $0.value.expiresAt > now }
        return grants.values.sorted { $0.sensor < $1.sensor }
    }

    func activateByOwner(_ sensor: String, reason: String = "Owner enabled Sensorium") async throws {
        let kind = sensor.lowercased()
        guard UIApplication.shared.applicationState == .active else {
            throw CompanionError.badResponse("Open Vishnu in the foreground to start Sensorium.")
        }
        switch kind {
        case "location":
            let status = locationManager.authorizationStatus
            if status == .notDetermined { locationManager.requestWhenInUseAuthorization() }
            if status == .denied || status == .restricted { throw CompanionError.badResponse("Location permission is not available.") }
            locationManager.startUpdatingLocation()
            if CLLocationManager.headingAvailable() { locationManager.startUpdatingHeading() }
            _ = grant(kind, reason: reason)
        case "motion":
            if motion.isAccelerometerAvailable { motion.startAccelerometerUpdates() }
            if motion.isGyroAvailable { motion.startGyroUpdates() }
            if motion.isDeviceMotionAvailable { motion.startDeviceMotionUpdates() }
            if CMAltimeter.isRelativeAltitudeAvailable() {
                altimeter.startRelativeAltitudeUpdates(to: OperationQueue.main) { [weak self] value, _ in
                    Task { @MainActor in self?.latestAltitude = value }
                }
            }
            _ = grant(kind, reason: reason)
        case "environment", "network":
            _ = grant(kind, reason: reason)
        case "microphone":
            let allowed = await withCheckedContinuation { continuation in
                AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
            }
            guard allowed else { throw CompanionError.badResponse("Microphone permission was not granted.") }
            try SensoriumAudioFeatures.shared.start()
            _ = grant(kind, reason: reason)
        case "screen":
            try await SensoriumScreenSession.shared.startByOwner()
            _ = grant(kind, resourceID: "mobile:screen", reason: reason)
        case "document":
            guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized || await AVCaptureDevice.requestAccess(for: .video) else {
                throw CompanionError.badResponse("Camera permission is required for local document extraction.")
            }
            _ = grant(kind, reason: reason)
        case "spatial":
            guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized || await AVCaptureDevice.requestAccess(for: .video) else {
                throw CompanionError.badResponse("Camera permission is required for ARKit spatial sensing.")
            }
            try SensoriumSpatialSession.shared.startByOwner()
            _ = grant(kind, resourceID: "mobile:spatial", reason: reason)
        default:
            _ = grant(kind, reason: reason)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) { latestLocation = locations.last }
    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) { latestHeading = newHeading }

    func inventory() -> [String: Any] {
        [
            "location": ["available": CLLocationManager.locationServicesEnabled(), "authorization": locationManager.authorizationStatus.rawValue],
            "motion": ["accelerometer": motion.isAccelerometerAvailable, "gyroscope": motion.isGyroAvailable, "device_motion": motion.isDeviceMotionAvailable, "magnetometer": motion.isMagnetometerAvailable],
            "environment": ["barometer": CMAltimeter.isRelativeAltitudeAvailable(), "proximity": true, "ambient_light_lux": false, "thermal": true, "battery": true],
            "network": ["available": true],
            "screen": ["replaykit": SensoriumScreenSession.shared.available],
            "microphone": ["permission": SensoriumAudioFeatures.permissionDescription],
            "document": ["vision_text": true, "barcode": true, "hand_pose": true, "body_pose": true],
            "spatial": SensoriumSpatialSession.shared.inventory(),
            "captured_at": Date().timeIntervalSince1970,
        ]
    }

    private func arr(_ values: (Double, Double, Double)?) -> [Double]? { values.map { [$0.0, $0.1, $0.2] } }

    func snapshot(_ sensors: [String]) throws -> [String: Any] {
        var values: [String: Any] = [:]
        var proofs: [String: Any] = [:]
        for requested in sensors.prefix(16) {
            let kind = requested.lowercased()
            let grant = try require(kind)
            proofs[kind] = grant.proof
            switch kind {
            case "location":
                if let location = latestLocation {
                    values[kind] = [
                        "available": true,
                        "latitude": location.coordinate.latitude,
                        "longitude": location.coordinate.longitude,
                        "accuracy_m": location.horizontalAccuracy,
                        "altitude_m": location.altitude,
                        "bearing_deg": latestHeading?.trueHeading as Any,
                        "speed_m_s": location.speed,
                        "captured_at": location.timestamp.timeIntervalSince1970,
                        "freshness_seconds": 60.0,
                        "confidence": location.horizontalAccuracy <= 20 ? 0.95 : location.horizontalAccuracy <= 100 ? 0.8 : 0.55,
                    ]
                } else {
                    values[kind] = ["available": false, "captured_at": Date().timeIntervalSince1970, "confidence": 0.2]
                }
            case "motion":
                let a = motion.accelerometerData?.acceleration
                let g = motion.gyroData?.rotationRate
                let dm = motion.deviceMotion
                values[kind] = [
                    "accelerometer_g": a.map { [$0.x, $0.y, $0.z] } as Any,
                    "gyroscope_rad_s": g.map { [$0.x, $0.y, $0.z] } as Any,
                    "orientation_rad_yaw_pitch_roll": dm.map { [$0.attitude.yaw, $0.attitude.pitch, $0.attitude.roll] } as Any,
                    "magnetic_field_accuracy": dm?.magneticField.accuracy.rawValue as Any,
                    "activity_hint": activityHint(),
                    "captured_at": Date().timeIntervalSince1970,
                    "freshness_seconds": 5.0,
                    "confidence": dm == nil && a == nil ? 0.3 : 0.9,
                ]
            case "environment":
                UIDevice.current.isProximityMonitoringEnabled = true
                UIDevice.current.isBatteryMonitoringEnabled = true
                values[kind] = [
                    "proximity_near": UIDevice.current.proximityState,
                    "ambient_light_lux": NSNull(),
                    "ambient_light_public_api_available": false,
                    "relative_altitude_m": latestAltitude?.relativeAltitude.doubleValue as Any,
                    "pressure_kpa": latestAltitude?.pressure.doubleValue as Any,
                    "thermal_status": ProcessInfo.processInfo.thermalState.rawValue,
                    "battery_percent": UIDevice.current.batteryLevel < 0 ? -1 : Int(UIDevice.current.batteryLevel * 100),
                    "orientation": UIDevice.current.orientation.rawValue,
                    "captured_at": Date().timeIntervalSince1970,
                    "freshness_seconds": 15.0,
                    "confidence": 0.9,
                ]
            case "network":
                let path = latestPath
                values[kind] = [
                    "connected": path?.status == .satisfied,
                    "expensive": path?.isExpensive ?? false,
                    "constrained": path?.isConstrained ?? false,
                    "transports": networkTransports(path),
                    "captured_at": Date().timeIntervalSince1970,
                    "freshness_seconds": 30.0,
                    "confidence": 0.95,
                ]
            default: break
            }
        }
        return ["sensors": values, "sessions": proofs]
    }

    private func activityHint() -> String {
        guard let a = motion.accelerometerData?.acceleration else { return "unknown" }
        let magnitude = sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
        if magnitude > 1.8 { return "high_motion" }
        if abs(magnitude - 1.0) > 0.12 { return "moving" }
        return "stationary_likely"
    }

    private func networkTransports(_ path: NWPath?) -> [String] {
        guard let path else { return [] }
        var rows: [String] = []
        if path.usesInterfaceType(.wifi) { rows.append("wifi") }
        if path.usesInterfaceType(.cellular) { rows.append("cellular") }
        if path.usesInterfaceType(.wiredEthernet) { rows.append("ethernet") }
        if path.usesInterfaceType(.loopback) { rows.append("loopback") }
        return rows
    }
}
