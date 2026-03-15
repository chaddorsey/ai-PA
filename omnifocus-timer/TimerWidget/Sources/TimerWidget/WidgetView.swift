import SwiftUI

struct WidgetView: View {
    @ObservedObject var state: TimerState

    var body: some View {
        Text(state.currentTaskName.isEmpty ? "No task" : state.currentTaskName)
            .frame(width: 300, height: 64)
            .background(Color.green.opacity(0.5))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
