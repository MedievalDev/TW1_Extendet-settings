"""tw1_Extendet-settings - Schadensarten von Two Worlds 1 einstellen.

Schreibt tw1_Extendet-settings.ini in den Spielordner; das TWSE-Plugin
TWExtended.dll liest die Datei beim Start und bei jeder Aenderung im
laufenden Spiel. Design nach PY_TOOL_DESIGN.md (Dark Theme, theme.py).
Deutsche Texte sind die Quelle (tr), englische Tabelle am Dateiende.
"""
import ctypes
import datetime
import json
import os
import shutil
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import theme
from theme import (BG, PANEL, FIELD, CANVAS_BG, LINE, SEL, INK, MUT, DIM,
                   GOLD, GOLD_HI, OK, ERR, FONT, FONT_BOLD, FONT_SMALL,
                   FONT_MONO, FONT_H2)

VERSION = '1.0'
TOOL_NAME = 'tw1_Extendet-settings'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_Extendet-settings'
SITE_URL = 'https://alchemy-fox.de/'
GUIDE_URL = 'https://alchemy-fox.de/game/TW1_Extendet-settings/'
COMMUNITY_URL = 'https://twmp.alchemy-fox.de/'
TWSE_URL = 'https://github.com/buglord/Two-Worlds-1-Script-Extender'

INI_NAME = 'tw1_Extendet-settings.ini'
PLUGIN_DLL = 'TWExtended.dll'
LOG_NAME = 'TWExtended.log'
STATUS_NAME = 'TWExtended.status'
TWSE_EXE = 'TwoWorldsExtended.exe'
TWSE_DLL = 'twse.dll'

FROZEN = bool(getattr(sys, 'frozen', False))
HERE = os.path.dirname(os.path.abspath(sys.argv[0] if FROZEN else __file__))
RES = getattr(sys, '_MEIPASS', HERE)
DATEN = (os.path.join(os.environ.get('LOCALAPPDATA', HERE), 'TW1ExtendedSettings')
         if FROZEN else HERE)
KONFIG_DATEI = os.path.join(DATEN, 'tw1_extended_settings.json')
ICON = os.path.join(RES, 'tw1_extended.ico')

# Originalwerte des Spiels (TwoWorlds.exe 1.7), siehe tw_extended.c
STANDARD = {
    'fall_enabled': 1, 'fall_percent': 100, 'fall_min': 8.0, 'fall_death': 25.0,
    'fall_lethal': 1,
    'slide_enabled': 1, 'slide_percent': 10, 'slide_grace': 30,
    'lava_enabled': 1, 'lava_percent': 5, 'lava_every': 1,
    'horse_immortal': 0, 'whistle_set': 0, 'whistle_m': 40,
    'log_damage': 0,
}
WHISTLE_ORIGINAL_M = 40
WHISTLE_FILE_OFFSET = 0x280C8B   # Immediate von "cmp eax, 0xA00" in TwoWorlds(Extended).exe 1.7, 64 je Meter

INI_KEYS = (  # (Sektion, Schluessel, unser Name, Typ)
    ('FallDamage', 'Enabled', 'fall_enabled', int),
    ('FallDamage', 'Percent', 'fall_percent', int),
    ('FallDamage', 'MinHeight', 'fall_min', float),
    ('FallDamage', 'DeathHeight', 'fall_death', float),
    ('FallDamage', 'Lethal', 'fall_lethal', int),
    ('SlideDamage', 'Enabled', 'slide_enabled', int),
    ('SlideDamage', 'Percent', 'slide_percent', int),
    ('SlideDamage', 'GraceTicks', 'slide_grace', int),
    ('LavaDamage', 'Enabled', 'lava_enabled', int),
    ('LavaDamage', 'Percent', 'lava_percent', int),
    ('LavaDamage', 'EveryFrames', 'lava_every', int),
    ('Horse', 'Immortal', 'horse_immortal', int),
    ('Horse', 'WhistleRangeMeters', 'whistle_ini', int),
    ('Diagnose', 'LogDamage', 'log_damage', int),
)


# --------------------------------------------------------------------------
# Sprache
# --------------------------------------------------------------------------

def systemsprache():
    try:
        lang = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return 'de' if lang == 0x07 else 'en'
    except Exception:
        return 'en'


SPRACHE = 'en'


def tr(text):
    if SPRACHE == 'de':
        return text
    return TEXTE_EN.get(text, text)


# --------------------------------------------------------------------------
# Konfig des Tools und Spielordner
# --------------------------------------------------------------------------

class Konfig(dict):
    def __init__(self):
        super().__init__()
        try:
            with open(KONFIG_DATEI, encoding='utf-8') as f:
                self.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(DATEN, exist_ok=True)
            with open(KONFIG_DATEI, 'w', encoding='utf-8') as f:
                json.dump(self, f, indent=2)
        except Exception:
            pass


def spielpfad_registry():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\WOW6432Node\Reality Pump\TwoWorlds\FileSystem') as k:
            return winreg.QueryValueEx(k, 'DataPath')[0]
    except Exception:
        return ''


def ini_lesen(pfad):
    """Sehr kleiner INI-Leser, gleiche Regeln wie das Plugin."""
    werte = dict(STANDARD)
    try:
        with open(pfad, encoding='utf-8', errors='replace') as f:
            zeilen = f.read().splitlines()
    except OSError:
        return werte, False
    sekt = ''
    for z in zeilen:
        z = z.split(';')[0].split('#')[0].strip()
        if not z:
            continue
        if z.startswith('['):
            sekt = z.strip('[]').strip().lower()
            continue
        if '=' not in z:
            continue
        k, v = (t.strip() for t in z.split('=', 1))
        for s, key, name, typ in INI_KEYS:
            if s.lower() == sekt and key.lower() == k.lower():
                try:
                    werte[name] = typ(float(v)) if typ is int else typ(v)
                except ValueError:
                    pass
    m = werte.pop('whistle_ini', 0)
    if m > 0:
        werte['whistle_set'], werte['whistle_m'] = 1, m
    else:
        werte['whistle_set'] = 0
    return werte, True


def ini_schreiben(pfad, w):
    text = (
        f'; {TOOL_NAME} - written by the tool, read by TWExtended.dll (Two Worlds 1.7)\n'
        '; Changes are picked up by the running game within a second.\n'
        '\n[FallDamage]\n'
        f'Enabled={int(w["fall_enabled"])}        ; 0 = no fall damage, no fall death, no stun\n'
        f'Percent={int(w["fall_percent"])}      ; damage scale, 100 = original, 0 = no damage\n'
        f'MinHeight={w["fall_min"]:.1f}    ; damage starts above this height (original 8.0)\n'
        f'DeathHeight={w["fall_death"]:.1f} ; instant death above this height (original 25.0), 0 = never\n'
        f'Lethal={int(w["fall_lethal"])}         ; 1 = original: instant death when the damage would kill you\n'
        '\n[SlideDamage]\n'
        f'Enabled={int(w["slide_enabled"])}        ; damage while sliding down steep slopes\n'
        f'Percent={int(w["slide_percent"])}       ; percent of max HP per damage tick (original 10)\n'
        f'GraceTicks={int(w["slide_grace"])}    ; ticks of sliding before damage starts (original 30)\n'
        '\n[LavaDamage]\n'
        f'Enabled={int(w["lava_enabled"])}        ; damage while swimming in lava\n'
        f'Percent={int(w["lava_percent"])}        ; percent of max HP per damage tick (original 5)\n'
        f'EveryFrames={int(w["lava_every"])}    ; a damage tick every n frames (original 1 = every frame)\n'
        '\n[Horse]\n'
        f'Immortal={int(w["horse_immortal"])}       ; 1 = the hero\'s horse takes no damage\n'
        f'WhistleRangeMeters={int(w["whistle_m"]) if w["whistle_set"] else 0} ; distance the horse answers the whistle from (original 40), 0 = leave the exe as it is\n'
        '\n[Diagnose]\n'
        f'LogDamage={int(w["log_damage"])}      ; 1 = log every HP loss of the hero to TWExtended.log\n')
    tmp = pfad + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, pfad)


def exe_pfeifreichweite(spiel):
    """Pfeifreichweite in Metern aus der Exe auf der Platte, 0 wenn unlesbar."""
    for name in (TWSE_EXE, 'TwoWorlds.exe'):
        try:
            with open(os.path.join(spiel, name), 'rb') as f:
                f.seek(WHISTLE_FILE_OFFSET - 1)
                b = f.read(5)
            if len(b) == 5 and b[0] == 0x3D:
                return int.from_bytes(b[1:], 'little') // 64
        except OSError:
            pass
    return 0


def prozess_laeuft(namen):
    """True, wenn ein Prozess mit einem der Namen laeuft (Toolhelp, ohne Konsole)."""
    try:
        TH32CS_SNAPPROCESS = 0x2

        class PE32(ctypes.Structure):
            _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong),
                        ('th32ProcessID', ctypes.c_ulong),
                        ('th32DefaultHeapID', ctypes.c_void_p),
                        ('th32ModuleID', ctypes.c_ulong), ('cntThreads', ctypes.c_ulong),
                        ('th32ParentProcessID', ctypes.c_ulong),
                        ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                        ('szExeFile', ctypes.c_char * 260)]
        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return False
        pe = PE32()
        pe.dwSize = ctypes.sizeof(PE32)
        gefunden = False
        ok = k32.Process32First(snap, ctypes.byref(pe))
        wollen = {n.lower() for n in namen}
        while ok:
            if pe.szExeFile.decode(errors='replace').lower() in wollen:
                gefunden = True
                break
            ok = k32.Process32Next(snap, ctypes.byref(pe))
        k32.CloseHandle(snap)
        return gefunden
    except Exception:
        return False


# --------------------------------------------------------------------------
# Hauptfenster
# --------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, konfig):
        super().__init__()
        self.withdraw()
        self.konfig = konfig
        self.restart = False
        self.lang = SPRACHE
        self.spiel = konfig.get('game_dir') or spielpfad_registry()
        self.werte = dict(STANDARD)
        self.vars = {}
        self._speicher_job = None
        self._laden_aktiv = False
        self.guide = None
        theme.apply_dark_theme(self)
        self.title(f'{TOOL_NAME} {VERSION}')
        try:
            self.iconbitmap(ICON)
        except Exception:
            pass
        self.minsize(820, 560)
        self.geometry('980x900')
        self.protocol('WM_DELETE_WINDOW', self.beenden)
        self.bind('<Control-s>', lambda e: self.anwenden())
        self.bind('<F1>', lambda e: self.guide_starten())
        self.bau_menueleiste()
        self.bau_statusleiste()
        self.bau_inhalt()
        self.laden()
        self.aktualisiere_status()
        self.update_idletasks()
        self.deiconify()
        theme.dark_titlebar(self)
        self._tick_job = self.after(1500, self._tick)
        if not konfig.get('guide_seen'):
            self.after(400, self.guide_starten)

    # ---------------------------------------------------------- Menueleiste
    def bau_menueleiste(self):
        bar = ttk.Frame(self, style='Menubar.TFrame')
        bar.pack(fill='x')
        self.menubar = bar
        for key, filler in ((tr('Datei'), self._fill_datei),
                            (tr('Ansicht'), self._fill_ansicht),
                            (tr('Hilfe'), self._fill_hilfe)):
            item = ttk.Label(bar, text=key, style='Menubar.TLabel')
            item.pack(side='left')
            item.bind('<Button-1>', lambda ev, f=filler, w=item: self._popup(f, w))
            item.bind('<Enter>', lambda ev, w=item: w.state(['active']))
            item.bind('<Leave>', lambda ev, w=item: w.state(['!active']))
        ttk.Label(bar, text=TOOL_NAME.upper(), style='Menubar.TLabel').pack(side='right', padx=(0, 6))
        self.bau_sprachumschalter(bar).pack(side='right')

    def bau_sprachumschalter(self, bar):
        box = ttk.Frame(bar, style='Menubar.TFrame')
        self.lang_labels = {}
        for i, code in enumerate(('de', 'en')):
            if i:
                ttk.Label(box, text='·', style='Menubar.TLabel', padding=(2, 5)).pack(side='left')
            lbl = ttk.Label(box, text=code.upper(), style='Menubar.TLabel',
                            padding=(4, 5), cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda ev, c=code: self.sprache_setzen(c))
            self.lang_labels[code] = lbl
        for code, lbl in self.lang_labels.items():
            lbl.configure(foreground=GOLD if code == self.lang else MUT)
        return box

    def sprache_setzen(self, code):
        if code == self.lang:
            return
        self.konfig['lang'] = code
        self.konfig.save()
        self.restart = True
        self.destroy()

    def _popup(self, filler, widget):
        menu = theme.Menu(self)
        filler(menu)
        try:
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _fill_datei(self, m):
        m.add_command(label=tr('Anwenden'), accelerator='Strg+S', command=self.anwenden)
        m.add_command(label=tr('Originalwerte'), command=self.originalwerte)
        m.add_separator()
        m.add_command(label=tr('Spielordner wählen ...'), command=self.spielordner_waehlen)
        m.add_command(label=tr('Spielordner öffnen'), command=self.spielordner_oeffnen)
        m.add_command(label=tr('Plugin installieren'), command=self.plugin_installieren)
        m.add_separator()
        m.add_command(label=tr('Beenden'), command=self.beenden)

    def _fill_ansicht(self, m):
        sub = theme.Menu(m)
        sub.add_radiobutton(label='Deutsch', command=lambda: self.sprache_setzen('de'),
                            value='de', variable=tk.StringVar(value=self.lang))
        sub.add_radiobutton(label='English', command=lambda: self.sprache_setzen('en'),
                            value='en', variable=tk.StringVar(value=self.lang))
        m.add_cascade(label=tr('Sprache'), menu=sub)

    def _fill_hilfe(self, m):
        m.add_command(label=tr('Guide starten'), accelerator='F1', command=self.guide_starten)
        m.add_command(label=tr('Kurzanleitung'), command=self.kurzanleitung)
        m.add_separator()
        for name, url in self.links():
            m.add_command(label=f'{name}  ({url})', command=lambda u=url: webbrowser.open(u))
        m.add_separator()
        m.add_command(label=tr('Über'), command=self.ueber)

    def links(self):
        return ((tr('GitHub-Repo'), GITHUB_URL), ('Alchemy Fox', SITE_URL),
                (tr('Guide-Seite'), GUIDE_URL), (tr('Community'), COMMUNITY_URL),
                ('TWSE (buglord)', TWSE_URL))

    # ---------------------------------------------------------- Statusleiste
    def bau_statusleiste(self):
        leiste = ttk.Frame(self, style='Status.TFrame')
        leiste.pack(side='bottom', fill='x')
        self.status_label = ttk.Label(leiste, text='', style='Status.TLabel')
        self.status_label.pack(side='left')
        self.status_rechts = ttk.Label(leiste, text='', style='Status.TLabel')
        self.status_rechts.pack(side='right')

    def melden(self, text, art='info'):
        stil = {'ok': 'StatusOk.TLabel', 'err': 'StatusErr.TLabel'}.get(art, 'Status.TLabel')
        self.status_label.configure(text=text, style=stil)

    # ---------------------------------------------------------- Inhalt
    def bau_inhalt(self):
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True)
        rolle = tk.Canvas(body, background=BG, highlightthickness=0, borderwidth=0)
        rolle_sb = ttk.Scrollbar(body, orient='vertical', command=rolle.yview)
        rolle.configure(yscrollcommand=rolle_sb.set)
        links = ttk.Frame(rolle)
        self._links_id = rolle.create_window((0, 0), window=links, anchor='nw')
        links.bind('<Configure>', lambda e: rolle.configure(scrollregion=rolle.bbox('all')))
        rolle.bind('<Configure>', lambda e: rolle.itemconfigure(self._links_id, width=e.width))
        self.bind_all('<MouseWheel>', lambda e: self._rollen(rolle, e))
        self.rolle = rolle
        rechts = ttk.Frame(body, style='Panel.TFrame', width=330)
        rechts.pack(side='right', fill='y', padx=(6, 12), pady=(10, 8))
        rechts.pack_propagate(False)
        rolle_sb.pack(side='right', fill='y', pady=(10, 8))
        rolle.pack(side='left', fill='both', expand=True, padx=(12, 4), pady=(10, 8))

        # --- Fallschaden
        self.box_fall = ttk.LabelFrame(links, text=tr('Fallschaden'), padding=(10, 6))
        self.box_fall.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_fall, 'fall_enabled', tr('Fallschaden an'),
                      tr('Aus: kein Schaden, kein Sturztod, keine Benommenheit nach der Landung.'))
        self.regler(self.box_fall, 'fall_percent', tr('Schaden in Prozent des Originals'), 0, 300, 1,
                    tr('100 = wie im Spiel, 50 = halber Schaden, 0 = keiner. Das Spiel rechnet in Prozent der maximalen Lebenspunkte, deshalb wirkt es auf jeder Stufe gleich.'))
        self.zahl(self.box_fall, 'fall_min', tr('Schaden ab Fallhöhe'), 0.0, 100.0, 0.5,
                  tr('Original 8.0. Darunter passiert nichts.'))
        self.zahl(self.box_fall, 'fall_death', tr('Sofort tot ab Fallhöhe'), 0.0, 500.0, 0.5,
                  tr('Original 25.0. 0 = nie durch die Höhe allein sterben.'))
        self.schalter(self.box_fall, 'fall_lethal', tr('Sofort tot, wenn der Schaden zum Töten reicht'),
                      tr('Original an. Aus: der Schaden wird normal abgezogen, das Spiel entscheidet über die Lebenspunkte.'))

        # --- Rutschschaden
        self.box_slide = ttk.LabelFrame(links, text=tr('Rutschschaden (steile Hänge)'), padding=(10, 6))
        self.box_slide.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_slide, 'slide_enabled', tr('Rutschschaden an'),
                      tr('Schaden, wenn der Held einen zu steilen Hang hinunterrutscht.'))
        self.regler(self.box_slide, 'slide_percent', tr('Prozent der Lebenspunkte je Schadenstick'), 0, 100, 1,
                    tr('Original 10. Ein Tick alle fünf Spielschritte, solange gerutscht wird.'))
        self.regler(self.box_slide, 'slide_grace', tr('Ticks Rutschen bis zum ersten Schaden'), 0, 127, 1,
                    tr('Original 30. Höher = länger schadlos rutschen.'))

        # --- Pferd
        self.box_horse = ttk.LabelFrame(links, text=tr('Pferd'), padding=(10, 6))
        self.box_horse.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_horse, 'horse_immortal', tr('Pferd unsterblich'),
                      tr('Das zuletzt gerittene Pferd nimmt keinen Schaden mehr; seine Lebenspunkte bleiben voll.'))
        self.schalter(self.box_horse, 'whistle_set', tr('Pfeifreichweite setzen'),
                      tr('Aus = die Exe bleibt, wie sie ist (Original 40 m, oder ein bereits gepatchter Wert).'))
        self.regler(self.box_horse, 'whistle_m', tr('Pfeifreichweite in Metern'), 5, 1000, 5,
                    tr('Original 40 m. Gerufen wird nur das zuletzt gerittene Pferd, und nur, wenn es noch geladen ist und einen Weg findet.'))
        self.whistle_hinweis = ttk.Label(self.box_horse, text='', style='Muted.TLabel')
        self.whistle_hinweis.pack(anchor='w', pady=(0, 2))

        # --- Lava
        self.box_lava = ttk.LabelFrame(links, text=tr('Lavaschaden'), padding=(10, 6))
        self.box_lava.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_lava, 'lava_enabled', tr('Lavaschaden an'),
                      tr('Lava verhält sich wie Wasser, zieht aber Lebenspunkte ab, solange der Held drin schwimmt.'))
        self.regler(self.box_lava, 'lava_percent', tr('Prozent der Lebenspunkte je Schadenstick'), 0, 100, 1,
                    tr('Original 5. Auch hier rechnet das Spiel in Prozent der maximalen Lebenspunkte.'))
        self.regler(self.box_lava, 'lava_every', tr('Ein Schadenstick alle n Bilder'), 1, 60, 1,
                    tr('Original 1 = jedes Bild, also bei 5 % nach 20 Bildern tot. 10 = nur jedes zehnte Bild.'))

        # --- Diagnose
        self.box_diag = ttk.LabelFrame(links, text=tr('Diagnose'), padding=(10, 6))
        self.box_diag.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_diag, 'log_damage', tr('Jeden Lebenspunkt-Verlust des Helden protokollieren'),
                      tr('Schreibt Schaden, Lebenspunkte und Aufrufer nach TWExtended.log.'))

        # --- rechts: Status, Knoepfe, Log (von unten gepackt)
        ttk.Label(rechts, text=tr('Status'), style='PanelTitle.TLabel').pack(fill='x')
        self.status_zeilen = {}
        for key in ('spiel', 'twse', 'plugin', 'aktiv', 'laeuft', 'ini'):
            row = ttk.Frame(rechts, style='Panel.TFrame')
            row.pack(fill='x', padx=8)
            lbl = ttk.Label(row, text='', style='Panel.TLabel', wraplength=300, justify='left')
            lbl.pack(anchor='w')
            self.status_zeilen[key] = lbl

        knoepfe = ttk.Frame(rechts, style='Panel.TFrame')
        knoepfe.pack(side='bottom', fill='x', padx=8, pady=(6, 8))
        self.btn_anwenden = ttk.Button(knoepfe, text=tr('Anwenden'), style='Accent.TButton', command=self.anwenden)
        self.btn_anwenden.pack(fill='x', pady=(0, 4))
        self.btn_original = ttk.Button(knoepfe, text=tr('Originalwerte'), command=self.originalwerte)
        self.btn_original.pack(fill='x', pady=(0, 4))
        self.btn_plugin = ttk.Button(knoepfe, text=tr('Plugin installieren'), command=self.plugin_installieren)
        self.btn_plugin.pack(fill='x', pady=(0, 4))
        ttk.Button(knoepfe, text=tr('Log leeren'), command=self.log_leeren).pack(fill='x')

        ttk.Label(rechts, text=tr('Plugin-Log'), style='PanelTitle.TLabel').pack(fill='x', pady=(8, 0))
        logbox = ttk.Frame(rechts, style='Panel.TFrame')
        logbox.pack(fill='both', expand=True, padx=8)
        self.log = tk.Text(logbox, wrap='none', font=FONT_MONO, state='disabled', height=8)
        sb = ttk.Scrollbar(logbox, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        self.log.tag_configure('err', foreground=ERR)
        self.log.tag_configure('gold', foreground=GOLD)
        self.log.tag_configure('mut', foreground=MUT)

    def _rollen(self, rolle, ev):
        w = self.winfo_containing(ev.x_root, ev.y_root)
        while w is not None:
            if w is rolle:
                rolle.yview_scroll(-1 if ev.delta > 0 else 1, 'units')
                return
            w = getattr(w, 'master', None)

    # Bausteine ------------------------------------------------------------
    def _var(self, name, typ):
        v = (tk.IntVar if typ is int else tk.DoubleVar)(value=STANDARD[name])
        v.trace_add('write', lambda *a, n=name: self._geaendert(n))
        self.vars[name] = v
        return v

    def schalter(self, parent, name, text, hinweis):
        v = self._var(name, int)
        ttk.Checkbutton(parent, text=text, variable=v).pack(anchor='w')
        ttk.Label(parent, text=hinweis, style='Muted.TLabel', wraplength=520, justify='left').pack(anchor='w', padx=(22, 0), pady=(0, 4))

    def regler(self, parent, name, text, lo, hi, step, hinweis):
        v = self._var(name, int)
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(4, 0))
        ttk.Label(row, text=text).pack(side='left')
        sp = ttk.Spinbox(row, from_=lo, to=hi, increment=step, width=6, textvariable=v)
        sp.pack(side='right')
        scale = tk.Scale(parent, from_=lo, to=hi, orient='horizontal', showvalue=0,
                         resolution=step, background=BG, troughcolor=FIELD,
                         activebackground=GOLD_HI, highlightthickness=0, borderwidth=0,
                         sliderrelief='flat', sliderlength=22, width=12,
                         command=lambda val, n=name: self._von_regler(n, val))
        scale.configure(background=GOLD)
        scale.pack(fill='x', pady=(4, 0))
        scale.set(STANDARD[name])
        setattr(self, f'scale_{name}', scale)
        ttk.Label(parent, text=hinweis, style='Muted.TLabel', wraplength=520, justify='left').pack(anchor='w', pady=(0, 4))

    def zahl(self, parent, name, text, lo, hi, step, hinweis):
        v = self._var(name, float)
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(4, 0))
        ttk.Label(row, text=text).pack(side='left')
        ttk.Spinbox(row, from_=lo, to=hi, increment=step, width=8, textvariable=v, format='%.1f').pack(side='right')
        ttk.Label(parent, text=hinweis, style='Muted.TLabel', wraplength=520, justify='left').pack(anchor='w', pady=(0, 4))

    def _von_regler(self, name, val):
        neu = int(round(float(val)))
        if self.vars[name].get() != neu:
            self.vars[name].set(neu)

    def _geaendert(self, name):
        if self._laden_aktiv:
            return
        try:
            wert = self.vars[name].get()
        except (tk.TclError, ValueError):
            return
        scale = getattr(self, f'scale_{name}', None)
        if scale is not None and int(round(scale.get())) != wert:
            scale.set(wert)
        self.melden(tr('Geändert, wird gleich angewendet ...'))
        if self._speicher_job:
            self.after_cancel(self._speicher_job)
        self._speicher_job = self.after(700, self.anwenden)

    # ---------------------------------------------------------- Laden / Speichern
    def ini_pfad(self):
        return os.path.join(self.spiel, INI_NAME) if self.spiel else ''

    def laden(self):
        self._laden_aktiv = True
        try:
            werte, da = ini_lesen(self.ini_pfad()) if self.spiel else (dict(STANDARD), False)
            self.werte = werte
            for name, v in self.vars.items():
                v.set(werte[name])
                scale = getattr(self, f'scale_{name}', None)
                if scale is not None:
                    scale.set(werte[name])
        finally:
            self._laden_aktiv = False
        if da:
            self.melden(tr('Einstellungen aus dem Spielordner geladen.'), 'ok')
        elif self.spiel:
            self.melden(tr('Noch keine Einstellungsdatei, Originalwerte angezeigt.'))
        else:
            self.melden(tr('Spielordner nicht gefunden. Datei > Spielordner wählen.'), 'err')

    def werte_aus_feldern(self):
        w = {}
        for name, v in self.vars.items():
            try:
                w[name] = v.get()
            except (tk.TclError, ValueError):
                w[name] = self.werte.get(name, STANDARD[name])
        w['fall_percent'] = max(0, min(1000, int(w['fall_percent'])))
        w['slide_percent'] = max(0, min(100, int(w['slide_percent'])))
        w['slide_grace'] = max(0, min(127, int(w['slide_grace'])))
        w['lava_percent'] = max(0, min(100, int(w['lava_percent'])))
        w['lava_every'] = max(1, min(600, int(w['lava_every'])))
        w['fall_min'] = max(0.0, float(w['fall_min']))
        w['fall_death'] = max(0.0, float(w['fall_death']))
        return w

    def anwenden(self):
        self._speicher_job = None
        if not self.spiel:
            self.melden(tr('Spielordner nicht gefunden. Datei > Spielordner wählen.'), 'err')
            return False
        w = self.werte_aus_feldern()
        try:
            ini_schreiben(self.ini_pfad(), w)
        except OSError as e:
            self.melden(tr('Schreiben fehlgeschlagen: {fehler}').format(fehler=e), 'err')
            return False
        self.werte = w
        jetzt = datetime.datetime.now().strftime('%H:%M:%S')
        if prozess_laeuft((TWSE_EXE, 'TwoWorlds.exe')):
            self.melden(tr('Angewendet {zeit}. Das laufende Spiel übernimmt die Werte innerhalb einer Sekunde.').format(zeit=jetzt), 'ok')
        else:
            self.melden(tr('Gespeichert {zeit}. Wirkt beim nächsten Start über TwoWorldsExtended.exe.').format(zeit=jetzt), 'ok')
        return True

    def originalwerte(self):
        self._laden_aktiv = True
        try:
            for name, v in self.vars.items():
                v.set(STANDARD[name])
                scale = getattr(self, f'scale_{name}', None)
                if scale is not None:
                    scale.set(STANDARD[name])
        finally:
            self._laden_aktiv = False
        self.anwenden()

    # ---------------------------------------------------------- Spielordner / Plugin
    def spielordner_waehlen(self):
        pfad = filedialog.askdirectory(title=tr('Spielordner von Two Worlds wählen'), initialdir=self.spiel or None)
        if not pfad:
            return
        pfad = os.path.normpath(pfad)
        if not os.path.exists(os.path.join(pfad, 'TwoWorlds.exe')):
            messagebox.showerror(TOOL_NAME, tr('In diesem Ordner liegt keine TwoWorlds.exe.'))
            return
        self.spiel = pfad
        self.konfig['game_dir'] = pfad
        self.konfig.save()
        self.laden()
        self.aktualisiere_status()

    def spielordner_oeffnen(self):
        if self.spiel and os.path.isdir(self.spiel):
            os.startfile(self.spiel)

    def plugin_quelle(self):
        for kandidat in (os.path.join(RES, PLUGIN_DLL),
                         os.path.join(HERE, 'bin', 'TWSEPlugins', PLUGIN_DLL)):
            if os.path.exists(kandidat):
                return kandidat
        return ''

    def plugin_installieren(self):
        if not self.spiel:
            self.melden(tr('Spielordner nicht gefunden. Datei > Spielordner wählen.'), 'err')
            return
        quelle = self.plugin_quelle()
        if not quelle:
            messagebox.showerror(TOOL_NAME, tr('TWExtended.dll liegt nicht neben dem Tool.'))
            return
        if prozess_laeuft((TWSE_EXE, 'TwoWorlds.exe')):
            messagebox.showwarning(TOOL_NAME, tr('Bitte das Spiel beenden, dann das Plugin installieren.'))
            return
        ziel_ordner = os.path.join(self.spiel, 'TWSEPlugins')
        try:
            os.makedirs(ziel_ordner, exist_ok=True)
            shutil.copy2(quelle, os.path.join(ziel_ordner, PLUGIN_DLL))
        except OSError as e:
            messagebox.showerror(TOOL_NAME, tr('Kopieren fehlgeschlagen: {fehler}').format(fehler=e))
            return
        fehlt = [n for n in (TWSE_EXE, TWSE_DLL) if not os.path.exists(os.path.join(self.spiel, n))]
        if fehlt:
            messagebox.showinfo(TOOL_NAME, tr('Plugin kopiert. Es fehlt aber noch TWSE ({dateien}): einmal den TWSE-Patcher von buglord auf TwoWorlds.exe anwenden, danach immer über TwoWorldsExtended.exe starten.').format(dateien=', '.join(fehlt)))
        else:
            self.melden(tr('Plugin installiert. Spiel über TwoWorldsExtended.exe starten.'), 'ok')
        self.aktualisiere_status()

    # ---------------------------------------------------------- Status / Log
    def aktualisiere_status(self):
        z = self.status_zeilen
        if not self.spiel:
            z['spiel'].configure(text=tr('Spielordner: nicht gefunden'), foreground=ERR)
            for k in ('twse', 'plugin', 'aktiv', 'laeuft', 'ini'):
                z[k].configure(text='', foreground=MUT)
            return
        z['spiel'].configure(text=tr('Spielordner: {pfad}').format(pfad=self.spiel), foreground=INK)
        twse = all(os.path.exists(os.path.join(self.spiel, n)) for n in (TWSE_EXE, TWSE_DLL))
        z['twse'].configure(text=tr('TWSE (TwoWorldsExtended.exe): {zustand}').format(
            zustand=tr('vorhanden') if twse else tr('fehlt')), foreground=OK if twse else ERR)
        plugin = os.path.exists(os.path.join(self.spiel, 'TWSEPlugins', PLUGIN_DLL))
        z['plugin'].configure(text=tr('Plugin TWExtended.dll: {zustand}').format(
            zustand=tr('installiert') if plugin else tr('nicht installiert')), foreground=OK if plugin else ERR)
        self.btn_plugin.configure(text=tr('Plugin aktualisieren') if plugin else tr('Plugin installieren'))
        status = self.status_lesen()
        if status:
            z['aktiv'].configure(text=tr('Plugin zuletzt aktiv: {zeit}').format(zeit=status.get('time', '?')), foreground=INK)
        else:
            z['aktiv'].configure(text=tr('Plugin zuletzt aktiv: noch nie (Spiel noch nicht über TWSE gestartet)'), foreground=MUT)
        laeuft = prozess_laeuft((TWSE_EXE, 'TwoWorlds.exe'))
        z['laeuft'].configure(text=tr('Spiel läuft: {zustand}').format(zustand=tr('ja') if laeuft else tr('nein')),
                              foreground=OK if laeuft else MUT)
        z['ini'].configure(text=tr('Datei: {pfad}').format(pfad=self.ini_pfad()), foreground=MUT)
        exe_m = exe_pfeifreichweite(self.spiel)
        aktiv = status.get('whistle_now', '')
        teile = []
        if exe_m:
            teile.append(tr('In der Exe auf der Platte: {m} m').format(m=exe_m))
        if aktiv and aktiv not in ('-1', ''):
            teile.append(tr('im laufenden Spiel zuletzt: {m} m').format(m=aktiv))
        self.whistle_hinweis.configure(text=', '.join(teile))
        self.status_rechts.configure(text=f'{TOOL_NAME} {VERSION}')
        self.log_aktualisieren()

    def status_lesen(self):
        try:
            with open(os.path.join(self.spiel, STATUS_NAME), encoding='utf-8', errors='replace') as f:
                return dict(l.strip().split('=', 1) for l in f if '=' in l)
        except OSError:
            return {}

    def log_aktualisieren(self):
        pfad = os.path.join(self.spiel, LOG_NAME) if self.spiel else ''
        try:
            with open(pfad, encoding='utf-8', errors='replace') as f:
                zeilen = f.read().splitlines()[-200:]
        except OSError:
            zeilen = [tr('(noch kein Plugin-Log im Spielordner)')]
        text = '\n'.join(zeilen)
        if getattr(self, '_log_text', None) == text:
            return
        self._log_text = text
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        for zeile in zeilen:
            tag = 'err' if 'FEHLER' in zeile else ('gold' if ('SubHP' in zeile or 'Kill(' in zeile or 'Sturz' in zeile) else ('mut' if zeile.startswith('===') or zeile.startswith('(') else ''))
            self.log.insert('end', zeile + '\n', tag)
        self.log.configure(state='disabled')
        self.log.see('end')

    def log_leeren(self):
        if not self.spiel:
            return
        try:
            open(os.path.join(self.spiel, LOG_NAME), 'w').close()
            self._log_text = None
            self.log_aktualisieren()
            self.melden(tr('Log geleert.'), 'ok')
        except OSError as e:
            self.melden(tr('Log leeren fehlgeschlagen: {fehler}').format(fehler=e), 'err')

    def _tick(self):
        if not self.winfo_exists():
            return
        try:
            self.aktualisiere_status()
        except tk.TclError:
            return
        self._tick_job = self.after(1500, self._tick)

    def destroy(self):
        for job in (getattr(self, '_tick_job', None), self._speicher_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._tick_job = self._speicher_job = None
        super().destroy()

    # ---------------------------------------------------------- Hilfe
    def guide_starten(self):
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.lift()
            return
        self.guide = Guide(self)

    def kurzanleitung(self):
        Textfenster(self, tr('Kurzanleitung'), tr(KURZANLEITUNG))

    def ueber(self):
        dlg = tk.Toplevel(self)
        dlg.title(tr('Über'))
        dlg.transient(self)
        dlg.resizable(False, False)
        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=TOOL_NAME, style='Brand.TLabel').pack(anchor='w')
        ttk.Label(frame, text=tr('Version {v}').format(v=VERSION), style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        ttk.Label(frame, text=tr(UEBER_TEXT), wraplength=460, justify='left').pack(anchor='w', pady=(0, 10))
        for name, url in self.links():
            lnk = ttk.Label(frame, text=f'{name}: {url}', style='Link.TLabel', cursor='hand2')
            lnk.pack(anchor='w', padx=(12, 0))
            lnk.bind('<Button-1>', lambda e, u=url: webbrowser.open(u))
        ttk.Button(frame, text=tr('Schließen'), style='Accent.TButton', command=dlg.destroy).pack(anchor='e', pady=(14, 0))
        theme.dark_titlebar(dlg)
        dlg.grab_set()

    def beenden(self):
        if self._speicher_job:
            self.after_cancel(self._speicher_job)
            self._speicher_job = None
            self.anwenden()
        self.destroy()


class Textfenster(tk.Toplevel):
    def __init__(self, master, titel, text):
        super().__init__(master)
        self.title(titel)
        self.transient(master)
        self.geometry('620x520')
        t = tk.Text(self, wrap='word', padx=12, pady=10)
        sb = ttk.Scrollbar(self, orient='vertical', command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        t.pack(fill='both', expand=True)
        t.insert('1.0', text)
        t.configure(state='disabled')
        theme.dark_titlebar(self)


# --------------------------------------------------------------------------
# Guide beim ersten Start
# --------------------------------------------------------------------------

class Guide(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.i = 0
        self.frames = []
        self.title(tr('Guide'))
        self.transient(app)
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.configure(background=PANEL)
        self.protocol('WM_DELETE_WINDOW', self.schliessen)
        self.schritte = [
            (tr('Willkommen'), tr('Dieses Tool stellt ein, wie viel Schaden Two Worlds 1 beim Fallen und Rutschen macht. Die Werte wirken sofort, auch während das Spiel läuft.'), None),
            (tr('Status rechts'), tr('Hier siehst du den Spielordner, ob TWSE und das Plugin da sind und wann das Plugin zuletzt gelaufen ist. Fehlt das Plugin, klicke "Plugin installieren".'), 'status_block'),
            (tr('Fallschaden'), tr('Schalter aus = gar kein Fallschaden. Der Regler skaliert den Originalschaden: 50 ist die Hälfte, 0 ist nichts. Darunter die Höhen, ab denen Schaden und Sturztod beginnen.'), 'box_fall'),
            (tr('Rutschschaden'), tr('Beim Hinunterrutschen steiler Hänge zieht das Spiel alle paar Ticks Prozent der Lebenspunkte ab. Prozent und Anlaufzeit lassen sich hier setzen.'), 'box_slide'),
            (tr('Pferd'), tr('"Pferd unsterblich" schützt das zuletzt gerittene Pferd. Die Pfeifreichweite gilt nur, wenn ihr Schalter an ist; sonst bleibt der Wert aus der Exe.'), 'box_horse'),
            (tr('Lava'), tr('Lava zieht jedes Bild 5 % der Lebenspunkte ab. Der erste Regler ändert die Prozent, der zweite, wie oft ein Tick kommt. Beides zusammen bestimmt, wie lange man in Lava überlebt.'), 'box_lava'),
            (tr('Diagnose'), tr('Das Protokoll schreibt jeden Lebenspunkt-Verlust des Helden mit Aufrufer in TWExtended.log. Nur zum Suchen nach weiteren Schadensquellen nötig, sonst aus lassen.'), 'box_diag'),
            (tr('Anwenden'), tr('Jede Änderung wird nach einer Sekunde automatisch gespeichert. Der Knopf "Anwenden" (Strg+S) macht es sofort. "Originalwerte" stellt das Spiel zurück.'), 'btn_anwenden'),
            (tr('Fertig'), tr('Das Spiel muss über TwoWorldsExtended.exe (TWSE) starten, sonst lädt kein Plugin. Diesen Guide gibt es jederzeit unter Hilfe > Guide starten oder mit F1.'), None),
        ]
        wrap = ttk.Frame(self, style='Panel.TFrame', padding=(14, 10))
        wrap.pack(fill='both', expand=True)
        self.kopf = ttk.Label(wrap, text='', style='PanelTitle.TLabel', padding=(0, 0))
        self.kopf.pack(anchor='w')
        self.titel = ttk.Label(wrap, text='', style='Panel.TLabel', font=FONT_H2, foreground=GOLD)
        self.titel.pack(anchor='w', pady=(4, 2))
        self.text = ttk.Label(wrap, text='', style='Panel.TLabel', wraplength=360, justify='left')
        self.text.pack(anchor='w', pady=(0, 10))
        self.nicht_mehr = tk.IntVar(value=0)
        ttk.Checkbutton(wrap, text=tr('Beim Start nicht mehr anzeigen'), variable=self.nicht_mehr,
                        style='Panel.TCheckbutton').pack(anchor='w', pady=(0, 8))
        reihe = ttk.Frame(wrap, style='Panel.TFrame')
        reihe.pack(fill='x')
        self.btn_zurueck = ttk.Button(reihe, text=tr('Zurück'), command=self.zurueck)
        self.btn_zurueck.pack(side='left')
        self.btn_weiter = ttk.Button(reihe, text=tr('Weiter'), style='Accent.TButton', command=self.weiter)
        self.btn_weiter.pack(side='left', padx=(6, 0))
        ttk.Button(reihe, text=tr('Beenden'), command=self.schliessen).pack(side='right')
        self.zeigen()
        self.update_idletasks()
        x = app.winfo_rootx() + 24
        y = app.winfo_rooty() + 60
        self.geometry(f'+{x}+{y}')
        theme.dark_titlebar(self)

    def ziel(self, name):
        if name == 'status_block':
            return self.app.status_zeilen['spiel'].master.master
        return getattr(self.app, name, None) if name else None

    def zeigen(self):
        titel, text, widget = self.schritte[self.i]
        self.kopf.configure(text=tr('Schritt {n} von {m}').format(n=self.i + 1, m=len(self.schritte)))
        self.titel.configure(text=titel)
        self.text.configure(text=text)
        self.btn_zurueck.state(['!disabled'] if self.i > 0 else ['disabled'])
        self.btn_weiter.configure(text=tr('Fertig') if self.i == len(self.schritte) - 1 else tr('Weiter'))
        self.markieren(self.ziel(widget))

    def markieren(self, widget):
        for f in self.frames:
            f.destroy()
        self.frames = []
        if widget is None:
            return
        root = self.app
        root.update_idletasks()
        x = widget.winfo_rootx() - root.winfo_rootx()
        y = widget.winfo_rooty() - root.winfo_rooty()
        w, h, t = widget.winfo_width(), widget.winfo_height(), 3
        for fx, fy, fw, fh in ((x, y, w, t), (x, y + h - t, w, t), (x, y, t, h), (x + w - t, y, t, h)):
            f = tk.Frame(root, background=GOLD)
            f.place(x=fx, y=fy, width=fw, height=fh)
            self.frames.append(f)

    def weiter(self):
        if self.i >= len(self.schritte) - 1:
            self.schliessen()
            return
        self.i += 1
        self.zeigen()

    def zurueck(self):
        if self.i > 0:
            self.i -= 1
            self.zeigen()

    def schliessen(self):
        self.markieren(None)
        if self.nicht_mehr.get() or self.i == len(self.schritte) - 1:
            self.app.konfig['guide_seen'] = True
            self.app.konfig.save()
        self.destroy()


# --------------------------------------------------------------------------
# Texte
# --------------------------------------------------------------------------

KURZANLEITUNG = """tw1_Extendet-settings - Kurzanleitung

1. Voraussetzung: Two Worlds 1 (1.7) mit TWSE von buglord. Einmal den TWSE-Patcher auf TwoWorlds.exe anwenden, es entsteht TwoWorldsExtended.exe. Das Spiel immer darüber starten.
2. Plugin: Der Knopf "Plugin installieren" kopiert TWExtended.dll nach <Spiel>\\TWSEPlugins\\.
3. Werte: Jede Änderung landet nach einer Sekunde in <Spiel>\\tw1_Extendet-settings.ini. Das Plugin prüft die Datei jede Sekunde und übernimmt sie sofort, auch mitten im Spiel.
4. Fallschaden: Das Spiel rechnet Schaden in Prozent der maximalen Lebenspunkte: (Höhe - 8) * 5,9 %. Ab Höhe 25 ist der Held sofort tot, ebenso wenn der Schaden zum Töten reicht. Alle vier Größen sind hier einstellbar, der Schalter nimmt alles weg.
5. Rutschschaden: Wer länger als 30 Ticks einen steilen Hang hinunterrutscht, verliert alle fünf Spielschritte 10 % der Lebenspunkte. Beides einstellbar.
6. Pferd: "Pferd unsterblich" fängt jeden Schaden am zuletzt gerittenen Pferd ab und hält seine Lebenspunkte voll. Die Pfeifreichweite (Original 40 m) sitzt als Zahl in der Exe; das Plugin setzt sie im Speicher, wenn der Schalter an ist, sonst bleibt der Exe-Wert. Gerufen wird nur das zuletzt gerittene Pferd, und nur wenn es noch geladen ist.
7. Lava: Wer in Lava schwimmt, verliert jedes Bild 5 % der maximalen Lebenspunkte. Prozent und Takt (alle n Bilder) sind einstellbar, der Schalter nimmt den Schaden ganz weg.
8. Konsole im Spiel: twext.reload liest die Datei neu, twext.status zeigt die Werte, twext.log 1 schaltet das Protokoll ein.

Originalwerte: Fall an, 100 %, ab 8.0, tot ab 25.0, tödlich an; Rutschen an, 10 %, ab 30 Ticks; Lava an, 5 %, jedes Bild; Pferd sterblich, Pfeife 40 m.
"""

UEBER_TEXT = """Stellt Fall-, Rutsch- und Lavaschaden, Pferde-Unsterblichkeit und die Pfeifreichweite von Two Worlds 1 ein. Die Werte schreibt das Tool in eine Datei im Spielordner, das TWSE-Plugin TWExtended.dll wendet sie im laufenden Spiel an. Baut auf dem Two Worlds Script Extender von buglord auf. Lizenz CC0."""

TEXTE_EN = {
    'Datei': 'File', 'Ansicht': 'View', 'Hilfe': 'Help',
    'Anwenden': 'Apply', 'Originalwerte': 'Original values',
    'Spielordner wählen ...': 'Choose game folder ...', 'Spielordner öffnen': 'Open game folder',
    'Plugin installieren': 'Install plugin', 'Plugin aktualisieren': 'Update plugin', 'Beenden': 'Quit',
    'Sprache': 'Language', 'Guide starten': 'Start guide', 'Kurzanleitung': 'Quick guide', 'Über': 'About',
    'GitHub-Repo': 'GitHub repo', 'Guide-Seite': 'Guide page', 'Community': 'Community',
    'Fallschaden': 'Fall damage', 'Fallschaden an': 'Fall damage on',
    'Aus: kein Schaden, kein Sturztod, keine Benommenheit nach der Landung.': 'Off: no damage, no fall death, no stun after landing.',
    'Schaden in Prozent des Originals': 'Damage in percent of the original',
    '100 = wie im Spiel, 50 = halber Schaden, 0 = keiner. Das Spiel rechnet in Prozent der maximalen Lebenspunkte, deshalb wirkt es auf jeder Stufe gleich.': '100 = as in the game, 50 = half damage, 0 = none. The game works in percent of max HP, so it feels the same on every level.',
    'Schaden ab Fallhöhe': 'Damage starts at fall height', 'Original 8.0. Darunter passiert nichts.': 'Original 8.0. Below that nothing happens.',
    'Sofort tot ab Fallhöhe': 'Instant death at fall height', 'Original 25.0. 0 = nie durch die Höhe allein sterben.': 'Original 25.0. 0 = never die from height alone.',
    'Sofort tot, wenn der Schaden zum Töten reicht': 'Instant death when the damage would kill you',
    'Original an. Aus: der Schaden wird normal abgezogen, das Spiel entscheidet über die Lebenspunkte.': 'Original on. Off: the damage is subtracted normally and the game decides by hit points.',
    'Rutschschaden': 'Slide damage', 'Rutschschaden (steile Hänge)': 'Slide damage (steep slopes)', 'Rutschschaden an': 'Slide damage on',
    'Schaden, wenn der Held einen zu steilen Hang hinunterrutscht.': 'Damage while the hero slides down a slope that is too steep.',
    'Prozent der Lebenspunkte je Schadenstick': 'Percent of hit points per damage tick',
    'Original 10. Ein Tick alle fünf Spielschritte, solange gerutscht wird.': 'Original 10. One tick every five game steps while sliding.',
    'Ticks Rutschen bis zum ersten Schaden': 'Ticks of sliding before the first damage',
    'Original 30. Höher = länger schadlos rutschen.': 'Original 30. Higher = slide longer without damage.',
    'Pferd': 'Horse', 'Pferd unsterblich': 'Horse immortal',
    'Das zuletzt gerittene Pferd nimmt keinen Schaden mehr; seine Lebenspunkte bleiben voll.': 'The last ridden horse takes no more damage; its hit points stay full.',
    'Pfeifreichweite setzen': 'Set whistle range',
    'Aus = die Exe bleibt, wie sie ist (Original 40 m, oder ein bereits gepatchter Wert).': 'Off = the exe stays as it is (original 40 m, or an already patched value).',
    'Pfeifreichweite in Metern': 'Whistle range in meters',
    'Original 40 m. Gerufen wird nur das zuletzt gerittene Pferd, und nur, wenn es noch geladen ist und einen Weg findet.': 'Original 40 m. Only the last ridden horse is called, and only while it is still loaded and finds a path.',
    'In der Exe auf der Platte: {m} m': 'In the exe on disk: {m} m',
    'im laufenden Spiel zuletzt: {m} m': 'last seen in the running game: {m} m',
    '"Pferd unsterblich" schützt das zuletzt gerittene Pferd. Die Pfeifreichweite gilt nur, wenn ihr Schalter an ist; sonst bleibt der Wert aus der Exe.': '"Horse immortal" protects the last ridden horse. The whistle range only applies while its switch is on; otherwise the exe value stays.',
    'Lavaschaden': 'Lava damage', 'Lavaschaden an': 'Lava damage on', 'Diagnose': 'Diagnostics',
    'Lava verhält sich wie Wasser, zieht aber Lebenspunkte ab, solange der Held drin schwimmt.': 'Lava behaves like water but drains hit points while the hero swims in it.',
    'Original 5. Auch hier rechnet das Spiel in Prozent der maximalen Lebenspunkte.': 'Original 5. Here too the game works in percent of max hit points.',
    'Ein Schadenstick alle n Bilder': 'One damage tick every n frames',
    'Original 1 = jedes Bild, also bei 5 % nach 20 Bildern tot. 10 = nur jedes zehnte Bild.': 'Original 1 = every frame, so at 5 % you are dead after 20 frames. 10 = only every tenth frame.',
    'Lava zieht jedes Bild 5 % der Lebenspunkte ab. Der erste Regler ändert die Prozent, der zweite, wie oft ein Tick kommt. Beides zusammen bestimmt, wie lange man in Lava überlebt.': 'Lava takes 5 % of hit points every frame. The first slider changes the percent, the second how often a tick comes. Together they decide how long you survive in lava.',
    'Das Protokoll schreibt jeden Lebenspunkt-Verlust des Helden mit Aufrufer in TWExtended.log. Nur zum Suchen nach weiteren Schadensquellen nötig, sonst aus lassen.': 'The log writes every hit point loss of the hero with its caller to TWExtended.log. Only needed to hunt for further damage sources, otherwise leave it off.',
    'Jeden Lebenspunkt-Verlust des Helden protokollieren': 'Log every hit point loss of the hero',
    'Schreibt Schaden, Lebenspunkte und Aufrufer nach TWExtended.log.': 'Writes damage, hit points and caller to TWExtended.log.',
    'Status': 'Status', 'Log leeren': 'Clear log', 'Plugin-Log': 'Plugin log',
    'Geändert, wird gleich angewendet ...': 'Changed, applying in a moment ...',
    'Einstellungen aus dem Spielordner geladen.': 'Settings loaded from the game folder.',
    'Noch keine Einstellungsdatei, Originalwerte angezeigt.': 'No settings file yet, showing original values.',
    'Spielordner nicht gefunden. Datei > Spielordner wählen.': 'Game folder not found. File > Choose game folder.',
    'Schreiben fehlgeschlagen: {fehler}': 'Writing failed: {fehler}',
    'Angewendet {zeit}. Das laufende Spiel übernimmt die Werte innerhalb einer Sekunde.': 'Applied {zeit}. The running game picks the values up within a second.',
    'Gespeichert {zeit}. Wirkt beim nächsten Start über TwoWorldsExtended.exe.': 'Saved {zeit}. Takes effect on the next start via TwoWorldsExtended.exe.',
    'Spielordner von Two Worlds wählen': 'Choose the Two Worlds game folder',
    'In diesem Ordner liegt keine TwoWorlds.exe.': 'There is no TwoWorlds.exe in this folder.',
    'TWExtended.dll liegt nicht neben dem Tool.': 'TWExtended.dll is not next to the tool.',
    'Bitte das Spiel beenden, dann das Plugin installieren.': 'Please quit the game, then install the plugin.',
    'Kopieren fehlgeschlagen: {fehler}': 'Copy failed: {fehler}',
    'Plugin kopiert. Es fehlt aber noch TWSE ({dateien}): einmal den TWSE-Patcher von buglord auf TwoWorlds.exe anwenden, danach immer über TwoWorldsExtended.exe starten.': 'Plugin copied. TWSE is still missing ({dateien}): run the TWSE patcher by buglord once on TwoWorlds.exe, then always start via TwoWorldsExtended.exe.',
    'Plugin installiert. Spiel über TwoWorldsExtended.exe starten.': 'Plugin installed. Start the game via TwoWorldsExtended.exe.',
    'Spielordner: nicht gefunden': 'Game folder: not found', 'Spielordner: {pfad}': 'Game folder: {pfad}',
    'TWSE (TwoWorldsExtended.exe): {zustand}': 'TWSE (TwoWorldsExtended.exe): {zustand}',
    'vorhanden': 'present', 'fehlt': 'missing',
    'Plugin TWExtended.dll: {zustand}': 'Plugin TWExtended.dll: {zustand}',
    'installiert': 'installed', 'nicht installiert': 'not installed',
    'Plugin zuletzt aktiv: {zeit}': 'Plugin last active: {zeit}',
    'Plugin zuletzt aktiv: noch nie (Spiel noch nicht über TWSE gestartet)': 'Plugin last active: never (game not started via TWSE yet)',
    'Spiel läuft: {zustand}': 'Game running: {zustand}', 'ja': 'yes', 'nein': 'no',
    'Datei: {pfad}': 'File: {pfad}',
    '(noch kein Plugin-Log im Spielordner)': '(no plugin log in the game folder yet)',
    'Log geleert.': 'Log cleared.', 'Log leeren fehlgeschlagen: {fehler}': 'Clearing the log failed: {fehler}',
    'Version {v}': 'Version {v}', 'Schließen': 'Close',
    'Guide': 'Guide', 'Willkommen': 'Welcome',
    'Dieses Tool stellt ein, wie viel Schaden Two Worlds 1 beim Fallen und Rutschen macht. Die Werte wirken sofort, auch während das Spiel läuft.': 'This tool sets how much damage Two Worlds 1 deals for falling and sliding. Values take effect immediately, even while the game is running.',
    'Status rechts': 'Status on the right',
    'Hier siehst du den Spielordner, ob TWSE und das Plugin da sind und wann das Plugin zuletzt gelaufen ist. Fehlt das Plugin, klicke "Plugin installieren".': 'Here you see the game folder, whether TWSE and the plugin are present and when the plugin last ran. If the plugin is missing, click "Install plugin".',
    'Schalter aus = gar kein Fallschaden. Der Regler skaliert den Originalschaden: 50 ist die Hälfte, 0 ist nichts. Darunter die Höhen, ab denen Schaden und Sturztod beginnen.': 'Switch off = no fall damage at all. The slider scales the original damage: 50 is half, 0 is nothing. Below are the heights where damage and fall death begin.',
    'Beim Hinunterrutschen steiler Hänge zieht das Spiel alle paar Ticks Prozent der Lebenspunkte ab. Prozent und Anlaufzeit lassen sich hier setzen.': 'While sliding down steep slopes the game takes a percentage of hit points every few ticks. Percent and grace time are set here.',
    'Lava': 'Lava',
    'Jede Änderung wird nach einer Sekunde automatisch gespeichert. Der Knopf "Anwenden" (Strg+S) macht es sofort. "Originalwerte" stellt das Spiel zurück.': 'Every change is saved automatically after a second. The "Apply" button (Ctrl+S) does it right away. "Original values" restores the game.',
    'Fertig': 'Done',
    'Das Spiel muss über TwoWorldsExtended.exe (TWSE) starten, sonst lädt kein Plugin. Diesen Guide gibt es jederzeit unter Hilfe > Guide starten oder mit F1.': 'The game must start via TwoWorldsExtended.exe (TWSE), otherwise no plugin loads. This guide is always available under Help > Start guide or with F1.',
    'Beim Start nicht mehr anzeigen': "Don't show at startup", 'Zurück': 'Back', 'Weiter': 'Next',
    'Schritt {n} von {m}': 'Step {n} of {m}',
    KURZANLEITUNG: """tw1_Extendet-settings - Quick guide

1. Requirement: Two Worlds 1 (1.7) with TWSE by buglord. Run the TWSE patcher once on TwoWorlds.exe; it creates TwoWorldsExtended.exe. Always start the game through it.
2. Plugin: The "Install plugin" button copies TWExtended.dll to <Game>\\TWSEPlugins\\.
3. Values: Every change lands in <Game>\\tw1_Extendet-settings.ini after a second. The plugin checks the file every second and applies it right away, even mid-game.
4. Fall damage: The game computes damage in percent of max HP: (height - 8) * 5.9 %. From height 25 the hero dies instantly, likewise when the damage would kill. All four numbers are adjustable here; the switch removes everything.
5. Slide damage: Sliding down a steep slope for more than 30 ticks costs 10 % of hit points every five game steps. Both adjustable.
6. Horse: "Horse immortal" drops all damage to the last ridden horse and keeps its hit points full. The whistle range (original 40 m) is a number inside the exe; the plugin sets it in memory while its switch is on, otherwise the exe value stays. Only the last ridden horse is called, and only while it is still loaded.
7. Lava: Swimming in lava costs 5 % of max hit points every frame. Percent and rate (every n frames) are adjustable; the switch removes the damage entirely.
8. In-game console: twext.reload re-reads the file, twext.status shows the values, twext.log 1 turns on the log.

Original values: fall on, 100 %, from 8.0, death from 25.0, lethal on; slide on, 10 %, from 30 ticks; lava on, 5 %, every frame; horse mortal, whistle 40 m.
""",
    UEBER_TEXT: """Adjusts fall, slide and lava damage, horse immortality and the whistle range of Two Worlds 1. The tool writes the values to a file in the game folder; the TWSE plugin TWExtended.dll applies them in the running game. Built on the Two Worlds Script Extender by buglord. License CC0.""",
}


def main():
    global SPRACHE
    konfig = Konfig()
    while True:
        SPRACHE = os.environ.get('TWEXT_LANG') or konfig.get('lang') or systemsprache()
        app = App(konfig)
        app.mainloop()
        if not app.restart:
            break


if __name__ == '__main__':
    main()
