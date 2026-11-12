import WidgetKit
import SwiftUI

struct UrokEntry: TimelineEntry {
    let date: Date
    let state: LessonState?
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> UrokEntry {
        UrokEntry(date: Date(), state: Sched.next(from: Date()))
    }

    func getSnapshot(in context: Context, completion: @escaping (UrokEntry) -> Void) {
        completion(UrokEntry(date: Date(), state: Sched.next(from: Date())))
    }

    // Заранее отдаём iOS все смены на 14 дней вперёд:
    // виджет переключается точно по времени, без фоновых обновлений.
    func getTimeline(in context: Context, completion: @escaping (Timeline<UrokEntry>) -> Void) {
        let now = Date()
        let today = Sched.startOfDay(now)
        var dates: Set<Date> = [now]
        for off in 0..<14 {
            let day = Sched.cal.date(byAdding: .day, value: off, to: today)!
            if let m = Sched.cal.date(bySettingHour: 0, minute: 1, second: 0, of: day), m > now {
                dates.insert(m)
            }
            for s in Sched.lessons(for: day) {
                if s.start > now { dates.insert(s.start) }
                if s.end > now { dates.insert(s.end) }
            }
        }
        let sorted = dates.sorted()
        let entries = sorted.map { UrokEntry(date: $0, state: Sched.next(from: $0)) }
        let reload = (sorted.last ?? now).addingTimeInterval(60)
        completion(Timeline(entries: entries, policy: .after(reload)))
    }
}

private let gray = Color(red: 0.545, green: 0.576, blue: 0.655)
private let accent = Color(red: 0.22, green: 0.71, blue: 1.0)

struct UrokView: View {
    let entry: UrokEntry

    var body: some View {
        if let s = entry.state {
            content(s)
        } else {
            Text("Уроков нет")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(.white)
        }
    }

    @ViewBuilder
    private func content(_ s: LessonState) -> some View {
        let l = s.slot.lesson
        VStack(alignment: .leading, spacing: 0) {
            Text(Sched.label(s))
                .font(.system(size: 11, weight: .heavy))
                .foregroundColor(gray)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Spacer().frame(height: 6)
            Text("\(s.slot.num)-Й УРОК · \(s.slot.startStr)–\(s.slot.endStr)")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(accent)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
            Spacer(minLength: 4)
            Text(l.name)
                .font(.system(size: 24, weight: .bold))
                .foregroundColor(.white)
                .lineLimit(2)
                .minimumScaleFactor(0.5)
            Spacer().frame(height: 7)
            HStack(spacing: 6) {
                Image(systemName: "location.fill")
                    .font(.system(size: 11))
                    .foregroundColor(accent)
                Text(l.room != nil ? "Кабинет \(l.room!)" : l.building)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.white.opacity(0.14), lineWidth: 1))
            Spacer().frame(height: 8)
            HStack {
                Text(l.room != nil ? l.building : "")
                Spacer()
                Text("\(s.week) неделя")
            }
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(gray)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

@main
struct UrokWidget: Widget {
    let kind = "UrokWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: Provider()) { entry in
            UrokView(entry: entry)
                .containerBackground(for: .widget) {
                    LinearGradient(
                        colors: [Color(red: 0.05, green: 0.063, blue: 0.09),
                                 Color(red: 0.11, green: 0.13, blue: 0.19)],
                        startPoint: .top, endPoint: .bottom)
                }
        }
        .configurationDisplayName("Следующий урок")
        .description("Текущий или следующий урок и где он проходит.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
