"""Autostart (1.3.0): arguments from the plugin, the [Autostart] section written
by the tool and read by the plugin's C reader, single instance, and the window
started "from the game": minimized, no tour, closes when the game process ends.
Settings live in a temp folder, nothing is sent, the window is never topmost.

    py -3.13 -m unittest tests.test_autostart      (from the repo root)
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402
import foxfeedback  # noqa: E402
import foxfeedback_ui  # noqa: E402
import tw1_extended_settings as M  # noqa: E402

TCC = os.path.join(os.path.expanduser('~'), 'Desktop', 'TwStuff', 'tcc', 'tcc.exe')

C_READER = r'''
#define TWEXT_TEST 1
#include "tw_extended.c"
#undef printf
int main(){
	strcpy(g_gameDir, ".\\");
	defaults(&cfg);
	if(!readIni(&cfg)) return 2;
	char cmd[3 * MAX_PATH];
	buildToolCommand(cmd, sizeof cmd, &cfg, 99);
	fprintf(stdout, "%d|%d|%s|%s|%d|%s\n", cfg.autoStart, cfg.autoMinimized, cfg.toolPath, cfg.toolArgs, cfg.fallPercent, cmd);
	return 0;
}
'''


class Arguments(unittest.TestCase):
    def test_from_game(self):
        self.assertEqual(M.argumente(['--from-game', '1234', '--minimized']), (1234, True))
        self.assertEqual(M.argumente([]), (None, False))
        self.assertEqual(M.argumente(['--from-game', 'x']), (None, False))
        self.assertEqual(M.argumente(['--minimized']), (None, True))


class IniRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='twext_auto_')
        self.ini = os.path.join(self.tmp, M.INI_NAME)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def werte(self, **kw):
        w = dict(M.STANDARD)
        w.update(kw)
        return w

    def test_python_reads_back(self):
        M.ini_schreiben(self.ini, self.werte(auto_start=1, auto_min=0, auto_close=0, fall_percent=55))
        w, da = M.ini_lesen(self.ini)
        self.assertTrue(da)
        self.assertEqual((w['auto_start'], w['auto_min'], w['auto_close'], w['fall_percent']), (1, 0, 0, 55))
        text = open(self.ini, encoding='utf-8').read()
        prog, args = M.tool_befehl()
        self.assertIn(f'ToolPath={prog}\n', text, 'the path line carries no comment')
        self.assertTrue(os.path.isfile(prog))

    def test_defaults_are_off_minimized_close(self):
        w, _ = M.ini_lesen(self.ini)                 # no file yet
        self.assertEqual((w['auto_start'], w['auto_min'], w['auto_close']), (0, 1, 1))

    @unittest.skipUnless(os.path.isfile(TCC), 'tcc not on this PC')
    def test_plugin_reads_what_the_tool_writes(self):
        M.ini_schreiben(self.ini, self.werte(auto_start=1, auto_min=1, fall_percent=77))
        src = os.path.join(self.tmp, 'reader.c')
        with open(src, 'w') as f:
            f.write(C_READER)
        exe = os.path.join(self.tmp, 'reader.exe')
        r = subprocess.run([TCC, '-I' + os.path.join(ROOT, 'twse'), '-I' + ROOT, '-o', exe, src],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        out = subprocess.run([exe], cwd=self.tmp, capture_output=True, text=True).stdout.strip()
        start, mini, path, args, fall, cmd = out.split('|')
        prog, targs = M.tool_befehl()
        self.assertEqual((start, mini, fall), ('1', '1', '77'))
        self.assertEqual(path, prog)
        self.assertEqual(args, targs)
        self.assertTrue(cmd.endswith('--from-game 99 --minimized'), cmd)


class SingleInstance(unittest.TestCase):
    def test_second_start_is_refused(self):
        first = M.einzige_instanz()
        self.assertIsNotNone(first)
        # a second process sees the lock
        r = subprocess.run([sys.executable, '-c',
                            'import sys; sys.path.insert(0, r"%s"); import tw1_extended_settings as M; '
                            'print(M.einzige_instanz() is None)' % ROOT], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), 'True', r.stderr)


class FromGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='twext_game_')
        cls._orig = (M.KONFIG_DATEI, M.DATEN, foxfeedback.submit, foxfeedback_ui.FeedbackUI.start)
        M.DATEN = cls.tmp
        M.KONFIG_DATEI = os.path.join(cls.tmp, 'konfig.json')
        foxfeedback.submit = lambda *a, **k: (_ for _ in ()).throw(AssertionError('nothing is sent'))
        cls.fb_starts = []
        foxfeedback_ui.FeedbackUI.start = lambda self: cls.fb_starts.append(1)
        cls.spiel = os.path.join(cls.tmp, 'game')
        os.makedirs(cls.spiel)
        M.ini_schreiben(os.path.join(cls.spiel, M.INI_NAME), dict(M.STANDARD, auto_start=1))

    @classmethod
    def tearDownClass(cls):
        M.KONFIG_DATEI, M.DATEN, foxfeedback.submit, foxfeedback_ui.FeedbackUI.start = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_minimized_then_closes_with_the_game(self):
        game = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'])
        konfig = M.Konfig()
        konfig.update(game_dir=self.spiel, lang='en')
        M.SPRACHE = 'en'
        app = M.App(konfig, spiel_pid=game.pid, minimiert=True)
        closed = []
        real = app.destroy
        app.destroy = lambda: (closed.append(1), real())
        end = time.time() + 1.5
        while time.time() < end:
            app.update()
            time.sleep(0.02)
        self.assertEqual(app.state(), 'iconic', 'started minimized')
        self.assertIsNone(app.guide, 'no tour when started from the game')
        self.assertEqual(self.fb_starts, [], 'the test window waits until the window is opened')
        self.assertEqual(app.vars['auto_start'].get(), 1)
        game.wait()
        end = time.time() + 6
        while not closed and time.time() < end:
            try:
                app.update()
            except tk.TclError:
                break
            time.sleep(0.05)
        self.assertTrue(closed, 'the tool closed when the game ended')


if __name__ == '__main__':
    unittest.main()
