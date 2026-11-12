import Foundation

// Расписание 8-А (экономическая группа), недели 1–4.
// Пара = 2 урока подряд. .both — одно и то же на оба урока,
// .split(a, b) — a на первый урок пары, b на второй (nil = урока нет).

struct Lesson: Hashable {
    let name: String
    let room: Int?
    let building: String
}

enum Pair {
    case both(Lesson)
    case split(Lesson?, Lesson?)
}

func P(_ name: String, _ room: Int? = nil) -> Lesson {
    Lesson(name: name, room: room, building: "Поштова")
}
func Sh(_ name: String, _ room: Int? = nil) -> Lesson {
    Lesson(name: name, room: room, building: "Штейнбарга")
}
func Li(_ name: String) -> Lesson {
    Lesson(name: name, room: nil, building: "Лицей 12")
}

let bells: [(String, String)] = [
    ("08:15", "09:00"), ("09:05", "09:50"),
    ("10:05", "10:50"), ("10:55", "11:40"),
    ("12:00", "12:45"), ("12:50", "13:35"),
    ("13:50", "14:35"), ("14:40", "15:25"),
]

let schedule: [Int: [[Pair]]] = [
    1: [
        [.both(P("ЗБД", 17)), .split(P("Мистецтво", 17), P("ГО", 17)), .both(Sh("Біологія", 15)), .both(P("Фізкультура"))],
        [.both(P("Алгебра", 16)), .both(P("Укр. література", 14)), .both(Sh("Інформатика", 13)), .both(P("Географія", 7))],
        [.both(Li("Фізика")), .both(Li("Хімія")), .both(P("Зарубіжна літ.", 6)), .both(P("Геометрія", 13))],
        [.both(Li("Підприємництво")), .both(Li("Англійська")), .both(P("Економіка", 3)), .both(P("Алгебра", 16))],
        [.both(P("Укр. мова", 13)), .both(Sh("Історія", 15)), .both(P("Фізкультура"))],
    ],
    2: [
        [.split(nil, Li("Біологія")), .both(Li("Мистецтво")), .both(P("Біологія", 17))],
        [.both(P("Алгебра", 16)), .both(P("Укр. мова", 8)), .both(P("Географія", 8)), .both(P("Фізкультура"))],
        [.both(Li("Фізика")), .both(Li("Хімія")), .both(P("Геометрія", 12))],
        [.both(Sh("Інформатика", 13)), .both(Li("Англійська")), .both(P("Економіка", 3)), .both(P("Алгебра", 17))],
        [.both(P("Історія", 8)), .both(P("Англійська", 16)), .both(P("Робототехніка", 1))],
    ],
    3: [
        [.both(Sh("Інформатика", 13)), .split(Sh("Мистецтво", 12), Sh("ГО", 12)), .both(P("Біологія", 18))],
        [.both(P("Алгебра", 11)), .both(P("Укр. література", 17)), .both(Sh("Інформатика", 13)), .both(P("Географія", 6))],
        [.both(P("Фізика", 7)), .both(P("Хімія", 17)), .both(P("Зарубіжна літ.", 17)), .both(P("Геометрія", 12))],
        [.both(Li("Підприємництво")), .both(P("Англійська", 16)), .both(P("Економіка", 4)), .both(P("Алгебра", 7))],
        [.both(P("Укр. мова", 13)), .both(P("Історія", 14)), .both(P("Фізкультура"))],
    ],
    4: [
        [.both(P("Укр. мова", 11)), .split(P("Мистецтво", 6), P("Біологія", 6)), .split(Sh("Зарубіжна літ.", 15), nil)],
        [.both(P("Алгебра", 12)), .both(P("Укр. література", 7)), .both(P("Географія", 8)), .both(P("Фізкультура"))],
        [.both(Sh("Фізика", 12)), .both(P("Хімія", 18)), .both(P("Геометрія", 11)), .both(P("Фізкультура"))],
        [.both(Sh("Інформатика", 13)), .both(P("Англійська", 11)), .both(P("Економіка", 3)), .both(P("Алгебра", 13))],
        [.both(P("Історія", 8)), .both(P("Англійська", 13)), .both(P("Робототехніка", 5))],
    ],
]

struct LessonSlot {
    let lesson: Lesson
    let num: Int
    let start: Date
    let end: Date
    let startStr: String
    let endStr: String
}

struct LessonState {
    let slot: LessonSlot
    let current: Bool
    let dayOffset: Int
    let week: Int
    let day: Date
}

enum Sched {
    static let cal: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "Europe/Kyiv") ?? .current
        return c
    }()

    // 9 ноября 2026 — начало 2-й недели
    static let week2Monday: Date = cal.date(from: DateComponents(year: 2026, month: 11, day: 9))!

    static func startOfDay(_ d: Date) -> Date { cal.startOfDay(for: d) }

    // 0 = понедельник … 6 = воскресенье
    static func weekdayIndex(_ d: Date) -> Int {
        (cal.component(.weekday, from: d) + 5) % 7
    }

    static func mondayOf(_ d: Date) -> Date {
        let s = startOfDay(d)
        return cal.date(byAdding: .day, value: -weekdayIndex(s), to: s)!
    }

    static func weekNumber(_ d: Date) -> Int {
        let days = cal.dateComponents([.day], from: week2Monday, to: mondayOf(d)).day ?? 0
        let diff = Int((Double(days) / 7.0).rounded())
        return (((diff + 1) % 4) + 4) % 4 + 1   // diff 0 -> 2, 1 -> 3, 2 -> 4, 3 -> 1
    }

    static func at(_ day: Date, _ hhmm: String) -> Date {
        let p = hhmm.split(separator: ":").map { Int($0) ?? 0 }
        return cal.date(bySettingHour: p[0], minute: p[1], second: 0, of: day)!
    }

    static func lessons(for day: Date) -> [LessonSlot] {
        let wd = weekdayIndex(day)
        guard wd <= 4, let days = schedule[weekNumber(day)], wd < days.count else { return [] }
        var out: [LessonSlot] = []
        for (i, pair) in days[wd].enumerated() {
            let two: [Lesson?]
            switch pair {
            case .both(let l): two = [l, l]
            case .split(let a, let b): two = [a, b]
            }
            for k in 0..<2 {
                guard let l = two[k] else { continue }
                let idx = i * 2 + k
                guard idx < bells.count else { continue }
                out.append(LessonSlot(
                    lesson: l, num: idx + 1,
                    start: at(day, bells[idx].0), end: at(day, bells[idx].1),
                    startStr: bells[idx].0, endStr: bells[idx].1))
            }
        }
        return out
    }

    // Текущий урок или ближайший следующий
    static func next(from now: Date) -> LessonState? {
        let today = startOfDay(now)
        for off in 0..<15 {
            let day = cal.date(byAdding: .day, value: off, to: today)!
            for slot in lessons(for: day) where slot.end > now {
                return LessonState(slot: slot, current: slot.start <= now,
                                   dayOffset: off, week: weekNumber(day), day: day)
            }
        }
        return nil
    }

    static func label(_ s: LessonState) -> String {
        if s.current { return "СЕЙЧАС" }
        if s.dayOffset == 0 { return "СЛЕДУЮЩИЙ УРОК" }
        if s.dayOffset == 1 { return "ЗАВТРА" }
        let names = ["В ПОНЕДЕЛЬНИК", "ВО ВТОРНИК", "В СРЕДУ", "В ЧЕТВЕРГ", "В ПЯТНИЦУ"]
        let i = weekdayIndex(s.day)
        return i < names.count ? names[i] : "СЛЕДУЮЩИЙ УРОК"
    }
}
