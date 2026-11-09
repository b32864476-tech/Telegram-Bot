"""Системные операции Джарвиса (кроссплатформенные: Windows / Linux / macOS)."""
import asyncio
import io
import os
import platform
import shutil
import subprocess
import time

import psutil

OS = platform.system()  # 'Windows' | 'Linux' | 'Darwin'


def human(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ПБ"


def status_text() -> str:
    vm = psutil.virtual_memory()
    boot = time.time() - psutil.boot_time()
    d, rem = divmod(int(boot), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    lines = [
        f"🖥 {platform.node()} ({OS} {platform.release()})",
        f"⏱ Аптайм: {d}д {h}ч {m}м",
        f"🧠 CPU: {psutil.cpu_percent(interval=0.5)}%",
        f"💾 RAM: {vm.percent}% ({human(vm.used)} / {human(vm.total)})",
    ]
    try:
        root = os.path.abspath(os.sep)
        du = psutil.disk_usage(root)
        lines.append(f"📀 Диск {root}: {du.percent}% ({human(du.used)} / {human(du.total)})")
    except Exception:
        pass
    bat = getattr(psutil, "sensors_battery", lambda: None)()
    if bat:
        lines.append(f"🔋 Батарея: {bat.percent:.0f}% {'(заряжается)' if bat.power_plugged else ''}")
    return "\n".join(lines)


def screenshot_png() -> bytes:
    import mss
    import mss.tools

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[0])  # все мониторы
        return mss.tools.to_png(shot.rgb, shot.size)


def top_processes(n: int = 10) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except psutil.Error:
            pass
    time.sleep(0.5)
    rows = []
    for p in procs:
        try:
            rows.append((p.cpu_percent(None), p.info["memory_percent"] or 0, p.info["pid"], p.info["name"]))
        except psutil.Error:
            pass
    rows.sort(reverse=True)
    out = ["PID     CPU%   MEM%  Имя"]
    for cpu, mem, pid, name in rows[:n]:
        out.append(f"{pid:<7} {cpu:>5.1f} {mem:>5.1f}  {name}")
    return "\n".join(out)


def kill_process(target: str) -> str:
    """target — PID или имя процесса."""
    killed = []
    if target.isdigit():
        victims = [psutil.Process(int(target))]
    else:
        victims = [p for p in psutil.process_iter(["name"])
                   if (p.info["name"] or "").lower() == target.lower()]
    for p in victims:
        try:
            name = p.name()
            p.terminate()
            killed.append(f"{name} ({p.pid})")
        except psutil.Error as e:
            killed.append(f"ошибка {p.pid}: {e}")
    return "Завершено: " + ", ".join(killed) if killed else "Процесс не найден"


def lock() -> None:
    if OS == "Windows":
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif OS == "Darwin":
        subprocess.Popen(["pmset", "displaysleepnow"])
    else:
        subprocess.Popen("loginctl lock-session || xdg-screensaver lock", shell=True)


def power(action: str) -> None:
    cmds = {
        "Windows": {
            "shutdown": ["shutdown", "/s", "/t", "5"],
            "reboot": ["shutdown", "/r", "/t", "5"],
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "cancel": ["shutdown", "/a"],
        },
        "Linux": {
            "shutdown": ["systemctl", "poweroff"],
            "reboot": ["systemctl", "reboot"],
            "sleep": ["systemctl", "suspend"],
            "cancel": ["shutdown", "-c"],
        },
        "Darwin": {
            "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
            "reboot": ["osascript", "-e", 'tell app "System Events" to restart'],
            "sleep": ["pmset", "sleepnow"],
            "cancel": ["true"],
        },
    }
    subprocess.Popen(cmds[OS][action])


def open_target(target: str) -> None:
    """Открыть приложение, файл или URL."""
    if OS == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]
    elif OS == "Darwin":
        subprocess.Popen(["open", target] if os.path.exists(target) or "://" in target
                         else ["open", "-a", target])
    else:
        if shutil.which(target):
            subprocess.Popen([target])
        else:
            subprocess.Popen(["xdg-open", target])


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))
    if OS == "Linux":
        subprocess.run(["amixer", "-q", "sset", "Master", f"{percent}%"], check=True)
    elif OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {percent}"], check=True)
    else:
        raise RuntimeError("Регулировка громкости на Windows требует pycaw (не установлен)")
    return f"🔊 Громкость: {percent}%"


async def run_shell(cmd: str, timeout: int) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return f"⏰ Таймаут {timeout}с, процесс убит"
    text = out.decode(errors="replace").strip() or "(нет вывода)"
    return f"{text}\n[код выхода: {proc.returncode}]"
