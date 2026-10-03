"""Install on start (1.4.0): a normal start sets up TWSE and the plugin by itself
when something is missing or outdated, waits while the game runs, shows a rights
error once with "restart as administrator", and never installs when started
from the game. Plus the poison values (ini round trip) and the English table.
Everything happens in a temp game folder; twse_patch, the process check and
the folder search are stubbed, the real game is never touched.

    py -3.13 -m unittest tests.test_auto_install      (from the repo root)
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import foxfeedback  # noqa: E402
import foxfeedback_ui  # noqa: E402
import twse_patch  # noqa: E402
import tw1_extended_settings as M  # noqa: E402


def fake_twse(spiel, quelle):
    """Stand-in for twse_patch.installieren: just the two files."""
    for n in (M.TWSE_EXE, M.TWSE_DLL):
        with open(os.path.join(spiel, n), 'wb') as f:
            f.write(b'twse')
    return [M.TWSE_EXE, M.TWSE_DLL]


class AutoInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='twext_install_')
        cls._orig = (M.KONFIG_DATEI, M.DATEN, foxfeedback.submit, foxfeedback_ui.FeedbackUI.start,
                     twse_patch.installieren, M.prozess_laeuft, M.spielpfad_registry,
                     M._steam_bibliotheken, M.App.fehler, M.filedialog.askdirectory)
        M.DATEN = cls.tmp
        M.KONFIG_DATEI = os.path.join(cls.tmp, 'konfig.json')
        foxfeedback.submit = lambda *a, **k: (_ for _ in ()).throw(AssertionError('nothing is sent'))
        foxfeedback_ui.FeedbackUI.start = lambda self: None
        # never find the real game, never ask for a folder
        M.spielpfad_registry = lambda: ''
        M._steam_bibliotheken = lambda: []
        M.filedialog.askdirectory = lambda **k: ''
        cls.fehler = []
        M.App.fehler = lambda self, text, key, fp_en, extra=None: cls.fehler.append((key, extra))
        cls.quelle = M.App.plugin_quelle(None)
        assert cls.quelle, 'bin/TWSEPlugins/TWExtended.dll is needed for these tests'

    @classmethod
    def tearDownClass(cls):
        (M.KONFIG_DATEI, M.DATEN, foxfeedback.submit, foxfeedback_ui.FeedbackUI.start,
         twse_patch.installieren, M.prozess_laeuft, M.spielpfad_registry,
         M._steam_bibliotheken, M.App.fehler, M.filedialog.askdirectory) = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.spiel = tempfile.mkdtemp(prefix='game_', dir=self.tmp)
        with open(os.path.join(self.spiel, 'TwoWorlds.exe'), 'wb') as f:
            f.write(b'MZ')
        if os.path.exists(M.KONFIG_DATEI):
            os.remove(M.KONFIG_DATEI)
        self.fehler.clear()
        self.laeuft = False
        M.prozess_laeuft = lambda namen: self.laeuft
        twse_patch.installieren = fake_twse
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app.destroy()
            except Exception:
                pass

    def start(self, spiel_pid=None):
        konfig = M.Konfig()
        konfig.update(game_dir=self.spiel, lang='en', guide_seen=True)
        M.SPRACHE = 'en'
        self.app = M.App(konfig, spiel_pid=spiel_pid)
        return self.app

    def warten(self, sekunden):
        end = time.time() + sekunden
        while time.time() < end:
            self.app.update()
            time.sleep(0.02)

    def plugin(self):
        return os.path.join(self.spiel, 'TWSEPlugins', M.PLUGIN_DLL)

    def gleich(self):
        with open(self.plugin(), 'rb') as a, open(self.quelle, 'rb') as b:
            return a.read() == b.read()

    def test_missing_is_installed_on_start(self):
        self.start()
        self.warten(1.2)
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, M.TWSE_EXE)))
        self.assertTrue(self.gleich(), 'plugin copied')
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, M.INI_NAME)), 'ini written once')
        self.assertEqual(self.fehler, [])

    def test_waits_while_the_game_runs(self):
        self.laeuft = True
        self.start()
        self.warten(1.2)
        self.assertFalse(os.path.exists(self.plugin()), 'nothing while the game runs')
        self.assertTrue(self.app._auto_wartet)
        self.laeuft = False
        self.warten(2.0)                             # next tick picks it up
        self.assertTrue(self.gleich())
        self.assertFalse(self.app._auto_wartet)

    def test_outdated_plugin_is_replaced(self):
        fake_twse(self.spiel, '')
        os.makedirs(os.path.dirname(self.plugin()))
        with open(self.plugin(), 'wb') as f:
            f.write(b'old plugin')
        twse_patch.installieren = lambda *a: self.fail('an existing TWSE stays untouched')
        self.start()
        self.warten(1.2)
        self.assertTrue(self.gleich())
        self.assertEqual(self.fehler, [])

    def test_nothing_to_do_when_current(self):
        fake_twse(self.spiel, '')
        os.makedirs(os.path.dirname(self.plugin()))
        shutil.copy2(self.quelle, self.plugin())
        twse_patch.installieren = lambda *a: self.fail('nothing to install')
        self.start()
        self.warten(1.2)
        self.assertFalse(os.path.exists(os.path.join(self.spiel, M.INI_NAME)), 'no write when nothing is missing')

    def test_no_rights_shows_admin_restart_once(self):
        def verboten(spiel, quelle):
            raise PermissionError(13, 'Access is denied')
        twse_patch.installieren = verboten
        app = self.start()
        self.warten(1.2)
        self.assertEqual([k for k, _ in self.fehler], ['install.no_rights'])
        self.assertIsNotNone(self.fehler[0][1], 'the dialog offers a restart as administrator')
        self.assertEqual(app.konfig.get('auto_install_failed'), M.VERSION)
        app.auto_installieren()
        self.assertEqual(len(self.fehler), 1, 'shown once per version')

    def test_unknown_exe_is_reported_once(self):
        def fremd(spiel, quelle):
            raise ValueError('TwoWorlds.exe: keine bekannte Fassung (1.7 erwartet)')
        twse_patch.installieren = fremd
        app = self.start()
        self.warten(1.2)
        self.assertEqual([k for k, _ in self.fehler], ['install.twse_failed'])
        app.auto_installieren()
        self.assertEqual(len(self.fehler), 1)

    def test_button_still_works_after_a_failure(self):
        twse_patch.installieren = lambda *a: (_ for _ in ()).throw(PermissionError(13, 'denied'))
        app = self.start()
        self.warten(1.2)
        twse_patch.installieren = fake_twse
        app.plugin_installieren()
        self.assertTrue(self.gleich())

    def test_started_from_the_game_installs_nothing(self):
        game = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'])
        try:
            self.start(spiel_pid=game.pid)
            self.warten(1.2)
            self.assertFalse(os.path.exists(self.plugin()))
            self.assertFalse(os.path.exists(os.path.join(self.spiel, M.TWSE_EXE)))
        finally:
            game.kill()
            game.wait()

    def test_folder_search_prefers_the_saved_folder(self):
        self.assertEqual(M.spielordner_finden(self.spiel), os.path.normpath(self.spiel))
        leer = tempfile.mkdtemp(dir=self.tmp)
        self.assertNotEqual(M.spielordner_finden(leer), os.path.normpath(leer))


class PoisonValues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='twext_poison_')
        self.ini = os.path.join(self.tmp, M.INI_NAME)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip(self):
        M.ini_schreiben(self.ini, dict(M.STANDARD, poison_percent=250, poison_interval=12))
        w, da = M.ini_lesen(self.ini)
        self.assertTrue(da)
        self.assertEqual((w['poison_percent'], w['poison_interval']), (250, 12))
        self.assertIn('[PoisonDamage]', open(self.ini, encoding='utf-8').read())

    def test_limits(self):
        M.ini_schreiben(self.ini, dict(M.STANDARD, poison_percent=5000, poison_interval=0))
        w, _ = M.ini_lesen(self.ini)
        self.assertEqual((w['poison_percent'], w['poison_interval']), (1000, 1))
        M.ini_schreiben(self.ini, dict(M.STANDARD, poison_percent=-5, poison_interval=500))
        w, _ = M.ini_lesen(self.ini)
        self.assertEqual((w['poison_percent'], w['poison_interval']), (0, 127))

    def test_defaults_are_the_original(self):
        w, _ = M.ini_lesen(self.ini)
        self.assertEqual((w['poison_percent'], w['poison_interval']), (100, 31))


class EnglishTable(unittest.TestCase):
    def test_every_tr_literal_has_an_english_text(self):
        src = open(os.path.join(ROOT, 'tw1_extended_settings.py'), encoding='utf-8').read()
        fehlt = []
        for m in re.finditer(r"\btr\(('(?:[^'\\\n]|\\.)*')\)", src):
            text = ast.literal_eval(m.group(1))
            if text not in M.TEXTE_EN:
                fehlt.append(text)
        self.assertEqual(fehlt, [])


if __name__ == '__main__':
    unittest.main()
