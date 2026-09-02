from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .core import MacroEvent
from .linux_input import InputPlayer, InputRecorder, InputUnavailable


class MacroRecorderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.recorder = InputRecorder()
        self.player = InputPlayer()
        self.macro: tuple[MacroEvent, ...] = ()
        self.state = "idle"

        root.title("Macro Recorder")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)

        panel = tk.Frame(root, bg="#202124", padx=8, pady=8)
        panel.pack()

        self.record_button = self._button(
            panel, "●  REC", "#b3261e", "#d93025", self.record
        )
        self.play_button = self._button(
            panel, "▶  PLAY", "#137333", "#188038", self.play
        )
        self.stop_button = self._button(
            panel, "■  STOP", "#4f5358", "#656a70", self.stop
        )

        self.record_button.grid(row=0, column=0, padx=(0, 6))
        self.play_button.grid(row=0, column=1, padx=6)
        self.stop_button.grid(row=0, column=2, padx=(6, 0))
        self._show_state("idle")

    @staticmethod
    def _button(
        parent: tk.Widget,
        text: str,
        color: str,
        active_color: str,
        command: object,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=9,
            height=2,
            font=("DejaVu Sans", 10, "bold"),
            fg="white",
            bg=color,
            activeforeground="white",
            activebackground=active_color,
            disabledforeground="#9aa0a6",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )

    def record(self) -> None:
        try:
            self.recorder.start()
        except (InputUnavailable, OSError) as error:
            messagebox.showerror("Registrazione non disponibile", str(error))
            return

        self.macro = ()
        self._show_state("recording")

    def play(self) -> None:
        try:
            self.player.start(self.macro, self._playback_finished)
        except (InputUnavailable, OSError) as error:
            messagebox.showerror("Riproduzione non disponibile", str(error))
            return

        self._show_state("playing")

    def stop(self) -> None:
        if self.state == "recording":
            try:
                self.macro = self.recorder.stop(discard_last_stop_click=True)
            except InputUnavailable as error:
                messagebox.showerror("Registrazione interrotta", str(error))
                self.macro = ()
            self._show_state("ready" if self.macro else "idle")
        elif self.state == "playing":
            self.player.stop()
            self._show_state("ready")

    def _playback_finished(self, error: Exception | None) -> None:
        try:
            self.root.after(0, self._handle_playback_finished, error)
        except tk.TclError:
            pass

    def _handle_playback_finished(self, error: Exception | None) -> None:
        if error is not None:
            messagebox.showerror("Riproduzione interrotta", str(error))
        if self.root.winfo_exists():
            self._show_state("ready" if self.macro else "idle")

    def _show_state(self, state: str) -> None:
        self.state = state
        self.record_button.configure(state=tk.NORMAL if state in {"idle", "ready"} else tk.DISABLED)
        self.play_button.configure(state=tk.NORMAL if state == "ready" else tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL if state in {"recording", "playing"} else tk.DISABLED)

        titles = {
            "idle": "Macro Recorder",
            "ready": "Macro Recorder — pronto",
            "recording": "Macro Recorder — registrazione",
            "playing": "Macro Recorder — loop",
        }
        self.root.title(titles[state])

    def close(self) -> None:
        if self.recorder.active:
            self.recorder.stop()
        if self.player.active:
            self.player.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MacroRecorderApp(root)
    root.mainloop()

