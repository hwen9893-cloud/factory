"""Operating-system integration kept out of GUI and Core modules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def open_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def choose_directory(*, title: str, initial: Path | None = None) -> Path | None:
    """Show the host OS directory picker; never require users to type a path."""
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(
            parent=root,
            title=title,
            initialdir=str(initial) if initial and initial.exists() else None,
            mustexist=True,
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


class SingleInstance:
    """Best-effort named mutex on Windows; a no-op on other platforms."""

    def __init__(self, name: str = "Local\\StoryFactoryDesktop") -> None:
        self.name = name
        self.handle: Any = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        import ctypes

        self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        return bool(self.handle) and ctypes.windll.kernel32.GetLastError() != 183

    def release(self) -> None:
        if self.handle and sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


def show_error_dialog(title: str, message: str, *, log_dir: Path | None = None) -> None:
    """Display a final fallback when the GUI cannot be started."""
    if sys.platform == "win32":
        import ctypes

        suffix = "\n\n选择“是”打开日志目录。" if log_dir else ""
        flags = 0x10 | (0x04 if log_dir else 0x00)  # error icon + Yes/No or OK
        result = ctypes.windll.user32.MessageBoxW(None, message + suffix, title, flags)
        if log_dir and result == 6:
            open_directory(log_dir)
        return
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        pass

