import SwiftUI

struct ConfettiParticle {
    var x: CGFloat
    var y: CGFloat
    var velocityX: CGFloat
    var velocityY: CGFloat
    var size: CGFloat
    var rotation: Double
    var rotationSpeed: Double
    var color: Color
    var opacity: Double
}

final class ConfettiState: ObservableObject {
    @Published var isActive: Bool = false
    @Published var particles: [ConfettiParticle] = []

    private var displayLink: CVDisplayLink?
    private var startTime: Date?
    private var lastUpdate: Date?

    private static let particleCount = 40
    private static let gravity: CGFloat = 400
    private static let duration: TimeInterval = 2.0
    private static let fadeStartY: CGFloat = 50

    private static let colors: [Color] = [
        .yellow, .orange, .pink, .purple, .blue, .green, .red,
    ]

    func fire(fromRect rect: CGRect) {
        var newParticles: [ConfettiParticle] = []
        for _ in 0..<Self.particleCount {
            let startX = rect.minX + CGFloat.random(in: 0...rect.width)
            let startY = rect.midY
            let goesUp = Double.random(in: 0...1) < 0.3
            let vy: CGFloat = goesUp
                ? CGFloat.random(in: -250...(-100))
                : CGFloat.random(in: -50...50)
            let particle = ConfettiParticle(
                x: startX,
                y: startY,
                velocityX: CGFloat.random(in: -120...120),
                velocityY: vy,
                size: CGFloat.random(in: 4...8),
                rotation: Double.random(in: 0...360),
                rotationSpeed: Double.random(in: -360...360),
                color: Self.colors.randomElement()!,
                opacity: 1.0
            )
            newParticles.append(particle)
        }
        particles = newParticles
        isActive = true
        startTime = Date()
        lastUpdate = Date()
        startUpdating()
    }

    func stop() {
        isActive = false
        particles = []
        startTime = nil
        lastUpdate = nil
    }

    private func startUpdating() {
        // Use a simple Timer for updates at ~60fps
        Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] timer in
            guard let self = self, self.isActive else {
                timer.invalidate()
                return
            }
            self.update()
        }
    }

    private func update() {
        guard let startTime = startTime, let lastUpdate = lastUpdate else { return }
        let now = Date()
        let dt = CGFloat(now.timeIntervalSince(lastUpdate))
        let totalElapsed = now.timeIntervalSince(startTime)
        self.lastUpdate = now

        if totalElapsed >= Self.duration {
            stop()
            return
        }

        let screenMidY: CGFloat = 400 // approximate screen midpoint below widget

        for i in particles.indices {
            particles[i].velocityY += Self.gravity * dt
            particles[i].x += particles[i].velocityX * dt
            particles[i].y += particles[i].velocityY * dt
            particles[i].rotation += particles[i].rotationSpeed * Double(dt)

            // Fade based on vertical distance traveled downward
            let distanceFallen = max(0, particles[i].y - Self.fadeStartY)
            let fadeProgress = min(distanceFallen / screenMidY, 1.0)
            particles[i].opacity = max(0, 1.0 - fadeProgress)
        }
    }
}

struct ConfettiView: View {
    @ObservedObject var confetti: ConfettiState

    var body: some View {
        Canvas { context, size in
            for particle in confetti.particles {
                guard particle.opacity > 0.01 else { continue }
                let rect = CGRect(
                    x: particle.x - particle.size / 2,
                    y: particle.y - particle.size / 2,
                    width: particle.size,
                    height: particle.size * 0.6
                )
                context.opacity = particle.opacity
                context.fill(
                    Path(rect),
                    with: .color(particle.color)
                )
            }
        }
        .allowsHitTesting(false)
    }
}
