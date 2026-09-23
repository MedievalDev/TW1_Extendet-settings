"""tw1_Extendet-settings - Schadensarten von Two Worlds 1 einstellen.

Schreibt tw1_Extendet-settings.ini in den Spielordner; das TWSE-Plugin
TWExtended.dll liest die Datei beim Start und bei jeder Aenderung im
laufenden Spiel. Design nach PY_TOOL_DESIGN.md (Dark Theme, theme.py).
Deutsche Texte sind die Quelle (tr), englische Tabelle am Dateiende.
"""
import ctypes
import datetime
import traceback
import json
import os
import shutil
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import theme
import twse_patch
import foxfeedback_ui
from theme import (BG, PANEL, FIELD, CANVAS_BG, LINE, SEL, INK, MUT, DIM,
                   GOLD, GOLD_HI, OK, ERR, FONT, FONT_BOLD, FONT_SMALL,
                   FONT_MONO, FONT_H2)

TOOL_NAME = 'tw1_Extendet-settings'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_Extendet-settings'
SITE_URL = 'https://alchemy-fox.de/'
GUIDE_URL = 'https://alchemy-fox.de/game/TW1_ExtendedSettings/'
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
UNTESTED = os.path.join(RES, 'untested.json')
FEEDBACK_SLUG = 'extendedsettings'
VERSION = '1.3.1'

# Originalwerte des Spiels (TwoWorlds.exe 1.7), siehe tw_extended.c
STANDARD = {
    'fall_enabled': 1, 'fall_percent': 100, 'fall_min': 8.0, 'fall_death': 25.0,
    'fall_lethal': 1,
    'slide_enabled': 1, 'slide_percent': 10, 'slide_grace': 30,
    'lava_enabled': 1, 'lava_percent': 5, 'lava_every': 1,
    'horse_immortal': 0, 'whistle_set': 0, 'whistle_m': 40,
    'log_damage': 0,
    'auto_start': 0, 'auto_min': 1, 'auto_close': 1,
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
    ('Autostart', 'Enabled', 'auto_start', int),
    ('Autostart', 'Minimized', 'auto_min', int),
    ('Autostart', 'CloseWithGame', 'auto_close', int),
)
TOOL_MUTEX = 'Local\\TW1ExtendedSettings'   # dieselbe Sperre prueft das Plugin vor dem Autostart


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


def tool_befehl():
    """(Programm, Argumente), mit denen das Plugin dieses Tool startet: die Exe
    selbst, im Skriptmodus pythonw.exe mit dem Skriptpfad."""
    if FROZEN:
        return os.path.abspath(sys.executable), ''
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return (w if os.path.isfile(w) else exe), f'"{os.path.abspath(__file__)}"'


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
        f'LogDamage={int(w["log_damage"])}      ; 1 = log every HP loss of the hero to TWExtended.log\n'
        '\n[Autostart]\n'
        f'Enabled={int(w["auto_start"])}        ; 1 = the plugin opens this tool when the game starts\n'
        f'Minimized={int(w["auto_min"])}      ; 1 = open it minimized, the game keeps the focus\n'
        f'CloseWithGame={int(w["auto_close"])}  ; 1 = the tool closes when the game ends\n'
        '; ToolPath and ToolArgs are written by the tool itself (no comments on these lines)\n'
        f'ToolPath={tool_befehl()[0]}\n'
        f'ToolArgs={tool_befehl()[1]}\n')
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

def einzige_instanz():
    """Legt die Sperre an, die das Plugin vor dem Autostart prueft. Gibt den
    Handle zurueck, oder None, wenn das Tool schon laeuft."""
    try:
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        h = k32.CreateMutexW(None, False, TOOL_MUTEX)
        if h and k32.GetLastError() == 183:          # ERROR_ALREADY_EXISTS
            k32.CloseHandle(ctypes.c_void_p(h))
            return None
        return h or True
    except Exception:
        return True


def fenster_nach_vorn():
    """Holt das schon laufende Tool nach vorn (Fenstertitel beginnt mit dem Namen)."""
    try:
        u32 = ctypes.windll.user32
        gefunden = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def je_fenster(hwnd, _l):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value.startswith(TOOL_NAME + ' ') and u32.IsWindowVisible(hwnd):
                    gefunden.append(hwnd)
                    return False
            return True
        u32.EnumWindows(je_fenster, 0)
        if gefunden:
            u32.ShowWindow(ctypes.c_void_p(gefunden[0]), 9)      # SW_RESTORE
            u32.SetForegroundWindow(ctypes.c_void_p(gefunden[0]))
            return True
    except Exception:
        pass
    return False


def auf_prozessende_warten(pid, fertig):
    """Wartet in einem Thread auf das Ende des Spielprozesses und ruft dann
    fertig() - nur ein Flag setzen, Tk ist aus dem Thread tabu."""
    import threading

    def warten():
        try:
            k32 = ctypes.windll.kernel32
            k32.OpenProcess.restype = ctypes.c_void_p
            h = k32.OpenProcess(0x00100000, False, int(pid))    # SYNCHRONIZE
            if not h:
                fertig()                                        # schon beendet
                return
            k32.WaitForSingleObject(ctypes.c_void_p(h), 0xFFFFFFFF)
            k32.CloseHandle(ctypes.c_void_p(h))
        except Exception:
            return
        fertig()
    threading.Thread(target=warten, daemon=True).start()


def argumente(argv):
    """--from-game <PID> und --minimized, wie sie das Plugin beim Autostart mitgibt."""
    pid, mini = None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--from-game' and i + 1 < len(argv):
            try:
                pid = int(argv[i + 1])
            except ValueError:
                pid = None
            i += 1
        elif a == '--minimized':
            mini = True
        i += 1
    return pid, mini


class App(tk.Tk):
    def __init__(self, konfig, spiel_pid=None, minimiert=False):
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
        self.spiel_pid = spiel_pid           # vom Plugin gestartet: PID des Spiels
        self._spiel_zu = False               # setzt der Warte-Thread, _tick reagiert
        self._fb_wartet = False
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
        if minimiert:
            self.iconify()                   # minimiert, das Spiel behaelt den Fokus
        else:
            self.deiconify()
        theme.dark_titlebar(self)
        self.fb = foxfeedback_ui.FeedbackUI(
            self, FEEDBACK_SLUG, VERSION,
            cfg_get=lambda k, d=None: self.konfig.get(k, d),
            cfg_set=self._fb_set, lang=self.lang, tests_file=UNTESTED,
            open_guide=lambda *_a: self.guide_starten(),
            tool_name='TW1 Extended Settings', launcher=self._fb_launcher())
        self.report_callback_exception = self._absturz
        self._exp_labels()
        self._tick_job = self.after(1500, self._tick)
        if spiel_pid:
            # mit dem Spiel gestartet: kein Rundgang, das Testfenster erst, wenn
            # der Spieler das Fenster aufmacht
            auf_prozessende_warten(spiel_pid, self._spiel_beendet)
            self.fb.log.add('autostart from game')
            self._fb_wartet = True
            self.melden(tr('Mit dem Spiel gestartet. Änderungen wirken sofort im laufenden Spiel.'), 'ok')
        else:
            if not konfig.get('guide_seen'):
                self.after(400, self.guide_starten)
            self.after(1200, self.fb.start)

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
        m.add_command(label=tr('Installieren (TWSE + Plugin)'), command=self.plugin_installieren)
        m.add_command(label=tr('Spiel starten'), command=self.spiel_starten)
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
        self.fb.add_menu_items(m)
        m.add_separator()
        for name, url in self.links():
            m.add_command(label=f'{name}  ({url})', command=lambda u=url: webbrowser.open(u))
        m.add_separator()
        m.add_command(label=tr('Über'), command=self.ueber)

    # ---------------------------------------------------------- Rueckmeldung
    def _fb_set(self, key, value):
        self.konfig[key] = value
        self.konfig.save()

    def _fb_launcher(self):
        """Spiel fuer "Starten" im Testfenster: TwoWorldsExtended.exe zuerst,
        dazu ins Protokoll, was das Tool eingestellt hat (nur Werte)."""
        if not self.spiel or not os.path.isdir(self.spiel):
            return None

        def eigene_zeilen():
            w = self.werte_aus_feldern()
            zeilen = ['settings: ' + ', '.join(f'{k}={w[k]}' for k in sorted(w))]
            zeilen.append('twse present: %s' % self.twse_da())
            zeilen.append('plugin present: %s' % os.path.exists(
                os.path.join(self.spiel, 'TWSEPlugins', PLUGIN_DLL)))
            return zeilen
        la = foxfeedback_ui.tw1_launcher(self.spiel, extra_before=eigene_zeilen)
        la.names.sort(key=lambda n: (n.lower() != TWSE_EXE.lower(), n.lower()))
        return la

    def _exp_labels(self):
        """Bereiche mit ungetesteten Neuerungen tragen "(experimentell)",
        bis zwei Leute den Test bestaetigt haben."""
        for box, titel, label in ((self.box_lava, tr('Lavaschaden'), 'lava'),
                                  (self.box_horse, tr('Pferd'), 'horse')):
            if self.fb.experimental(label):
                titel += '  ' + tr('(experimentell)')
            if box.cget('text') != titel:
                box.configure(text=titel)

    def fehler(self, text, key, fp_en):
        """Fehlerdialog mit "Bug melden". ``key`` und ``fp_en`` sind feste
        englische Texte ohne Nutzerdaten (oeffentlicher Titel)."""
        self.fb.log.add('error ' + key)
        dlg = tk.Toplevel(self)
        dlg.title(TOOL_NAME)
        dlg.transient(self)
        dlg.resizable(False, False)
        rahmen = ttk.Frame(dlg, padding=16)
        rahmen.pack(fill='both', expand=True)
        ttk.Label(rahmen, text=text, foreground=ERR, wraplength=440, justify='left').pack(anchor='w', pady=(0, 12))
        reihe = ttk.Frame(rahmen)
        reihe.pack(fill='x')
        ttk.Button(reihe, text=tr('Bug melden'), command=lambda: self.fb.report_bug(
            parent=dlg, error_text=text, error_key=key,
            title=f'{key}: {fp_en}', fp_text=fp_en)).pack(side='left')
        ttk.Button(reihe, text=tr('Schließen'), style='Accent.TButton', command=dlg.destroy).pack(side='right')
        theme.dark_titlebar(dlg)
        dlg.grab_set()
        return dlg

    def _absturz(self, typ, wert, tb):
        """Unerwartete Ausnahme: Meldung mit Bug-melden-Knopf statt stillem Fehler."""
        stelle = ''
        for fs in reversed(traceback.extract_tb(tb)):
            if os.path.basename(fs.filename).startswith(('tw1_extended', 'twse_patch')):
                stelle = f'{os.path.basename(fs.filename)}:{fs.lineno}'
                break
        text = ''.join(traceback.format_exception(typ, wert, tb))
        try:
            self.fehler(tr('Unerwarteter Fehler: {fehler}').format(fehler=f'{typ.__name__}: {wert}') + '\n\n' + text[-1500:],
                        'crash', f'{typ.__name__} at {stelle or "unknown"}')
        except tk.TclError:
            pass

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

        # --- Autostart
        self.box_auto = ttk.LabelFrame(links, text=tr('Autostart'), padding=(10, 6))
        self.box_auto.pack(fill='x', pady=(0, 8))
        self.schalter(self.box_auto, 'auto_start', tr('Beim Spielstart öffnen'),
                      tr('Das Plugin öffnet dieses Tool, sobald das Spiel über TwoWorldsExtended.exe startet. So lassen sich die Werte mitten im Spiel ändern.'))
        self.schalter(self.box_auto, 'auto_min', tr('Minimiert starten, das Spiel behält den Fokus'),
                      tr('Empfohlen im Vollbild: Two Worlds kann sich minimieren, wenn ihm ein Fenster den Fokus nimmt. Mit zwei Monitoren den Haken herausnehmen.'))
        self.schalter(self.box_auto, 'auto_close', tr('Mit dem Spiel schließen'),
                      tr('Das Tool beendet sich, wenn das Spiel beendet wird. Gilt nur, wenn das Spiel es gestartet hat.'))
        self.auto_hinweis = ttk.Label(self.box_auto, text='', style='Muted.TLabel', wraplength=520, justify='left')
        self.auto_hinweis.pack(anchor='w', pady=(0, 2))

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
        self.btn_plugin = ttk.Button(knoepfe, text=tr('Installieren (TWSE + Plugin)'), command=self.plugin_installieren)
        self.btn_plugin.pack(fill='x', pady=(0, 4))
        self.btn_start = ttk.Button(knoepfe, text=tr('Spiel starten'), command=self.spiel_starten)
        self.btn_start.pack(fill='x', pady=(0, 4))
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
            self.fb.log.add('error settings.write_failed')
            return False
        self.werte = w
        self.fb.log.add('settings applied')
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
            self.fehler(tr('In diesem Ordner liegt keine TwoWorlds.exe.'), 'gamedir.no_exe', 'No TwoWorlds.exe in the chosen folder')
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

    def twse_quelle(self):
        for kandidat in (os.path.join(RES, TWSE_DLL),
                         os.path.join(HERE, 'bin', TWSE_DLL),
                         os.path.join(HERE, '..', 'twse', 'bin', TWSE_DLL)):
            if os.path.exists(kandidat):
                return kandidat
        return ''

    def twse_da(self):
        return all(os.path.exists(os.path.join(self.spiel, n)) for n in (TWSE_EXE, TWSE_DLL))

    def spiel_starten(self):
        if not self.spiel or not self.twse_da():
            self.melden(tr('TWSE fehlt noch. Erst "Installieren" klicken.'), 'err')
            return
        try:
            os.startfile(os.path.join(self.spiel, TWSE_EXE), cwd=self.spiel)
            self.melden(tr('Spiel gestartet (TwoWorldsExtended.exe).'), 'ok')
        except OSError as e:
            self.fehler(tr('Start fehlgeschlagen: {fehler}').format(fehler=e), 'game.start_failed', 'Starting TwoWorldsExtended.exe failed')

    def plugin_installieren(self):
        if not self.spiel:
            self.melden(tr('Spielordner nicht gefunden. Datei > Spielordner wählen.'), 'err')
            return
        quelle = self.plugin_quelle()
        if not quelle:
            self.fehler(tr('TWExtended.dll liegt nicht neben dem Tool.'), 'install.no_plugin', 'Plugin DLL missing next to the tool')
            return
        if prozess_laeuft((TWSE_EXE, 'TwoWorlds.exe')):
            messagebox.showwarning(TOOL_NAME, tr('Bitte das Spiel beenden, dann das Plugin installieren.'))
            return
        getan = []
        twse_dll = self.twse_quelle()
        if twse_dll:
            try:
                getan += twse_patch.installieren(self.spiel, twse_dll)
            except (OSError, ValueError) as e:
                self.fehler(tr('TWSE anlegen fehlgeschlagen: {fehler}').format(fehler=e), 'install.twse_failed', 'Creating TWSE failed')
                return
        ziel_ordner = os.path.join(self.spiel, 'TWSEPlugins')
        try:
            os.makedirs(ziel_ordner, exist_ok=True)
            shutil.copy2(quelle, os.path.join(ziel_ordner, PLUGIN_DLL))
            getan.append('TWSEPlugins\\' + PLUGIN_DLL)
        except OSError as e:
            self.fehler(tr('Kopieren fehlgeschlagen: {fehler}').format(fehler=e), 'install.copy_failed', 'Copying the plugin failed')
            return
        if not self.twse_da():
            messagebox.showinfo(TOOL_NAME, tr('Plugin kopiert, aber TWSE fehlt (twse.dll liegt nicht neben dem Tool). TWSE-Patcher von buglord auf TwoWorlds.exe anwenden, danach über TwoWorldsExtended.exe starten.'))
        else:
            self.fb.log.add('install ok')
            self.melden(tr('Installiert: {dateien}. Spiel mit "Spiel starten" oder über TwoWorldsExtended.exe starten.').format(dateien=', '.join(getan)), 'ok')
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
        alt = plugin and self.plugin_veraltet()
        z['plugin'].configure(text=tr('Plugin TWExtended.dll: {zustand}').format(
            zustand=tr('veraltet - "Aktualisieren" klicken') if alt else tr('installiert') if plugin else tr('nicht installiert')),
            foreground=ERR if (alt or not plugin) else OK)
        self._auto_hinweis(twse, plugin, alt)
        self.btn_plugin.configure(text=tr('Aktualisieren (TWSE + Plugin)') if (plugin and twse) else tr('Installieren (TWSE + Plugin)'))
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

    def plugin_veraltet(self):
        """True, wenn die Plugin-DLL im Spiel nicht die ist, die dieses Tool mitbringt."""
        quelle = self.plugin_quelle()
        ziel = os.path.join(self.spiel, 'TWSEPlugins', PLUGIN_DLL)
        try:
            if not quelle or os.path.getsize(quelle) != os.path.getsize(ziel):
                return bool(quelle)
            with open(quelle, 'rb') as a, open(ziel, 'rb') as b:
                return a.read() != b.read()
        except OSError:
            return False

    def _auto_hinweis(self, twse, plugin, alt):
        if not getattr(self, 'auto_hinweis', None):
            return
        try:
            an = int(self.vars['auto_start'].get())
        except (tk.TclError, ValueError, KeyError):
            an = 0
        if not an:
            text, farbe = '', MUT
        elif not (twse and plugin) or alt:
            text, farbe = tr('Der Autostart braucht das Plugin ab Version 1.3.0: rechts "Installieren" bzw. "Aktualisieren" klicken.'), ERR
        else:
            status = self.status_lesen().get('autostart', '')
            teile = status.split(',') if status else []
            letzte = teile[2] if len(teile) == 3 else ''
            text = {'1': tr('Beim letzten Spielstart wurde das Tool geöffnet.'),
                    '2': tr('Beim letzten Spielstart lief das Tool schon.'),
                    '-1': tr('Beim letzten Spielstart ging der Autostart schief - siehe Plugin-Log.')}.get(
                letzte, tr('Wirkt ab dem nächsten Spielstart über TwoWorldsExtended.exe.'))
            farbe = ERR if letzte == '-1' else MUT
        self.auto_hinweis.configure(text=text, foreground=farbe)

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

    def _spiel_beendet(self):
        self._spiel_zu = True                 # aus dem Warte-Thread: nur das Flag

    def _tick(self):
        if not self.winfo_exists():
            return
        if self._spiel_zu:
            self._spiel_zu = False
            self.spiel_pid = None
            if self.werte.get('auto_close', 1):
                self.beenden()
                return
            self.melden(tr('Das Spiel wurde beendet.'))
        if self._fb_wartet:
            try:
                if self.state() == 'normal':
                    self._fb_wartet = False
                    self.fb.start()
            except tk.TclError:
                pass
        try:
            self.aktualisiere_status()
            self._exp_labels()
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
            (tr('Status rechts'), tr('Hier siehst du den Spielordner, ob TWSE und das Plugin da sind und wann das Plugin zuletzt gelaufen ist. Fehlt etwas, klicke "Installieren": das legt TwoWorldsExtended.exe und twse.dll an und kopiert das Plugin. TwoWorlds.exe bleibt unverändert.'), 'status_block'),
            (tr('Fallschaden'), tr('Schalter aus = gar kein Fallschaden. Der Regler skaliert den Originalschaden: 50 ist die Hälfte, 0 ist nichts. Darunter die Höhen, ab denen Schaden und Sturztod beginnen.'), 'box_fall'),
            (tr('Rutschschaden'), tr('Beim Hinunterrutschen steiler Hänge zieht das Spiel alle paar Ticks Prozent der Lebenspunkte ab. Prozent und Anlaufzeit lassen sich hier setzen.'), 'box_slide'),
            (tr('Pferd'), tr('"Pferd unsterblich" schützt das zuletzt gerittene Pferd. Die Pfeifreichweite gilt nur, wenn ihr Schalter an ist; sonst bleibt der Wert aus der Exe.'), 'box_horse'),
            (tr('Lava'), tr('Lava zieht jedes Bild 5 % der Lebenspunkte ab. Der erste Regler ändert die Prozent, der zweite, wie oft ein Tick kommt. Beides zusammen bestimmt, wie lange man in Lava überlebt.'), 'box_lava'),
            (tr('Diagnose'), tr('Das Protokoll schreibt jeden Lebenspunkt-Verlust des Helden mit Aufrufer in TWExtended.log. Nur zum Suchen nach weiteren Schadensquellen nötig, sonst aus lassen.'), 'box_diag'),
            (tr('Autostart'), tr('Auf Wunsch öffnet das Plugin dieses Tool bei jedem Spielstart, minimiert, damit das Spiel im Vordergrund bleibt. Beim Beenden des Spiels schließt es sich wieder.'), 'box_auto'),
            (tr('Anwenden'), tr('Jede Änderung wird nach einer Sekunde automatisch gespeichert. Der Knopf "Anwenden" (Strg+S) macht es sofort. "Originalwerte" stellt das Spiel zurück.'), 'btn_anwenden'),
            (tr('Fertig'), tr('Das Spiel muss über TwoWorldsExtended.exe (TWSE) starten, sonst lädt kein Plugin; der Knopf "Spiel starten" tut genau das. Diesen Guide gibt es jederzeit unter Hilfe > Guide starten oder mit F1.'), None),
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

1. Voraussetzung: Two Worlds 1 (1.7). Der Knopf "Installieren" legt TwoWorldsExtended.exe (Kopie von TwoWorlds.exe mit dem TWSE-Lader von buglord, plus 4-GB-Flag und Win11-Texteingabe-Fix) und twse.dll an. TwoWorlds.exe selbst wird nicht angefasst.
2. Plugin: Derselbe Knopf kopiert TWExtended.dll nach <Spiel>\\TWSEPlugins\\. Das Spiel immer über TwoWorldsExtended.exe starten, zum Beispiel mit "Spiel starten".
3. Werte: Jede Änderung landet nach einer Sekunde in <Spiel>\\tw1_Extendet-settings.ini. Das Plugin prüft die Datei jede Sekunde und übernimmt sie sofort, auch mitten im Spiel.
4. Fallschaden: Das Spiel rechnet Schaden in Prozent der maximalen Lebenspunkte: (Höhe - 8) * 5,9 %. Ab Höhe 25 ist der Held sofort tot, ebenso wenn der Schaden zum Töten reicht. Alle vier Größen sind hier einstellbar, der Schalter nimmt alles weg.
5. Rutschschaden: Wer länger als 30 Ticks einen steilen Hang hinunterrutscht, verliert alle fünf Spielschritte 10 % der Lebenspunkte. Beides einstellbar.
6. Pferd: "Pferd unsterblich" fängt jeden Schaden am zuletzt gerittenen Pferd ab und hält seine Lebenspunkte voll. Die Pfeifreichweite (Original 40 m) sitzt als Zahl in der Exe; das Plugin setzt sie im Speicher, wenn der Schalter an ist, sonst bleibt der Exe-Wert. Gerufen wird nur das zuletzt gerittene Pferd, und nur wenn es noch geladen ist.
7. Lava: Wer in Lava schwimmt, verliert jedes Bild 5 % der maximalen Lebenspunkte. Prozent und Takt (alle n Bilder) sind einstellbar, der Schalter nimmt den Schaden ganz weg.
8. Konsole im Spiel: twext.reload liest die Datei neu, twext.status zeigt die Werte, twext.log 1 schaltet das Protokoll ein.
9. Autostart: Ist "Beim Spielstart öffnen" an, startet das Plugin dieses Tool zusammen mit dem Spiel, auf Wunsch minimiert und ohne dem Spiel den Fokus zu nehmen, und schließt es mit dem Spiel wieder. Das Tool trägt seinen eigenen Pfad in die Datei ein. Es läuft nie doppelt.

Originalwerte: Fall an, 100 %, ab 8.0, tot ab 25.0, tödlich an; Rutschen an, 10 %, ab 30 Ticks; Lava an, 5 %, jedes Bild; Pferd sterblich, Pfeife 40 m.
"""

UEBER_TEXT = """Stellt Fall-, Rutsch- und Lavaschaden, Pferde-Unsterblichkeit und die Pfeifreichweite von Two Worlds 1 ein. Die Werte schreibt das Tool in eine Datei im Spielordner, das TWSE-Plugin TWExtended.dll wendet sie im laufenden Spiel an. Baut auf dem Two Worlds Script Extender (TWSE) von buglord auf und legt ihn selbst an; twse.dll und der Patch sind CC0. Lizenz CC0."""

TEXTE_EN = {
    'Autostart': 'Autostart',
    'Beim Spielstart öffnen': 'Open when the game starts',
    'Das Plugin öffnet dieses Tool, sobald das Spiel über TwoWorldsExtended.exe startet. So lassen sich die Werte mitten im Spiel ändern.':
        'The plugin opens this tool as soon as the game starts via TwoWorldsExtended.exe, so values can be changed mid-game.',
    'Minimiert starten, das Spiel behält den Fokus': 'Start minimized, the game keeps the focus',
    'Empfohlen im Vollbild: Two Worlds kann sich minimieren, wenn ihm ein Fenster den Fokus nimmt. Mit zwei Monitoren den Haken herausnehmen.':
        'Recommended in fullscreen: Two Worlds may minimize when a window takes its focus. With two monitors, untick it.',
    'Mit dem Spiel schließen': 'Close with the game',
    'Das Tool beendet sich, wenn das Spiel beendet wird. Gilt nur, wenn das Spiel es gestartet hat.':
        'The tool quits when the game quits. Only when the game started it.',
    'Der Autostart braucht das Plugin ab Version 1.3.0: rechts "Installieren" bzw. "Aktualisieren" klicken.':
        'Autostart needs the plugin from version 1.3.0: click "Install" or "Update" on the right.',
    'Beim letzten Spielstart wurde das Tool geöffnet.': 'At the last game start the tool was opened.',
    'Beim letzten Spielstart lief das Tool schon.': 'At the last game start the tool was already running.',
    'Beim letzten Spielstart ging der Autostart schief - siehe Plugin-Log.': 'At the last game start the autostart failed - see the plugin log.',
    'Wirkt ab dem nächsten Spielstart über TwoWorldsExtended.exe.': 'Takes effect from the next game start via TwoWorldsExtended.exe.',
    'Mit dem Spiel gestartet. Änderungen wirken sofort im laufenden Spiel.': 'Started with the game. Changes take effect right away in the running game.',
    'Das Spiel wurde beendet.': 'The game has ended.',
    'veraltet - "Aktualisieren" klicken': 'outdated - click "Update"',
    'Auf Wunsch öffnet das Plugin dieses Tool bei jedem Spielstart, minimiert, damit das Spiel im Vordergrund bleibt. Beim Beenden des Spiels schließt es sich wieder.':
        'If you like, the plugin opens this tool at every game start, minimized so the game stays in front. It closes again when the game ends.',
    'Datei': 'File', 'Ansicht': 'View', 'Hilfe': 'Help',
    'Anwenden': 'Apply', 'Originalwerte': 'Original values',
    'Spielordner wählen ...': 'Choose game folder ...', 'Spielordner öffnen': 'Open game folder',
    'Installieren (TWSE + Plugin)': 'Install (TWSE + plugin)', 'Aktualisieren (TWSE + Plugin)': 'Update (TWSE + plugin)',
    'Spiel starten': 'Start game', 'Beenden': 'Quit',
    'TWSE fehlt noch. Erst "Installieren" klicken.': 'TWSE is still missing. Click "Install" first.',
    'Spiel gestartet (TwoWorldsExtended.exe).': 'Game started (TwoWorldsExtended.exe).',
    'Start fehlgeschlagen: {fehler}': 'Start failed: {fehler}',
    'TWSE anlegen fehlgeschlagen: {fehler}': 'Creating TWSE failed: {fehler}',
    'Plugin kopiert, aber TWSE fehlt (twse.dll liegt nicht neben dem Tool). TWSE-Patcher von buglord auf TwoWorlds.exe anwenden, danach über TwoWorldsExtended.exe starten.': 'Plugin copied, but TWSE is missing (twse.dll is not next to the tool). Run buglord\'s TWSE patcher on TwoWorlds.exe, then start via TwoWorldsExtended.exe.',
    'Installiert: {dateien}. Spiel mit "Spiel starten" oder über TwoWorldsExtended.exe starten.': 'Installed: {dateien}. Start the game with "Start game" or via TwoWorldsExtended.exe.',
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
    'Lavaschaden': 'Lava damage', '(experimentell)': '(experimental)',
    'Bug melden': 'Report a bug', 'Unerwarteter Fehler: {fehler}': 'Unexpected error: {fehler}', 'Lavaschaden an': 'Lava damage on', 'Diagnose': 'Diagnostics',
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
    'Hier siehst du den Spielordner, ob TWSE und das Plugin da sind und wann das Plugin zuletzt gelaufen ist. Fehlt etwas, klicke "Installieren": das legt TwoWorldsExtended.exe und twse.dll an und kopiert das Plugin. TwoWorlds.exe bleibt unverändert.': 'Here you see the game folder, whether TWSE and the plugin are present and when the plugin last ran. If something is missing, click "Install": it creates TwoWorldsExtended.exe and twse.dll and copies the plugin. TwoWorlds.exe stays untouched.',
    'Schalter aus = gar kein Fallschaden. Der Regler skaliert den Originalschaden: 50 ist die Hälfte, 0 ist nichts. Darunter die Höhen, ab denen Schaden und Sturztod beginnen.': 'Switch off = no fall damage at all. The slider scales the original damage: 50 is half, 0 is nothing. Below are the heights where damage and fall death begin.',
    'Beim Hinunterrutschen steiler Hänge zieht das Spiel alle paar Ticks Prozent der Lebenspunkte ab. Prozent und Anlaufzeit lassen sich hier setzen.': 'While sliding down steep slopes the game takes a percentage of hit points every few ticks. Percent and grace time are set here.',
    'Lava': 'Lava',
    'Jede Änderung wird nach einer Sekunde automatisch gespeichert. Der Knopf "Anwenden" (Strg+S) macht es sofort. "Originalwerte" stellt das Spiel zurück.': 'Every change is saved automatically after a second. The "Apply" button (Ctrl+S) does it right away. "Original values" restores the game.',
    'Fertig': 'Done',
    'Das Spiel muss über TwoWorldsExtended.exe (TWSE) starten, sonst lädt kein Plugin; der Knopf "Spiel starten" tut genau das. Diesen Guide gibt es jederzeit unter Hilfe > Guide starten oder mit F1.': 'The game must start via TwoWorldsExtended.exe (TWSE), otherwise no plugin loads; the "Start game" button does exactly that. This guide is always available under Help > Start guide or with F1.',
    'Beim Start nicht mehr anzeigen': "Don't show at startup", 'Zurück': 'Back', 'Weiter': 'Next',
    'Schritt {n} von {m}': 'Step {n} of {m}',
    KURZANLEITUNG: """tw1_Extendet-settings - Quick guide

1. Requirement: Two Worlds 1 (1.7). The "Install" button creates TwoWorldsExtended.exe (a copy of TwoWorlds.exe with buglord's TWSE loader, plus the 4 GB flag and the Win11 text input fix) and twse.dll. TwoWorlds.exe itself is not touched.
2. Plugin: The same button copies TWExtended.dll to <Game>\\TWSEPlugins\\. Always start the game through TwoWorldsExtended.exe, for example with "Start game".
3. Values: Every change lands in <Game>\\tw1_Extendet-settings.ini after a second. The plugin checks the file every second and applies it right away, even mid-game.
4. Fall damage: The game computes damage in percent of max HP: (height - 8) * 5.9 %. From height 25 the hero dies instantly, likewise when the damage would kill. All four numbers are adjustable here; the switch removes everything.
5. Slide damage: Sliding down a steep slope for more than 30 ticks costs 10 % of hit points every five game steps. Both adjustable.
6. Horse: "Horse immortal" drops all damage to the last ridden horse and keeps its hit points full. The whistle range (original 40 m) is a number inside the exe; the plugin sets it in memory while its switch is on, otherwise the exe value stays. Only the last ridden horse is called, and only while it is still loaded.
7. Lava: Swimming in lava costs 5 % of max hit points every frame. Percent and rate (every n frames) are adjustable; the switch removes the damage entirely.
8. In-game console: twext.reload re-reads the file, twext.status shows the values, twext.log 1 turns on the log.
9. Autostart: With "Open when the game starts" on, the plugin starts this tool together with the game, minimized if you like and without taking the focus from the game, and closes it with the game. The tool writes its own path into the file. It never runs twice.

Original values: fall on, 100 %, from 8.0, death from 25.0, lethal on; slide on, 10 %, from 30 ticks; lava on, 5 %, every frame; horse mortal, whistle 40 m.
""",
    UEBER_TEXT: """Adjusts fall, slide and lava damage, horse immortality and the whistle range of Two Worlds 1. The tool writes the values to a file in the game folder; the TWSE plugin TWExtended.dll applies them in the running game. Built on the Two Worlds Script Extender (TWSE) by buglord and installs it itself; twse.dll and the patch are CC0. License CC0.""",
}


def main():
    global SPRACHE, _SPERRE
    pid, mini = argumente(sys.argv[1:])
    _SPERRE = einzige_instanz()
    if _SPERRE is None:
        if pid is None:
            fenster_nach_vorn()          # von Hand gestartet: das offene Fenster zeigen
        return
    konfig = Konfig()
    while True:
        SPRACHE = os.environ.get('TWEXT_LANG') or konfig.get('lang') or systemsprache()
        app = App(konfig, spiel_pid=pid, minimiert=mini)
        app.mainloop()
        if not app.restart:
            break
        mini = False                     # nach DE/EN-Wechsel normal zeigen


if __name__ == '__main__':
    main()
