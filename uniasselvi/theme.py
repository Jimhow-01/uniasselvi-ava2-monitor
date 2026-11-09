"""Paleta escura + helpers de widgets flat para launcher e painel."""
import tkinter as tk
from tkinter import ttk

C = {
    "bg": "#0B1220",
    "card": "#131C2E",
    "border": "#26334D",
    "accent": "#2563EB",
    "accent_hover": "#1E55C7",
    "text": "#E6ECF7",
    "muted": "#8A97AC",
    "ok": "#34D399",
    "err": "#F87171",
    "warn": "#FBBF24",
    "input_bg": "#0E1626",
}


def make_font(root):
    root.option_add("*Font", ("Segoe UI", 10))


def apply_dark_style(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=C["bg"], foreground=C["text"],
                    fieldbackground=C["input_bg"], bordercolor=C["border"])
    style.configure("TFrame", background=C["bg"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"])
    style.configure("TNotebook", background=C["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=C["card"], foreground=C["muted"],
                    padding=(16, 8))
    style.map("TNotebook.Tab",
              background=[("selected", C["accent"])],
              foreground=[("selected", "#FFFFFF")])
    style.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=C["bg"], foreground=C["muted"],
                    borderwidth=0, font=("Segoe UI", 9, "bold"))
    style.map("Treeview",
              background=[("selected", C["accent"])],
              foreground=[("selected", "#FFFFFF")])
    style.configure("TButton", background=C["card"], foreground=C["text"],
                    bordercolor=C["border"], padding=6)
    style.map("TButton", background=[("active", C["border"])])
    style.configure("TSpinbox", background=C["input_bg"], foreground=C["text"],
                    arrowcolor=C["muted"], fieldbackground=C["input_bg"])
    style.configure("TCheckbutton", background=C["bg"], foreground=C["text"])
    style.map("TCheckbutton", background=[("active", C["bg"])])


class PlaceholderEntry(tk.Entry):
    def __init__(self, master, placeholder="", **kw):
        kw.setdefault("bg", C["input_bg"])
        kw.setdefault("fg", C["text"])
        kw.setdefault("insertbackground", C["text"])
        kw.setdefault("relief", "flat")
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", C["border"])
        kw.setdefault("highlightcolor", C["accent"])
        kw.setdefault("font", ("Segoe UI", 11))
        super().__init__(master, **kw)
        self.placeholder = placeholder
        self._show_attr = kw.get("show", "")
        self._ph_shown = False
        if placeholder:
            self._show_ph()
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)

    def _show_ph(self):
        if not self.get():
            self._ph_shown = True
            # placeholder nunca mascarado: senão a dica vira "●●●●"
            self.config(show="")
            self.insert(0, self.placeholder)
            self.config(fg=C["muted"])

    def _focus_in(self, _):
        if self._ph_shown:
            self.delete(0, "end")
            self._ph_shown = False
            self.config(fg=C["text"], show=self._show_attr)

    def _focus_out(self, _):
        if not self.get():
            self._show_ph()

    def value(self):
        return "" if self._ph_shown else self.get()

    def set_value(self, text):
        """Preenche o campo sem colidir com o placeholder."""
        self.delete(0, "end")
        self._ph_shown = False
        if text:
            self.insert(0, text)
            self.config(fg=C["text"], show=self._show_attr)
        else:
            self._show_ph()

    def set_placeholder(self, text):
        was_shown = self._ph_shown
        if was_shown:
            self.delete(0, "end")
        self.placeholder = text
        self._ph_shown = False
        if not self.get():
            self._show_ph()


def flat_button(parent, text, command, kind="primary"):
    if kind == "primary":
        bg, fg, hover = C["accent"], "#FFFFFF", C["accent_hover"]
    elif kind == "danger":
        bg, fg, hover = C["card"], C["err"], C["border"]
    else:
        bg, fg, hover = C["card"], C["text"], C["border"]
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, padx=18, pady=8,
                   font=("Segoe UI", 10, "bold"), cursor="hand2")
    lbl._base_bg, lbl._hover_bg = bg, hover

    def _enter(_):
        if lbl["state"] == "normal":
            lbl.config(bg=hover)

    def _leave(_):
        if lbl["state"] == "normal":
            lbl.config(bg=bg)

    def _click(_):
        if lbl["state"] == "normal":
            command()

    lbl.bind("<Enter>", _enter)
    lbl.bind("<Leave>", _leave)
    lbl.bind("<Button-1>", _click)
    return lbl


def set_button(btn, text=None, enabled=True):
    if text is not None:
        btn.config(text=text)
    btn.config(state="normal" if enabled else "disabled",
               cursor="hand2" if enabled else "arrow")
    if not enabled:
        btn.config(bg=C["border"], fg=C["muted"])
    else:
        btn.config(bg=btn._base_bg, fg=btn.cget("fg") if btn.cget("fg") != C["muted"] else C["text"])


def link_label(parent, text, command):
    lbl = tk.Label(parent, text=text, bg=C["bg"], fg=C["accent"],
                   font=("Segoe UI", 9, "underline"), cursor="hand2")
    lbl.bind("<Button-1>", lambda e: command())
    return lbl
