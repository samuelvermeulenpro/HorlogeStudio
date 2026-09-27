#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Horloge de studio
=================

Horloge murale numérique inspirée du modèle Orium (anneau de points +
affichage digital), redessinée comme exemple aux couleurs de la marque Radio Mercure
(bleu / orange), pour affichage sur un poste sous Debian + XFCE4.

Dépendances : uniquement la bibliothèque standard Python 3 (Tkinter).
Testé pour Python 3.7+ / Tk 8.6.

Utilisation
-----------
    python3 horloge_studio.py                # plein écran, 24h
    python3 horloge_studio.py --window        # fenêtré
    python3 horloge_studio.py --size 900x900  # taille fenêtrée
    python3 horloge_studio.py --12h           # affichage 12h AM/PM
    python3 horloge_studio.py --no-seconds    # masque le compteur secondes
    python3 horloge_studio.py --no-logo       # masque le bandeau
    python3 horloge_studio.py --window --borderless --opacity 0.85
                                               # fenêtré, sans bordures, semi-transparent
    python3 horloge_studio.py --window --shaped
                                               # fenêtré, DÉCOUPÉ en cercle : le carré
                                               # noir disparaît, seul le cercle reste
                                               # visible (Linux/X11 : extension XShape ;
                                               # Windows : couleur-clé -transparentcolor,
                                               # native et sans artefact au déplacement)

Raccourcis clavier (une fois l'appli lancée)
---------------------------------------------
    Échap / q   -> quitter
    F11 / f     -> bascule plein écran / fenêtré
    t           -> bascule épinglage au premier plan (activé par défaut)
    + / -       -> augmenter / diminuer l'opacité de la fenêtre
    o           -> bascule opacité totale <-> semi-transparente
    (en mode --borderless : cliquer-glisser n'importe où pour déplacer la fenêtre ;
     survoler le cercle fait apparaître une petite croix en haut à droite pour
     quitter au clic — utile si le focus clavier ne répond pas)

Note sur --shaped
------------------
    Ce mode découpe réellement la fenêtre à la forme du cercle via
    l'extension X11 "Shape" (libX11 / libXext, présentes par défaut sur
    Debian). En dehors du cercle, il n'y a plus de fenêtre du tout : pas
    de carré noir, pas de transparence "voilée" — juste le bureau ou ce
    qu'il y a derrière. Fonctionne sans compositeur ; avec un compositeur
    actif (xfwm4 > Paramètres > Gestionnaire de fenêtres > Compositeur),
    le contour du cercle est lissé au lieu d'être crénelé. Implique
    --window --borderless. Si les bibliothèques X11 sont introuvables,
    l'appli bascule automatiquement sur la fenêtre carrée classique.
"""

import argparse
import ctypes
import ctypes.util
import math
import sys
import tkinter as tk
from datetime import datetime

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

# Couleur-clé utilisée pour la transparence native Windows (-transparentcolor).
# Choisie pour ne jamais apparaître ailleurs dans le dessin de l'horloge.
TRANSPARENT_KEY = "#ff00fe"

# ---------------------------------------------------------------------------
# Découpe de fenêtre circulaire (X11 Shape extension) — optionnel, Linux only
# ---------------------------------------------------------------------------
_SHAPE_BOUNDING = 0
_SHAPE_INPUT = 2
_SHAPE_SET = 0


class _X11ShapeUnavailable(Exception):
    pass


def _load_x11_shape_libs():
    """Charge libX11 / libXext via ctypes. Lève _X11ShapeUnavailable si
    indisponible (plateforme non-Linux, bibliothèques absentes, etc.)."""
    def _load(soname_base):
        # find_library() dépend souvent des symlinks fournis par les paquets
        # -dev (absents sur un système "normal") : on tente d'abord les noms
        # de bibliothèque partagée réels, présents même sans paquets -dev.
        candidates = [
            f"lib{soname_base}.so.6",
            f"lib{soname_base}.so",
            ctypes.util.find_library(soname_base),
        ]
        last_error = None
        for name in candidates:
            if not name:
                continue
            try:
                return ctypes.CDLL(name)
            except OSError as exc:
                last_error = exc
        raise _X11ShapeUnavailable(f"lib{soname_base} introuvable ({last_error})")

    x11 = _load("X11")
    xext = _load("Xext")

    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XCreatePixmap.restype = ctypes.c_ulong
    x11.XCreatePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                   ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    x11.XCreateGC.restype = ctypes.c_void_p
    x11.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                               ctypes.c_ulong, ctypes.c_void_p]
    x11.XSetForeground.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    x11.XFillRectangle.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    x11.XFillArc.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                              ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                              ctypes.c_int, ctypes.c_int]
    x11.XFreeGC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    xext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
    return x11, xext


def apply_circular_window_shape(tk_window_id, width, height, margin=2):
    """Découpe la fenêtre X11 d'id `tk_window_id` en cercle inscrit dans
    (width, height) : en dehors du disque, la fenêtre cesse d'exister
    (plus de rendu, plus de clics) — c'est le bureau/l'arrière-plan qui
    apparaît, pas une couleur. Ne lève jamais d'exception : retourne
    True en cas de succès, False sinon (et affiche un avertissement)."""
    try:
        x11, xext = _load_x11_shape_libs()
        display = x11.XOpenDisplay(None)
        if not display:
            raise _X11ShapeUnavailable("connexion au serveur X impossible")

        root = x11.XDefaultRootWindow(display)
        pixmap = x11.XCreatePixmap(display, root, width, height, 1)
        gc = x11.XCreateGC(display, pixmap, 0, None)

        x11.XSetForeground(display, gc, 0)          # 0 = zone masquée
        x11.XFillRectangle(display, pixmap, gc, 0, 0, width, height)

        diameter = max(1, min(width, height) - margin * 2)
        x0 = (width - diameter) // 2
        y0 = (height - diameter) // 2
        x11.XSetForeground(display, gc, 1)           # 1 = zone visible
        x11.XFillArc(display, pixmap, gc, x0, y0, diameter, diameter, 0, 360 * 64)

        xext.XShapeCombineMask(display, tk_window_id, _SHAPE_BOUNDING, 0, 0, pixmap, _SHAPE_SET)
        xext.XShapeCombineMask(display, tk_window_id, _SHAPE_INPUT, 0, 0, pixmap, _SHAPE_SET)

        x11.XFreeGC(display, gc)
        x11.XFreePixmap(display, pixmap)
        x11.XSync(display, 0)
        x11.XCloseDisplay(display)
        return True
    except Exception as exc:  # ne jamais planter l'appli pour un effet visuel
        print(f"[horloge_studio] Fenêtre circulaire indisponible ({exc}) "
              f"— fenêtre carrée classique conservée.", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Palette exemple "Radio Mercure" (bleu / orange / blanc), fond noir façon horloge Orium
# ---------------------------------------------------------------------------
COLOR_BG = "#000000"
COLOR_RING_OFF = "#241a10"      # points de l'anneau (éteints)
COLOR_RING_ON = "#FF8A1E"       # points allumés
COLOR_RING_OUTER = "#1B3F8B"    # cercle extérieur
COLOR_DIGITS = "#FF8A1E"        # chiffres (orange, façon LED)
COLOR_DIGITS_DIM = "#3a2410"    # segments "éteints" (effet LED 7 segments)
COLOR_COLON = "#FF8A1E"
COLOR_DATE = "#8fa7d6"
COLOR_LOGO_BLUE = "#1B3F8B"
COLOR_LOGO_ORANGE = "#FF6A13"
COLOR_LOGO_TEXT = "#FFFFFF"

FONT_FAMILY_DIGITS = "DejaVu Sans Mono"
FONT_FAMILY_UI = "DejaVu Sans"

DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


class StudioClock(tk.Tk):
    def __init__(self, fullscreen=True, geometry="800x800",
                 twelve_hour=False, show_seconds=True, show_logo=True,
                 show_date=True, topmost=True, borderless=False, opacity=1.0,
                 shaped=False):
        super().__init__()
        self.title("Horloge de Studio by Samuel Vermeulen")
        self.configure(bg=COLOR_BG)
        self.twelve_hour = twelve_hour
        self.show_seconds = show_seconds
        self.show_logo = show_logo
        self.show_date = show_date
        self._shaped = shaped
        self._fullscreen = fullscreen and not shaped
        self._topmost = topmost
        self._borderless = borderless or shaped
        self._opacity = max(0.10, min(1.0, opacity))
        self._opaque_backup = self._opacity if self._opacity < 1.0 else 0.85

        # Le découpage circulaire réel n'est possible qu'avec un mécanisme
        # natif par plateforme : XShape sous Linux/X11, colorkey (-transparentcolor)
        # sous Windows. Ailleurs (macOS...), on retombe sur la fenêtre carrée.
        self._shape_mode = None
        if shaped:
            if IS_LINUX:
                self._shape_mode = "x11"
            elif IS_WINDOWS:
                self._shape_mode = "colorkey"
            else:
                print(f"[horloge_studio] Fenêtre circulaire non prise en charge sur "
                      f"cette plateforme ({sys.platform}) — fenêtre carrée conservée.",
                      file=sys.stderr)

        if self._fullscreen:
            self.attributes("-fullscreen", True)
        else:
            self.geometry(geometry)
            if self._borderless:
                self.overrideredirect(True)
        self.attributes("-topmost", self._topmost)
        self.attributes("-alpha", self._opacity)
        if self._shape_mode == "colorkey":
            self.attributes("-transparentcolor", TRANSPARENT_KEY)

        self.canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        if self._shape_mode == "colorkey":
            # Windows : tout pixel de cette couleur devient invisible ; on
            # peint le carré entier dans cette couleur puis un disque noir
            # opaque par-dessus (voir _redraw), sans aucun code bas niveau.
            self.canvas.configure(bg=TRANSPARENT_KEY)

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("q", lambda e: self.destroy())
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("f", self._toggle_fullscreen)
        self.bind("t", self._toggle_topmost)
        self.bind("+", self._increase_opacity)
        self.bind("<KP_Add>", self._increase_opacity)
        self.bind("-", self._decrease_opacity)
        self.bind("<KP_Subtract>", self._decrease_opacity)
        self.bind("o", self._toggle_opacity)

        if self._borderless:
            self.canvas.bind("<ButtonPress-1>", self._start_drag)
            self.canvas.bind("<B1-Motion>", self._do_drag)
            if self._shape_mode == "x11":
                self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        if self._borderless:
            # Une fenêtre sans bordure ne reçoit jamais le focus clavier
            # automatiquement, et certains gestionnaires de fenêtres le
            # reprennent peu après : on le réaffirme en continu (chaque
            # seconde, au moment du rafraîchissement de l'horloge) plutôt
            # qu'une seule fois au démarrage.
            self.focus_force()
            self.canvas.bind("<ButtonPress-1>", lambda e: self.focus_force(), add="+")
            # Filet de sécurité indépendant du clavier : une petite croix
            # discrète apparaît au survol du cercle pour quitter au clic.
            self._show_close = False
            self.canvas.bind("<Enter>", self._on_hover_enter)
            self.canvas.bind("<Leave>", self._on_hover_leave)
            self.canvas.tag_bind("close_btn", "<Button-1>", lambda e: self.destroy())
            self.canvas.tag_bind("close_btn", "<Enter>",
                                  lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind("close_btn", "<Leave>",
                                  lambda e: self.canvas.config(cursor=""))

        self._last_second = -1
        if self._shape_mode == "x11":
            self._shape_size = None
            self.bind("<Map>", self._apply_shape)
            self.bind("<Configure>", self._apply_shape)
            self.after(50, self._apply_shape)  # filet de sécurité si <Map> ne se déclenche pas
        self._tick()

    # -- fenêtre --------------------------------------------------------
    def _toggle_fullscreen(self, _event=None):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)
        self._redraw()

    def _toggle_topmost(self, _event=None):
        self._topmost = not self._topmost
        self.attributes("-topmost", self._topmost)

    def _set_opacity(self, value):
        self._opacity = max(0.10, min(1.0, value))
        self.attributes("-alpha", self._opacity)

    def _increase_opacity(self, _event=None):
        self._set_opacity(self._opacity + 0.05)

    def _decrease_opacity(self, _event=None):
        self._set_opacity(self._opacity - 0.05)

    def _toggle_opacity(self, _event=None):
        if self._opacity >= 0.99:
            self._set_opacity(self._opaque_backup)
        else:
            self._opaque_backup = self._opacity
            self._set_opacity(1.0)

    def _start_drag(self, event):
        self._drag_offset = (event.x, event.y)

    def _do_drag(self, event):
        x = self.winfo_pointerx() - self._drag_offset[0]
        y = self.winfo_pointery() - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _end_drag(self, _event=None):
        # Contourne un bug connu du compositeur xfwm4 : après un déplacement
        # en direct, une fenêtre découpée (XShape) peut laisser une image
        # figée de l'arrière-plan derrière elle. Un cycle rapide masquer /
        # réafficher force xfwm4 à recomposer entièrement l'écran et efface
        # la trace (léger clignotement, imperceptible en usage normal).
        self.withdraw()
        self.after(30, self._refresh_after_drag)

    def _refresh_after_drag(self):
        self.deiconify()
        self.attributes("-topmost", self._topmost)
        self._shape_size = None
        self._apply_shape()

    def _on_hover_enter(self, _event=None):
        self._show_close = True
        self._redraw()

    def _on_hover_leave(self, _event=None):
        self._show_close = False
        self.canvas.config(cursor="")
        self._redraw()

    def _apply_shape(self, _event=None):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            # la fenêtre n'a pas encore sa taille réelle à l'écran : réessaie
            self.after(50, self._apply_shape)
            return
        if (w, h) == self._shape_size:
            return  # déjà appliqué pour cette taille
        ok = apply_circular_window_shape(self.winfo_id(), w, h)
        if ok:
            self._shape_size = (w, h)
            print(f"[horloge_studio] Fenêtre découpée en cercle ({w}x{h}, "
                  f"xid={self.winfo_id()}).", file=sys.stderr)

    # -- boucle d'horloge -------------------------------------------------
    def _tick(self):
        now = datetime.now()
        if now.second != self._last_second:
            self._last_second = now.second
            self._redraw(now)
            if self._borderless:
                self.focus_force()
        # rafraîchissement rapide pour rester synchro sans charger le CPU
        self.after(150, self._tick)

    # -- dessin -----------------------------------------------------------
    def _redraw(self, now=None):
        now = now or datetime.now()
        c = self.canvas
        c.delete("all")

        w = c.winfo_width() or 800
        h = c.winfo_height() or 800
        cx, cy = w / 2, h / 2
        size = min(w, h)
        radius = size * 0.46

        if self._shape_mode == "colorkey":
            # Windows : le carré entier est en couleur-clé (invisible), seul
            # le disque noir dessiné par-dessus reste visible à l'écran.
            diameter = size - 4
            c.create_oval(cx - diameter / 2, cy - diameter / 2,
                          cx + diameter / 2, cy + diameter / 2,
                          fill=COLOR_BG, outline="")

        self._draw_ring(c, cx, cy, radius, now)
        self._draw_time(c, cx, cy, size, now)
        if self.show_date:
            self._draw_date(c, cx, cy, radius, now)
        if self.show_logo:
            self._draw_logo(c, cx, cy, radius, size)
        if getattr(self, "_show_close", False):
            self._draw_close_button(c, cx, cy, radius)

    def _draw_ring(self, c, cx, cy, radius, now):
        # cercle extérieur bleu, fin, façon boîtier
        c.create_oval(cx - radius - 6, cy - radius - 6,
                       cx + radius + 6, cy + radius + 6,
                       outline=COLOR_RING_OUTER, width=3)

        n_dots = 60
        dot_r = radius * 0.028
        seconds_frac = now.second + now.microsecond / 1_000_000
        lit_count = int(seconds_frac)  # points allumés en balayage (comme le modèle)

        for i in range(n_dots):
            angle = math.radians(i * 6 - 90)  # 0 en haut, sens horaire
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            lit = (i <= lit_count) if self.show_seconds else False
            color = COLOR_RING_ON if lit else COLOR_RING_OFF
            c.create_oval(x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                          fill=color, outline="")

    def _draw_time(self, c, cx, cy, size, now):
        hour = now.hour
        suffix = ""
        if self.twelve_hour:
            suffix = " AM" if hour < 12 else " PM"
            hour = hour % 12
            if hour == 0:
                hour = 12
        time_str = f"{hour:02d}:{now.minute:02d}"

        font_size = int(size * 0.20)
        c.create_text(cx, cy, text=time_str,
                      fill=COLOR_DIGITS,
                      font=(FONT_FAMILY_DIGITS, font_size, "bold"))

        if suffix:
            c.create_text(cx + size * 0.30, cy + size * 0.02, text=suffix.strip(),
                          fill=COLOR_DIGITS, font=(FONT_FAMILY_UI, int(font_size * 0.22), "bold"))

        if self.show_seconds:
            sec_str = f"{now.second:02d}"
            c.create_text(cx, cy + size * 0.185, text=sec_str,
                          fill=COLOR_DIGITS, font=(FONT_FAMILY_DIGITS, int(font_size * 0.32), "bold"))

    def _draw_date(self, c, cx, cy, radius, now):
        day_name = DAYS_FR[now.weekday()]
        date_str = f"{day_name} {now.day} {MONTHS_FR[now.month - 1]} {now.year}"
        c.create_text(cx, cy - radius * 0.55, text=date_str.upper(),
                      fill=COLOR_DATE, font=(FONT_FAMILY_UI, max(10, int(radius * 0.05)), "normal"))

    def _draw_logo(self, c, center_x, center_y, radius, size):
        # petit badge "lecture" façon logo Radio Mercure + texte, ancré près du bas
        # du cercle mais toujours à l'intérieur de celui-ci
        r = max(12, size * 0.024)
        badge_cx = center_x - r * 5.5
        badge_cy = center_y + radius * 0.74

        c.create_oval(badge_cx - r, badge_cy - r, badge_cx + r, badge_cy + r,
                      fill=COLOR_LOGO_BLUE, outline="")
        c.create_oval(badge_cx - r * 0.8, badge_cy - r * 0.8, badge_cx + r * 0.8, badge_cy + r * 0.8,
                      fill=COLOR_LOGO_ORANGE, outline="")
        tri = [
            badge_cx - r * 0.32, badge_cy - r * 0.45,
            badge_cx - r * 0.32, badge_cy + r * 0.45,
            badge_cx + r * 0.5, badge_cy,
        ]
        c.create_polygon(tri, fill="white", outline="")

        c.create_text(badge_cx + r * 1.6, badge_cy, text="",
                      fill=COLOR_LOGO_TEXT, anchor="w",
                      font=(FONT_FAMILY_UI, max(10, int(size * 0.019)), "bold"))

    def _draw_close_button(self, c, cx, cy, radius):
        # petite croix discrète en haut à droite du cercle, visible
        # seulement au survol (mode --borderless) — quitte l'appli au clic
        r = max(11, radius * 0.075)
        bx = cx + radius * 0.62
        by = cy - radius * 0.62
        c.create_oval(bx - r, by - r, bx + r, by + r,
                      fill="#1a1a1a", outline="#555555", width=1, tags="close_btn")
        d = r * 0.42
        c.create_line(bx - d, by - d, bx + d, by + d,
                      fill="#e0e0e0", width=2, tags="close_btn")
        c.create_line(bx - d, by + d, bx + d, by - d,
                      fill="#e0e0e0", width=2, tags="close_btn")


def parse_args():
    p = argparse.ArgumentParser(description="Horloge de studio")
    p.add_argument("--window", action="store_true", help="Lancer en mode fenêtré (par défaut : plein écran)")
    p.add_argument("--size", default="800x800", help="Taille de la fenêtre en mode fenêtré, ex: 900x900")
    p.add_argument("--12h", dest="twelve_hour", action="store_true", help="Affichage 12h avec AM/PM")
    p.add_argument("--no-seconds", dest="show_seconds", action="store_false", help="Masquer les secondes et l'anneau animé")
    p.add_argument("--no-logo", dest="show_logo", action="store_false", help="Masquer le bandeau logo")
    p.add_argument("--no-date", dest="show_date", action="store_false", help="Masquer la date")
    p.add_argument("--no-topmost", dest="topmost", action="store_false", help="Ne pas épingler la fenêtre au premier plan")
    p.add_argument("--borderless", action="store_true", help="Mode fenêtré sans bordures ni barre de titre (glisser pour déplacer)")
    p.add_argument("--opacity", type=float, default=1.0, help="Opacité de la fenêtre, de 0.1 (très transparent) à 1.0 (opaque). Défaut : 1.0")
    p.add_argument("--shaped", action="store_true", help="Découpe la fenêtre en cercle : plus de carré noir, vrai fond transparent (Linux/X11). Implique --window --borderless")
    p.add_argument("--shape-selftest", action="store_true", help="Teste juste le chargement des bibliothèques X11 nécessaires à --shaped, puis quitte (sans ouvrir de fenêtre)")
    p.set_defaults(show_seconds=True, show_logo=True, show_date=True, topmost=True)
    return p.parse_args()


def main():
    args = parse_args()

    if args.shape_selftest:
        try:
            _load_x11_shape_libs()
            print("OK : libX11 et libXext chargées avec succès — --shaped devrait fonctionner.")
        except _X11ShapeUnavailable as exc:
            print(f"ÉCHEC : {exc}")
            print("Vérifiez leur présence avec : ldconfig -p | grep -E 'libX11|libXext'")
        return

    app = StudioClock(
        fullscreen=not args.window,
        geometry=args.size,
        twelve_hour=args.twelve_hour,
        show_seconds=args.show_seconds,
        show_logo=args.show_logo,
        show_date=args.show_date,
        topmost=args.topmost,
        borderless=args.borderless,
        opacity=args.opacity,
        shaped=args.shaped,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
