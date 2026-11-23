"""Эмуляция настоящей клавиатуры и мыши на компьютере.

Клавиши приходят с телефона как физические коды (`KeyboardEvent.code`:
KeyA, Digit1, ShiftLeft, ...). Буквы и символы нажимаются по *положению*
на клавиатуре, а не по символу — поэтому, как у реальной клавиатуры,
результат зависит от раскладки, выбранной на компьютере (EN/RU), и
сочетания вроде Ctrl+C работают в любой раскладке.
"""
from __future__ import annotations

import logging
import platform
import sys

log = logging.getLogger("keyboard")

if sys.platform == "win32":
    OS = "windows"
elif sys.platform == "darwin":
    OS = "mac"
else:
    OS = "linux"

# Символьные клавиши: code -> (символ US-раскладки, VK Windows, kVK macOS)
CHAR_KEYS: dict[str, tuple[str, int, int]] = {
    "KeyA": ("a", 0x41, 0x00), "KeyB": ("b", 0x42, 0x0B), "KeyC": ("c", 0x43, 0x08),
    "KeyD": ("d", 0x44, 0x02), "KeyE": ("e", 0x45, 0x0E), "KeyF": ("f", 0x46, 0x03),
    "KeyG": ("g", 0x47, 0x05), "KeyH": ("h", 0x48, 0x04), "KeyI": ("i", 0x49, 0x22),
    "KeyJ": ("j", 0x4A, 0x26), "KeyK": ("k", 0x4B, 0x28), "KeyL": ("l", 0x4C, 0x25),
    "KeyM": ("m", 0x4D, 0x2E), "KeyN": ("n", 0x4E, 0x2D), "KeyO": ("o", 0x4F, 0x1F),
    "KeyP": ("p", 0x50, 0x23), "KeyQ": ("q", 0x51, 0x0C), "KeyR": ("r", 0x52, 0x0F),
    "KeyS": ("s", 0x53, 0x01), "KeyT": ("t", 0x54, 0x11), "KeyU": ("u", 0x55, 0x20),
    "KeyV": ("v", 0x56, 0x09), "KeyW": ("w", 0x57, 0x0D), "KeyX": ("x", 0x58, 0x07),
    "KeyY": ("y", 0x59, 0x10), "KeyZ": ("z", 0x5A, 0x06),
    "Digit1": ("1", 0x31, 0x12), "Digit2": ("2", 0x32, 0x13), "Digit3": ("3", 0x33, 0x14),
    "Digit4": ("4", 0x34, 0x15), "Digit5": ("5", 0x35, 0x17), "Digit6": ("6", 0x36, 0x16),
    "Digit7": ("7", 0x37, 0x1A), "Digit8": ("8", 0x38, 0x1C), "Digit9": ("9", 0x39, 0x19),
    "Digit0": ("0", 0x30, 0x1D),
    "Minus": ("-", 0xBD, 0x1B), "Equal": ("=", 0xBB, 0x18),
    "BracketLeft": ("[", 0xDB, 0x21), "BracketRight": ("]", 0xDD, 0x1E),
    "Backslash": ("\\", 0xDC, 0x2A), "Semicolon": (";", 0xBA, 0x29),
    "Quote": ("'", 0xDE, 0x27), "Backquote": ("`", 0xC0, 0x32),
    "Comma": (",", 0xBC, 0x2B), "Period": (".", 0xBE, 0x2F), "Slash": ("/", 0xBF, 0x2C),
}

# Служебные клавиши: code -> имя в pynput.keyboard.Key
SPECIAL_KEYS: dict[str, str] = {
    "Escape": "esc", "Tab": "tab", "CapsLock": "caps_lock", "Space": "space",
    "Enter": "enter", "Backspace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "PageUp": "page_up", "PageDown": "page_down",
    "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right",
    "ShiftLeft": "shift_l", "ShiftRight": "shift_r",
    "ControlLeft": "ctrl_l", "ControlRight": "ctrl_r",
    "AltLeft": "alt_l", "AltRight": "alt_r",
    "MetaLeft": "cmd_l", "MetaRight": "cmd_r",
    "ContextMenu": "menu", "PrintScreen": "print_screen", "ScrollLock": "scroll_lock",
    "Pause": "pause", "NumLock": "num_lock",
    "AudioVolumeUp": "media_volume_up", "AudioVolumeDown": "media_volume_down",
    "AudioVolumeMute": "media_volume_mute", "MediaPlayPause": "media_play_pause",
    "MediaTrackNext": "media_next", "MediaTrackPrevious": "media_previous",
    **{f"F{i}": f"f{i}" for i in range(1, 21)},
}

# Псевдоклавиша «Mod»: Cmd на Mac, Ctrl на Windows/Linux
MOD_ALIAS = {"Mod": "MetaLeft" if OS == "mac" else "ControlLeft"}

# Комбинация переключения раскладки на компьютере
LAYOUT_SWITCH = {
    "windows": ["MetaLeft", "Space"],
    "mac": ["ControlLeft", "Space"],
    "linux": ["MetaLeft", "Space"],
}[OS]


class DryRun:
    """Заглушка без реального ввода — для проверки без доступа к экрану."""

    def __getattr__(self, name):
        def fn(*args, **kwargs):
            log.info("dry-run %s %s", name, args)
        return fn


class Backend:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        if dry_run:
            self.kb = self.mouse = DryRun()
            self._Key = self._KeyCode = self._Button = None
            return
        from pynput import keyboard, mouse  # импорт здесь: нужен доступ к экрану

        self.kb = keyboard.Controller()
        self.mouse = mouse.Controller()
        self._Key = keyboard.Key
        self._KeyCode = keyboard.KeyCode
        self._Button = mouse.Button

    # ---------- клавиатура ----------
    def resolve(self, code: str):
        code = MOD_ALIAS.get(code, code)
        if self.dry_run:
            return code
        if code in SPECIAL_KEYS:
            key = getattr(self._Key, SPECIAL_KEYS[code], None)
            if key is None and code.endswith(("Left", "Right")):
                # например, alt_r может отсутствовать — берём общий модификатор
                key = getattr(self._Key, SPECIAL_KEYS[code][:-2], None)
            return key
        if code in CHAR_KEYS:
            char, vk_win, vk_mac = CHAR_KEYS[code]
            if OS == "windows":
                return self._KeyCode.from_vk(vk_win)
            if OS == "mac":
                return self._KeyCode.from_vk(vk_mac)
            return self._KeyCode.from_char(char)
        return None

    def down(self, code: str) -> bool:
        key = self.resolve(code)
        if key is None:
            log.warning("неизвестная клавиша: %s", code)
            return False
        self.kb.press(key)
        return True

    def up(self, code: str) -> bool:
        key = self.resolve(code)
        if key is None:
            return False
        self.kb.release(key)
        return True

    def tap(self, code: str):
        if self.down(code):
            self.up(code)

    def combo(self, codes: list[str]):
        pressed = []
        try:
            for c in codes:
                if self.down(c):
                    pressed.append(c)
        finally:
            for c in reversed(pressed):
                self.up(c)

    def type_text(self, text: str):
        """Набор произвольного текста (любой язык, эмодзи) независимо от раскладки."""
        for ch in text:
            if ch == "\n":
                self.tap("Enter")
            elif ch == "\t":
                self.tap("Tab")
            else:
                self.kb.type(ch)

    # ---------- мышь ----------
    def _btn(self, name: str):
        if self.dry_run:
            return name
        return {"left": self._Button.left, "right": self._Button.right,
                "middle": self._Button.middle}.get(name, self._Button.left)

    def move(self, dx: float, dy: float):
        self.mouse.move(int(round(dx)), int(round(dy)))

    def click(self, button: str = "left", count: int = 1):
        self.mouse.click(self._btn(button), max(1, min(int(count), 3)))

    def mouse_down(self, button: str = "left"):
        self.mouse.press(self._btn(button))

    def mouse_up(self, button: str = "left"):
        self.mouse.release(self._btn(button))

    def scroll(self, dx: int, dy: int):
        self.mouse.scroll(int(dx), int(dy))


def os_label() -> str:
    return f"{OS} ({platform.platform(terse=True)})"
