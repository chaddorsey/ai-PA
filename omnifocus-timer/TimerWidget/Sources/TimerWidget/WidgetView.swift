import SwiftUI

// MARK: - Completing Phase

enum CompletingPhase {
    case inactive
    case slideOut
    case fadeIn
    case done
}

// MARK: - Constants

private enum WidgetLayout {
    static let width: CGFloat = 300
    static let heightCompact: CGFloat = 52
    static let heightWithNav: CGFloat = 64
    static let cornerRadius: CGFloat = 8
    static let horizontalPadding: CGFloat = 6
    static let verticalPadding: CGFloat = 4
    static let buttonSize: CGFloat = 14
    static let doneButtonSize: CGFloat = 16
    static let taskNameFont: CGFloat = 11
    static let estimateFont: CGFloat = 18
    static let unitFont: CGFloat = 8
    static let maxTaskChars = 50
    static let undoButtonSize: CGFloat = 16
    static let navDotSize: CGFloat = 5
    static let navArrowSize: CGFloat = 8
}

private enum WidgetColor {
    static let queued = Color(red: 0xA8/255, green: 0xE6/255, blue: 0xCF/255)
    static let running = Color(red: 0x34/255, green: 0xC7/255, blue: 0x59/255)
    static let paused = Color(red: 0x8E/255, green: 0x8E/255, blue: 0x93/255)
    static let completing = Color(red: 0x34/255, green: 0xC7/255, blue: 0x59/255)
    static let lastCompleted = Color(red: 0x34/255, green: 0xC7/255, blue: 0x59/255)
    static let doneGreen = Color(red: 0x26/255, green: 0x8C/255, blue: 0x26/255)
}

// MARK: - Hover Button Style

struct HoverButtonStyle: ButtonStyle {
    @State private var isHovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.white.opacity(isHovered ? 0.15 : 0.0))
                    .padding(-2)
            )
            .onHover { hovering in
                isHovered = hovering
            }
    }
}

// MARK: - Widget View

struct WidgetView: View {
    @ObservedObject var state: TimerState
    @ObservedObject var widgetFade: FadeManager
    @ObservedObject var undoFade: FadeManager
    @ObservedObject var inactivityFade: FadeManager
    var pulseOpacity: Double = 1.0
    var queuedGlowOpacity: Double = 0.0
    var completingPhase: CompletingPhase = .inactive
    var slideOutOffset: CGFloat = 0
    var fadeInOpacity: Double = 1.0

    private var effectiveOpacity: Double {
        let fade = widgetFade.isActive ? widgetFade.opacity : 1.0
        let inactivity = inactivityFade.isActive ? inactivityFade.opacity : 1.0
        return min(fade, inactivity)
    }

    private var showNav: Bool {
        state.queue.tasks.count > 1
    }

    private var widgetHeight: CGFloat {
        showNav ? WidgetLayout.heightWithNav : WidgetLayout.heightCompact
    }

    private var backgroundColor: Color {
        switch state.widgetState {
        case .idle: return .clear
        case .queued: return WidgetColor.queued
        case .running: return WidgetColor.running
        case .paused: return WidgetColor.paused
        case .completing: return WidgetColor.completing
        case .lastCompleted: return WidgetColor.lastCompleted
        }
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            mainContent
                .opacity(pulseOpacity)

            // Undo button overlay
            if state.showUndo && undoFade.isActive {
                undoButton
                    .opacity(undoFade.opacity)
                    .offset(x: -4, y: -4)
            }
        }
        .frame(width: WidgetLayout.width, height: widgetHeight)
        .opacity(effectiveOpacity)
    }

    // MARK: - Main Content

    private var mainContent: some View {
        VStack(spacing: 0) {
            // Primary row: buttons | task name | estimate
            HStack(spacing: 4) {
                buttonColumn
                taskNameView
                Spacer(minLength: 4)
                estimateColumn
            }
            .padding(.horizontal, WidgetLayout.horizontalPadding)
            .padding(.vertical, WidgetLayout.verticalPadding)

            // Navigation row
            if showNav {
                navigationRow
                    .padding(.bottom, 4)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: WidgetLayout.cornerRadius)
                .fill(backgroundColor)
        )
        .clipShape(RoundedRectangle(cornerRadius: WidgetLayout.cornerRadius))
    }

    // MARK: - Button Column

    private var buttonColumn: some View {
        VStack(spacing: 4) {
            playPauseButton
            if state.widgetState == .running || state.widgetState == .paused {
                doneButton
            }
        }
        .frame(width: 24)
    }

    @ViewBuilder
    private var playPauseButton: some View {
        if state.widgetState == .running {
            Button(action: { state.pausePressed() }) {
                Image(systemName: "pause.fill")
                    .font(.system(size: WidgetLayout.buttonSize))
                    .foregroundColor(.black)
            }
            .buttonStyle(HoverButtonStyle())
        } else if state.widgetState == .queued {
            Button(action: { state.playPressed() }) {
                ZStack {
                    // Green glow behind play button in queued state
                    Circle()
                        .fill(WidgetColor.running.opacity(0.4 + 0.3 * queuedGlowOpacity))
                        .frame(width: 22, height: 22)
                        .blur(radius: 4)
                    Image(systemName: "play.fill")
                        .font(.system(size: WidgetLayout.buttonSize))
                        .foregroundColor(.black)
                }
            }
            .buttonStyle(HoverButtonStyle())
        } else if state.widgetState == .paused {
            Button(action: { state.playPressed() }) {
                Image(systemName: "play.fill")
                    .font(.system(size: WidgetLayout.buttonSize))
                    .foregroundColor(.black)
            }
            .buttonStyle(HoverButtonStyle())
        } else {
            // lastCompleted / completing — show play if queue has items
            if !state.queue.tasks.isEmpty {
                Button(action: { state.playPressed() }) {
                    Image(systemName: "play.fill")
                        .font(.system(size: WidgetLayout.buttonSize))
                        .foregroundColor(.black)
                }
                .buttonStyle(HoverButtonStyle())
            } else {
                Color.clear.frame(width: WidgetLayout.buttonSize, height: WidgetLayout.buttonSize)
            }
        }
    }

    private var doneButton: some View {
        Button(action: { state.donePressed() }) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: WidgetLayout.doneButtonSize, weight: .semibold))
                .foregroundStyle(
                    .linearGradient(
                        colors: [WidgetColor.doneGreen, WidgetColor.doneGreen.opacity(0.8)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .shadow(color: .white.opacity(0.3), radius: 1, y: -0.5)
        }
        .buttonStyle(HoverButtonStyle())
    }

    // MARK: - Task Name

    private var taskNameView: some View {
        let displayName: String = {
            let name = state.currentTaskName
            if name.count > WidgetLayout.maxTaskChars {
                let idx = name.index(name.startIndex, offsetBy: WidgetLayout.maxTaskChars)
                return String(name[..<idx]) + "..."
            }
            return name
        }()

        return Text(displayName.isEmpty ? "No task" : displayName)
            .font(.system(size: WidgetLayout.taskNameFont, weight: .bold))
            .foregroundColor(.black)
            .lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .onTapGesture {
                state.taskNameClicked()
            }
            .offset(x: completingPhase == .slideOut ? slideOutOffset : 0)
            .opacity(completingPhase == .fadeIn ? fadeInOpacity : 1.0)
    }

    // MARK: - Estimate Column

    private var estimateColumn: some View {
        VStack(spacing: 0) {
            if let estimate = state.currentEstimateMin {
                Text("\(estimate)")
                    .font(.system(size: WidgetLayout.estimateFont, weight: .semibold))
                    .foregroundColor(.black)
                Text("min")
                    .font(.system(size: WidgetLayout.unitFont))
                    .foregroundColor(.black.opacity(0.7))
            }
        }
        .frame(width: 36)
    }

    // MARK: - Navigation Row

    private var navigationRow: some View {
        HStack(spacing: 6) {
            Spacer()

            // Left arrow
            if state.queueIndex > 0 {
                Button(action: { state.navigateQueue(direction: -1) }) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: WidgetLayout.navArrowSize, weight: .semibold))
                        .foregroundColor(.black.opacity(0.6))
                }
                .buttonStyle(HoverButtonStyle())
            }

            // Dots
            HStack(spacing: 3) {
                ForEach(0..<state.queue.tasks.count, id: \.self) { idx in
                    Circle()
                        .fill(idx == state.queueIndex ? Color.black : Color.black.opacity(0.3))
                        .frame(width: WidgetLayout.navDotSize, height: WidgetLayout.navDotSize)
                        .transition(.opacity)
                        .animation(.easeInOut(duration: 0.5), value: state.queue.tasks.count)
                }
            }

            // Right arrow
            if state.queueIndex < state.queue.tasks.count - 1 {
                Button(action: { state.navigateQueue(direction: 1) }) {
                    Image(systemName: "chevron.right")
                        .font(.system(size: WidgetLayout.navArrowSize, weight: .semibold))
                        .foregroundColor(.black.opacity(0.6))
                }
                .buttonStyle(HoverButtonStyle())
            }

            Spacer()
        }
    }

    // MARK: - Undo Button

    private var undoButton: some View {
        Button(action: { state.undoPressed() }) {
            ZStack {
                Circle()
                    .fill(Color.black.opacity(0.5))
                    .frame(width: WidgetLayout.undoButtonSize, height: WidgetLayout.undoButtonSize)
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
            }
        }
        .buttonStyle(HoverButtonStyle())
    }
}
