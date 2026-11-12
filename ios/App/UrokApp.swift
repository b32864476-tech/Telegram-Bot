import SwiftUI

@main
struct UrokApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    private let days: [Date] = {
        let today = Sched.startOfDay(Date())
        return (0..<7).compactMap { Sched.cal.date(byAdding: .day, value: $0, to: today) }
    }()

    private func title(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "ru_RU")
        f.timeZone = Sched.cal.timeZone
        f.dateFormat = "EEEE, d MMMM"
        return f.string(from: d).capitalized + " · \(Sched.weekNumber(d)) неделя"
    }

    var body: some View {
        NavigationView {
            List {
                ForEach(days, id: \.self) { day in
                    let slots = Sched.lessons(for: day)
                    if !slots.isEmpty {
                        Section(title(day)) {
                            ForEach(slots, id: \.num) { s in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text("\(s.num). \(s.lesson.name)").font(.headline)
                                        Text(s.lesson.room != nil
                                             ? "Кабинет \(s.lesson.room!), \(s.lesson.building)"
                                             : s.lesson.building)
                                            .font(.subheadline).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    Text("\(s.startStr)–\(s.endStr)")
                                        .font(.subheadline).foregroundColor(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Уроки 8-А")
        }
    }
}
