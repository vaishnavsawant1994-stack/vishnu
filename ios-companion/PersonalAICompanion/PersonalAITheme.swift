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
        static let softAccent = Color(red: 164/255, green: 226/255, blue: 1)
        static let primaryText = Color(red: 245/255, green: 250/255, blue: 1)
        static let secondaryText = Color(red: 167/255, green: 186/255, blue: 203/255)
        static let mutedText = Color(red: 104/255, green: 127/255, blue: 148/255)
        static let border = Color(red: 61/255, green: 174/255, blue: 235/255).opacity(0.30)
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
            RadialGradient(colors: [PersonalAITheme.ColorToken.accent.opacity(0.22), .clear], center: .topLeading, startRadius: 20, endRadius: 420)
            RadialGradient(colors: [PersonalAITheme.ColorToken.accent.opacity(0.18), .clear], center: .topTrailing, startRadius: 20, endRadius: 430)
            Canvas { context, size in
                for index in 0..<52 {
                    let x = CGFloat((index * 83) % 997) / 997 * size.width
                    let y = CGFloat((index * 137) % 991) / 991 * size.height
                    context.fill(Path(ellipseIn: CGRect(x: x, y: y, width: index % 7 == 0 ? 2 : 1, height: index % 7 == 0 ? 2 : 1)), with: .color(PersonalAITheme.ColorToken.softAccent.opacity(0.6)))
                }
            }.accessibilityHidden(true)
        }.ignoresSafeArea()
    }
}

struct VishnuGenesisCore: View {
    let state: String
    var size: CGFloat = 190
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotation = 0.0

    var body: some View {
        ZStack {
            Circle().fill(RadialGradient(colors: [.white, PersonalAITheme.ColorToken.brightAccent.opacity(0.65), PersonalAITheme.ColorToken.deepBackground.opacity(0.86)], center: .center, startRadius: 1, endRadius: size / 2))
            Canvas { context, canvas in
                for index in 0..<42 {
                    let x = CGFloat((index * 37) % 101) / 101 * canvas.width
                    let y = CGFloat((index * 53) % 103) / 103 * canvas.height
                    let dot = CGRect(x: x, y: y, width: index % 5 == 0 ? 5 : 3, height: index % 5 == 0 ? 5 : 3)
                    context.fill(Path(ellipseIn: dot), with: .color(PersonalAITheme.ColorToken.softAccent))
                    if index > 0 {
                        var path = Path(); path.move(to: CGPoint(x: x, y: y)); path.addLine(to: CGPoint(x: canvas.width - x, y: canvas.height - y))
                        context.stroke(path, with: .color(PersonalAITheme.ColorToken.brightAccent.opacity(0.22)), lineWidth: 0.55)
                    }
                }
            }.clipShape(Circle()).rotationEffect(.degrees(rotation))
            Ellipse().stroke(PersonalAITheme.ColorToken.brightAccent.opacity(0.75), lineWidth: 1).frame(width: size * 1.1, height: size * 0.38).rotationEffect(.degrees(16))
            Ellipse().stroke(PersonalAITheme.ColorToken.brightAccent.opacity(0.5), lineWidth: 1).frame(width: size * 1.06, height: size * 0.34).rotationEffect(.degrees(-48))
        }
        .frame(width: size, height: size)
        .overlay(Circle().stroke(PersonalAITheme.ColorToken.softAccent.opacity(0.88), lineWidth: 1))
        .shadow(color: PersonalAITheme.ColorToken.accent.opacity(0.38), radius: 22)
        .accessibilityLabel("Vishnu intelligence core. \(state).")
        .onAppear { guard !reduceMotion else { return }; withAnimation(.linear(duration: 30).repeatForever(autoreverses: false)) { rotation = 360 } }
    }
}

struct VishnuGenesisCard: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(16).background(PersonalAITheme.ColorToken.surface, in: RoundedRectangle(cornerRadius: 17))
            .overlay(RoundedRectangle(cornerRadius: 17).stroke(PersonalAITheme.ColorToken.border, lineWidth: 1))
    }
}

extension View { func vishnuGenesisCard() -> some View { modifier(VishnuGenesisCard()) } }
