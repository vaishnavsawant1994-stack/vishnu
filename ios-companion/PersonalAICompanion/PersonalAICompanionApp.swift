import SwiftUI
import UserNotifications
import UIKit

final class CompanionAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application:UIApplication,didFinishLaunchingWithOptions launchOptions:[UIApplication.LaunchOptionsKey:Any]?=nil)->Bool {
        BackgroundCoordinator.shared.register { NotificationCenter.default.post(name:.personalAIBackgroundRefresh,object:nil) }
        UNUserNotificationCenter.current().delegate=self
        UNUserNotificationCenter.current().requestAuthorization(options:[.alert,.sound,.badge]) { granted,_ in
            if granted { DispatchQueue.main.async { application.registerForRemoteNotifications() } }
        }
        return true
    }
    func application(_ application:UIApplication,didRegisterForRemoteNotificationsWithDeviceToken deviceToken:Data) {
        let token=deviceToken.map { String(format:"%02x",$0) }.joined()
        UserDefaults.standard.set(token,forKey:"personal_ai_apns_token")
        NotificationCenter.default.post(name:.personalAIAPNSToken,object:token)
    }
    func application(_ application:UIApplication,didFailToRegisterForRemoteNotificationsWithError error:Error) {
        NotificationCenter.default.post(name:.personalAIAPNSError,object:error.localizedDescription)
    }
    func userNotificationCenter(_ center:UNUserNotificationCenter,willPresent notification:UNNotification,withCompletionHandler completionHandler:@escaping (UNNotificationPresentationOptions)->Void) {
        completionHandler([.banner,.sound,.badge])
    }
}

extension Notification.Name {
    static let personalAIAPNSToken=Notification.Name("personalAIAPNSToken")
    static let personalAIAPNSError=Notification.Name("personalAIAPNSError")
    static let personalAIBackgroundRefresh=Notification.Name("personalAIBackgroundRefresh")
}

@main
struct PersonalAICompanionApp: App {
    @UIApplicationDelegateAdaptor(CompanionAppDelegate.self) private var appDelegate
    @StateObject private var store = CompanionStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if store.deviceID == nil {
                    ConnectOnboardingView(store: store)
                } else {
                    pairedHome
                }
            }
            .preferredColorScheme(.dark)
            .onAppear { if store.deviceID != nil { store.connect() } }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active, store.deviceID != nil { store.connect() }
                if phase == .background { BackgroundCoordinator.shared.schedule() }
            }
        }
    }

    private var pairedHome: some View {
        NavigationStack {
            Form {
                Section("Vishnu cloud") {
                    NavigationLink {
                        NativeCapabilitiesView()
                    } label: {
                        Label("Manage Universal Capabilities", systemImage: "point.3.connected.trianglepath.dotted")
                    }
                    NavigationLink {
                        NativeForgeV3View()
                    } label: {
                        Label("Capability Forge V3", systemImage: "hammer.circle")
                    }
                    Text("Vishnu cloud access is disabled in this internal-testing build; Capability Forge cloud controls are also disabled until a non-production server is configured.")
                        .font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
                    Text("Uses Safari so Google sign-in, trusted-device cookies, microphone access and conversation continuity work correctly.").font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
                }
                Section("Vishnu computer") {
                    LabeledContent("Address", value: store.baseURL)
                    Toggle("Allow insecure local development",isOn:$store.allowInsecureDevelopment)
                    if store.allowInsecureDevelopment {
                        Text("Development only. HTTP/WS exposes pairing and bearer credentials to the local network.").font(PersonalAITheme.Typography.supporting).foregroundStyle(.orange)
                    }
                }
                Section("Connection") {
                    LabeledContent("Status",value:store.status)
                    LabeledContent("Channel",value:store.connected ? "Connected" : "Offline")
                    HStack { Button("Connect") { store.connect() }; Button("Disconnect",role:.cancel) { store.disconnect() } }
                }
                Section("Voice") {
                    Toggle("Active voice session",isOn:Binding(get:{store.voiceActive},set:{ value in Task { await store.setVoiceActive(value) }}))
                    Text("Background audio is used only while an active voice session is running. Ordinary device connectivity follows iOS lifecycle rules.").font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
                }
                Section("Notifications") {
                    Text("The iPhone registers its APNs token and sends it through the authenticated Vishnu device channel. A later APNs provider stage can use this registration for server-initiated background notifications.").font(PersonalAITheme.Typography.supporting).foregroundStyle(.secondary)
                }
                Section("Security") {
                    Text("Device ID and bearer token are stored in the iPhone Keychain with this-device-only protection.").font(PersonalAITheme.Typography.supporting)
                    Button("Forget this iPhone",role:.destructive) { store.forgetDevice() }
                }
            }
            .scrollContentBackground(.hidden)
            .background(PersonalAITheme.ColorToken.background)
            .navigationTitle("Vishnu")
            .navigationBarTitleDisplayMode(.inline)
            .tint(PersonalAITheme.ColorToken.accent)
            .font(PersonalAITheme.Typography.body)
            .toolbar { ToolbarItem(placement: .principal) { Text("Vishnu").font(PersonalAITheme.Typography.pageTitle).fontWeight(.semibold) } }
        }
    }
}
