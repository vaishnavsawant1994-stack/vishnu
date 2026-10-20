import SwiftUI

/// Shared semantic values for the native companion. Font styles intentionally
/// use Dynamic Type roles so the system text size and accessibility settings win.
enum PersonalAITheme {
    enum ColorToken {
        static let background = Color(red: 2/255, green: 6/255, blue: 11/255)
        static let deepBackground = Color(red: 3/255, green: 10/255, blue: 18/255)
        static let surface = Color(red: 7/255, green: 21/255, blue: 34/255).opacity(0.72)
        static let elevatedSurface = Color(red: 9/255, green: 26/255, blue: 40/255)
        static let accent = Color(red: 32/255, green: 184/255, blue: 1)
        static let brightAccent = Color(red: 77/255, green: 220/255, blue: 1)
        static let softAccent = Color(red: 157/255, green: 219/255, blue: 1)
        static let primaryText = Color(red: 245/255, green: 250/255, blue: 1)
        static let secondaryText = Color(red: 167/255, green: 185/255, blue: 202/255)
        static let mutedText = Color(red: 102/255, green: 125/255, blue: 145/255)
        static let border = Color(red: 120/255, green: 190/255, blue: 230/255).opacity(0.18)
        static let destructive = Color.red
    }

    enum Space {
        static let x1: CGFloat = 4
        static let x2: CGFloat = 8
        static let x3: CGFloat = 12
        static let x4: CGFloat = 16
        static let x5: CGFloat = 20
        static let x6: CGFloat = 24
        static let x8: CGFloat = 32
        static let x10: CGFloat = 40
    }

    enum Typography {
        static let display: Font = .largeTitle
        static let pageTitle: Font = .title3
        static let sectionTitle: Font = .headline
        static let body: Font = .body
        static let supporting: Font = .subheadline
        static let control: Font = .callout
        static let metadata: Font = .caption
    }

    static let touchTarget: CGFloat = 44
    static let controlCornerRadius: CGFloat = 17
}

struct VishnuGenesisBackground: View {
    var body: some View {
        ZStack {
            PersonalAITheme.ColorToken.background
            Image("vishnu-genesis-cosmic-mobile")
                .resizable()
                .scaledToFill()
                .accessibilityHidden(true)
            LinearGradient(colors: [.clear, PersonalAITheme.ColorToken.background.opacity(0.24)], startPoint: .top, endPoint: .bottom)
        }.ignoresSafeArea()
    }
}

struct VishnuGenesisWordmark: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("V I S H N U")
                .font(.title3.weight(.medium))
                .foregroundStyle(PersonalAITheme.ColorToken.primaryText)
                .tracking(8)
            Rectangle()
                .fill(LinearGradient(colors: [.clear, PersonalAITheme.ColorToken.brightAccent, .clear], startPoint: .leading, endPoint: .trailing))
                .frame(width: 170, height: 1)
                .shadow(color: PersonalAITheme.ColorToken.accent.opacity(0.8), radius: 8)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Vishnu")
    }
}

struct VishnuGenesisCore: View {
    let state: String
    var size: CGFloat = 190
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotation = 0.0

    var body: some View {
        Image("vishnu-genesis-core")
        .resizable()
        .interpolation(.high)
        .scaledToFit()
        .frame(width: size, height: size)
        .rotationEffect(.degrees(rotation))
        .shadow(color: PersonalAITheme.ColorToken.accent.opacity(0.38), radius: 22)
        .accessibilityLabel("Vishnu intelligence core. \(state).")
        .onAppear { guard !reduceMotion else { return }; withAnimation(.linear(duration: 30).repeatForever(autoreverses: false)) { rotation = 360 } }
    }
}

struct VishnuGenesisInput: ViewModifier {
    func body(content: Content) -> some View {
        content
            .textFieldStyle(.plain)
            .foregroundStyle(PersonalAITheme.ColorToken.primaryText)
            .tint(PersonalAITheme.ColorToken.brightAccent)
            .padding(.horizontal, 14)
            .frame(minHeight: 56)
            .background(PersonalAITheme.ColorToken.deepBackground.opacity(0.82), in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(PersonalAITheme.ColorToken.border, lineWidth: 1))
    }
}

struct VishnuGenesisCard: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(16).background(PersonalAITheme.ColorToken.surface, in: RoundedRectangle(cornerRadius: 17))
            .overlay(RoundedRectangle(cornerRadius: 17).stroke(PersonalAITheme.ColorToken.border, lineWidth: 1))
    }
}

extension View {
    func vishnuGenesisCard() -> some View { modifier(VishnuGenesisCard()) }
    func vishnuGenesisInput() -> some View { modifier(VishnuGenesisInput()) }
}

struct VishnuGenesisButtonStyle: ButtonStyle {
    var primary = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(PersonalAITheme.Typography.control.weight(.semibold))
            .foregroundStyle(PersonalAITheme.ColorToken.primaryText)
            .padding(.horizontal, 20)
            .frame(maxWidth: .infinity, minHeight: PersonalAITheme.touchTarget + 12)
            .background {
                Capsule().fill(primary
                    ? PersonalAITheme.ColorToken.accent.opacity(configuration.isPressed ? 0.5 : 0.34)
                    : PersonalAITheme.ColorToken.deepBackground.opacity(0.78))
            }
            .overlay {
                Capsule().stroke(primary ? PersonalAITheme.ColorToken.brightAccent : PersonalAITheme.ColorToken.border, lineWidth: 1)
            }
            .shadow(color: primary ? PersonalAITheme.ColorToken.accent.opacity(configuration.isPressed ? 0.12 : 0.26) : .clear, radius: 16)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.18), value: configuration.isPressed)
    }
}
