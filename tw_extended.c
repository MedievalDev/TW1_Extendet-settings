/* TWExtended - Two Worlds 1 (1.7) TWSE-Plugin: Schadensarten einstellbar.
 *
 * Liest tw1_Extendet-settings.ini neben der Spiel-EXE (beim Start und bei
 * jeder Aenderung der Datei, gepollt im Frame-Hook) und wendet die Werte
 * sofort an. Das UI-Tool "tw1_Extendet-settings" schreibt diese Datei.
 *
 * Eingriffe (alle Adressen aus TwoWorlds.exe 1.7, gemessen 13.09.2026):
 *
 *  Fallschaden: Der PhysX-Charakter-Controller des Helden (Objekt in
 *    [0xAB42E4], vtable 0x9E3164) hat in Slot +0xAC die Landungsroutine
 *    0x754370. Sie rechnet aus dem Sturzwert [this+0xC4] * 0.1 eine Hoehe,
 *    unter 8.0 nichts, ueber 25.0 sofort tot, dazwischen
 *    Prozent = (Hoehe - 8) * 0.0588 * 100 vom Max-HP. Der Prozentwert geht
 *    ueber SetFallPercent (vtable +0x40) in die Positionsnachricht und wird
 *    im Empfaenger (0x585A40, identisch mit dem Konsolenbefehl hitfall) als
 *    MaxHP * Prozent / 100 abgezogen. Wir tauschen den vtable-Slot gegen
 *    eine eigene Fassung mit einstellbaren Werten.
 *
 *  Rutschschaden: 0x7556D0 (alle 5 Ticks): rutscht der Held laenger als
 *    30 Zaehler (cmp [esi+0x128], 0x1E bei 0x755770) einen steilen Hang,
 *    kommt SetFallPercent(10) (push 0xA bei 0x75577E). Beide Immediates
 *    werden direkt gepatcht.
 *
 *  Pferd: Das zuletzt gerittene Pferd (EC_GetHorse bzw. [Hero+0x62C]) wird
 *    auf Wunsch unsterblich: sein vtable-Slot +0x138 (SubHP) laesst den
 *    Schaden fallen, zusaetzlich werden die HP jeden Frame aufgefuellt.
 *    Pfeifreichweite: Tick 0x681760 (Ruf-Animation), bei 0x68188A
 *    "cmp eax, 0xA00" (40 m, 64 Einheiten je Meter) - Immediate patchbar,
 *    siehe QuestForge\HANDOFF_PFERD.md. 0 = Exe so lassen wie sie ist.
 *
 *  Lava: Das Schwimm-Update des Controllers (0x7563E0) geht die
 *    Fluessigkeiten durch; steht der Held in einer mit Lava-Flag
 *    ([liquid+0x4C] != 0), ruft es jeden Frame SetFallPercent(5)
 *    (push 5 bei 0x75650F, call [vt+0x40] bei 0x756513). Gefunden ueber die
 *    Diagnose: Aufrufer 0x585AF9 = HitFall. Der 6-Byte-Block wird durch einen
 *    Sprung in einen kleinen Thunk ersetzt, der Prozent und Takt aus der
 *    Konfiguration nimmt.
 *
 *  Diagnose: Die vtable-Slots +0x138 (SubHP) und +0xCC (Kill) des Helden
 *    werden auf Wunsch umgeleitet und jeder HP-Verlust mit Ruecksprungadresse
 *    protokolliert.
 *
 *  Autostart: Steht [Autostart] Enabled=1 in der ini, startet das Plugin
 *    beim Spielstart das Einstellungs-Tool (ToolPath/ToolArgs traegt das Tool
 *    selbst ein) mit --from-game <PID> und auf Wunsch --minimized. Laeuft das
 *    Tool schon (Mutex Local\TW1ExtendedSettings), passiert nichts.
 *
 * Build: tcc -shared -o TWExtended.dll tw_extended.c   (siehe build_extended.bat)
 */
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>
#include "twse_plugin.h"   /* Include-Verzeichnis twse\ oder ..\twse\ aus dem Build-Skript */

#define PLUG_NAME     "TWExtended"
#define INI_NAME      "tw1_Extendet-settings.ini"
#define LOG_NAME      "TWExtended.log"
#define STATUS_NAME   "TWExtended.status"

static TWSE_INFO* info;

/* --------------------------------------------------------- */
/* Pfade und Ausgabe                                         */
/* --------------------------------------------------------- */

static char g_gameDir[MAX_PATH];   /* Ordner der Spiel-EXE mit Backslash am Ende */
static FILE *g_logFile = 0;

static void initGameDir(void){
	DWORD n = GetModuleFileNameA(NULL, g_gameDir, MAX_PATH);
	int cut = -1;
	for(DWORD i = 0; i < n; i++) if(g_gameDir[i] == '\\') cut = (int)i;
	if(cut >= 0) g_gameDir[cut + 1] = 0; else g_gameDir[0] = 0;
}

static void pathOf(char *out, const char *name){
	strcpy(out, g_gameDir);
	strcat(out, name);
}

static void twlog(const char *fmt, ...){
	va_list ap;
	va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
	if(g_logFile == 0){
		char p[MAX_PATH]; pathOf(p, LOG_NAME);
		g_logFile = fopen(p, "a");
		if(g_logFile) fprintf(g_logFile, "\n=== %s Log ===\n", PLUG_NAME);
	}
	if(g_logFile){
		va_start(ap, fmt); vfprintf(g_logFile, fmt, ap); va_end(ap);
		fflush(g_logFile);
	}
}
#define printf twlog

/* --------------------------------------------------------- */
/* Einstellungen                                             */
/* --------------------------------------------------------- */

typedef struct {
	int   fallEnabled;     /* 0 = kein Fallschaden, kein Sturztod, keine Benommenheit */
	int   fallPercent;     /* Skalierung des Schadens, 100 = Original */
	float fallMinHeight;   /* ab dieser Hoehe gibt es Schaden (Original 8.0) */
	float fallDeathHeight; /* ab dieser Hoehe sofort tot (Original 25.0), 0 = nie */
	int   fallLethal;      /* 1 = Original: reicht der Schaden zum Toeten, sofort tot */
	int   slideEnabled;    /* Rutschschaden an Haengen */
	int   slidePercent;    /* Prozent vom Max-HP je Schadenstick (Original 10) */
	int   slideGrace;      /* Zaehler bis zum ersten Schaden (Original 30) */
	int   lavaEnabled;     /* Lavaschaden */
	int   lavaPercent;     /* Prozent vom Max-HP je Schadenstick (Original 5) */
	int   lavaEvery;       /* Schaden alle n Frames (Original 1) */
	int   horseImmortal;   /* Pferd des Helden nimmt keinen Schaden */
	int   whistleMeters;   /* Pfeifreichweite in Metern, 0 = Exe unveraendert (Original 40) */
	int   logDamage;       /* Diagnose: jeden HP-Verlust des Helden loggen */
	int   autoStart;       /* Einstellungs-Tool beim Spielstart oeffnen */
	int   autoMinimized;   /* ... minimiert, das Spiel behaelt den Fokus */
	char  toolPath[MAX_PATH];  /* Exe des Tools (oder pythonw.exe) */
	char  toolArgs[MAX_PATH];  /* Zusatzargumente, im Skriptmodus der Skriptpfad */
} Settings;

static Settings cfg;
static FILETIME g_iniTime;
static int g_iniSeen = 0;
static int g_autoResult = 0;   /* 0 aus, 1 gestartet, 2 lief schon, -1 Fehler */

static void defaults(Settings *s){
	s->fallEnabled = 1; s->fallPercent = 100; s->fallMinHeight = 8.0f;
	s->fallDeathHeight = 25.0f; s->fallLethal = 1;
	s->slideEnabled = 1; s->slidePercent = 10; s->slideGrace = 30;
	s->lavaEnabled = 1; s->lavaPercent = 5; s->lavaEvery = 1;
	s->horseImmortal = 0; s->whistleMeters = 0;
	s->logDamage = 0;
	s->autoStart = 0; s->autoMinimized = 1;
	s->toolPath[0] = 0; s->toolArgs[0] = 0;
}

static int clampi(int v, int lo, int hi){ return v < lo ? lo : (v > hi ? hi : v); }

static void trim(char *s){
	char *p = s; while(*p == ' ' || *p == '\t') p++;
	if(p != s) memmove(s, p, strlen(p) + 1);
	int n = (int)strlen(s);
	while(n > 0 && (s[n-1] == ' ' || s[n-1] == '\t' || s[n-1] == '\r' || s[n-1] == '\n')) s[--n] = 0;
}

/* Pfade duerfen ; und # enthalten: ToolPath/ToolArgs lesen den Rest der Zeile
 * ohne Kommentar. Gibt 1 zurueck, wenn die Zeile so ein Schluessel war. */
static int rawPathKey(const char *sect, char *line, Settings *s){
	char *eq = strchr(line, '=');
	if(!eq || stricmp(sect, "Autostart") != 0) return 0;
	char key[32]; int n = (int)(eq - line);
	if(n <= 0 || n >= (int)sizeof key) return 0;
	memcpy(key, line, n); key[n] = 0; trim(key);
	char *dst = stricmp(key, "ToolPath") == 0 ? s->toolPath : stricmp(key, "ToolArgs") == 0 ? s->toolArgs : 0;
	if(!dst) return 0;
	strncpy(dst, eq + 1, MAX_PATH - 1); dst[MAX_PATH - 1] = 0; trim(dst);
	return 1;
}

/* Sehr kleiner INI-Leser: [Sektion] und Schluessel=Wert, ; oder # als Kommentar. */
static int readIni(Settings *s){
	char p[MAX_PATH]; pathOf(p, INI_NAME);
	FILE *f = fopen(p, "r");
	if(!f) return 0;
	char line[1024], sect[64] = "";
	while(fgets(line, sizeof line, f)){
		if(rawPathKey(sect, line, s)) continue;
		char *c = strchr(line, ';'); if(c) *c = 0;
		c = strchr(line, '#'); if(c) *c = 0;
		trim(line);
		if(!line[0]) continue;
		if(line[0] == '['){
			char *e = strchr(line, ']'); if(e) *e = 0;
			strncpy(sect, line + 1, sizeof sect - 1); sect[sizeof sect - 1] = 0;
			continue;
		}
		char *eq = strchr(line, '='); if(!eq) continue;
		*eq = 0; char *key = line, *val = eq + 1; trim(key); trim(val);
		int   iv = atoi(val); float fv = (float)atof(val);
		if(stricmp(sect, "FallDamage") == 0){
			if(stricmp(key, "Enabled") == 0)          s->fallEnabled = iv != 0;
			else if(stricmp(key, "Percent") == 0)     s->fallPercent = clampi(iv, 0, 1000);
			else if(stricmp(key, "MinHeight") == 0)   s->fallMinHeight = fv < 0 ? 0 : fv;
			else if(stricmp(key, "DeathHeight") == 0) s->fallDeathHeight = fv < 0 ? 0 : fv;
			else if(stricmp(key, "Lethal") == 0)      s->fallLethal = iv != 0;
		}else if(stricmp(sect, "SlideDamage") == 0){
			if(stricmp(key, "Enabled") == 0)          s->slideEnabled = iv != 0;
			else if(stricmp(key, "Percent") == 0)     s->slidePercent = clampi(iv, 0, 100);
			else if(stricmp(key, "GraceTicks") == 0)  s->slideGrace = clampi(iv, 0, 127);
		}else if(stricmp(sect, "LavaDamage") == 0){
			if(stricmp(key, "Enabled") == 0)          s->lavaEnabled = iv != 0;
			else if(stricmp(key, "Percent") == 0)     s->lavaPercent = clampi(iv, 0, 100);
			else if(stricmp(key, "EveryFrames") == 0) s->lavaEvery = clampi(iv, 1, 600);
		}else if(stricmp(sect, "Horse") == 0){
			if(stricmp(key, "Immortal") == 0)                s->horseImmortal = iv != 0;
			else if(stricmp(key, "WhistleRangeMeters") == 0) s->whistleMeters = clampi(iv, 0, 20000);
		}else if(stricmp(sect, "Diagnose") == 0){
			if(stricmp(key, "LogDamage") == 0)        s->logDamage = iv != 0;
		}else if(stricmp(sect, "Autostart") == 0){
			if(stricmp(key, "Enabled") == 0)          s->autoStart = iv != 0;
			else if(stricmp(key, "Minimized") == 0)   s->autoMinimized = iv != 0;
		}
	}
	fclose(f);
	return 1;
}

static void writeDefaultIni(void){
	char p[MAX_PATH]; pathOf(p, INI_NAME);
	FILE *f = fopen(p, "w");
	if(!f) return;
	fprintf(f,
		"; tw1_Extendet-settings - written by TWExtended (Two Worlds 1.7)\n"
		"; Changes are picked up by the running game within a second.\n"
		"\n[FallDamage]\n"
		"Enabled=1        ; 0 = no fall damage, no fall death, no stun\n"
		"Percent=100      ; damage scale, 100 = original, 0 = no damage\n"
		"MinHeight=8.0    ; damage starts above this height (original 8.0)\n"
		"DeathHeight=25.0 ; instant death above this height (original 25.0), 0 = never\n"
		"Lethal=1         ; 1 = original: instant death when the damage would kill you\n"
		"\n[SlideDamage]\n"
		"Enabled=1        ; damage while sliding down steep slopes\n"
		"Percent=10       ; percent of max HP per damage tick (original 10)\n"
		"GraceTicks=30    ; ticks of sliding before damage starts (original 30)\n"
		"\n[LavaDamage]\n"
		"Enabled=1        ; damage while swimming in lava\n"
		"Percent=5        ; percent of max HP per damage tick (original 5)\n"
		"EveryFrames=1    ; a damage tick every n frames (original 1 = every frame)\n"
		"\n[Horse]\n"
		"Immortal=0       ; 1 = the hero's horse takes no damage\n"
		"WhistleRangeMeters=0 ; distance the horse answers the whistle from (original 40), 0 = leave the exe as it is\n"
		"\n[Diagnose]\n"
		"LogDamage=0      ; 1 = log every HP loss of the hero to TWExtended.log\n"
		"\n[Autostart]\n"
		"Enabled=0        ; 1 = open the settings tool when the game starts (the tool fills in ToolPath)\n"
		"Minimized=1      ; 1 = open it minimized, the game keeps the focus\n"
		"CloseWithGame=1  ; 1 = the tool closes when the game ends\n");
	fclose(f);
}

static int iniChanged(void){
	char p[MAX_PATH]; pathOf(p, INI_NAME);
	WIN32_FILE_ATTRIBUTE_DATA fa;
	if(!GetFileAttributesExA(p, GetFileExInfoStandard, &fa)) return 0;
	if(g_iniSeen && CompareFileTime(&fa.ftLastWriteTime, &g_iniTime) == 0) return 0;
	g_iniTime = fa.ftLastWriteTime; g_iniSeen = 1;
	return 1;
}

/* --------------------------------------------------------- */
/* Speicher schreiben                                        */
/* --------------------------------------------------------- */

static int writeMem(void *dst, const void *src, size_t n){
	DWORD old;
	if(!VirtualProtect(dst, n, PAGE_EXECUTE_READWRITE, &old)) return 0;
	memcpy(dst, src, n);
	VirtualProtect(dst, n, old, &old);
	FlushInstructionCache(GetCurrentProcess(), dst, n);
	return 1;
}

/* --------------------------------------------------------- */
/* Fallschaden: Landungsroutine des Helden-Controllers       */
/* --------------------------------------------------------- */

#define CTRL_VTABLE     0x009E3164
#define VT_LANDING      0xAC      /* 0x754370 */
#define VT_SETKILL      0x38      /* SetKill(int) -> Flag 0x200: sofort tot */
#define VT_SETFALL      0x40      /* SetFallPercent(int) -> Flag 0x400 */
#define ADDR_LANDING    0x00754370

/* Konstanten der Original-Routine (Datenbereich der EXE). Im Testbau
 * (-DTWEXT_TEST) sind es normale Variablen. */
#ifndef TWEXT_TEST
#define K_SCALE   (*(float *)0x00A5977C)   /* 0.1  : Sturzwert -> Hoehe        */
#define K_MIN     (*(float *)0x00A59804)   /* 8.0  : ab hier Schaden           */
#define K_DEATH   (*(float *)0x00A37354)   /* 25.0 : ab hier sofort tot        */
#define K_SLOPE   (*(float *)0x009EF84C)   /* 0.0588 = 1/17 je Hoeheneinheit   */
#define K_HUNDRED (*(float *)0x00A749D0)   /* 100.0                            */
#define K_STUN    (*(float *)0x00A36F48)   /* 30.0 : Benommenheits-Ticks       */
#else
static float K_SCALE = 0.1f, K_MIN = 8.0f, K_DEATH = 25.0f, K_SLOPE = 0.05882353f, K_HUNDRED = 100.0f, K_STUN = 30.0f;
#endif

typedef void (__fastcall *FN_CtrlInt)(void *ctrl, void *edxDummy, int v);   /* thiscall(int) */
#define CTRL_I(c, off) (*(int *)((char *)(c) + (off)))
#define CTRL_F(c, off) (*(float *)((char *)(c) + (off)))
#define VCALL_INT(c, slot, v) ((FN_CtrlInt)(*(void ***)(c))[(slot) / 4])((c), 0, (v))

static int g_landingHooked = 0;
static DWORD g_landingOrig = 0;

/* Ersatz fuer 0x754370. thiscall ohne Stack-Argumente = fastcall(this). */
static void __fastcall hookLanding(void *c){
	if(!cfg.fallEnabled) return;
	float h = CTRL_F(c, 0xC4) * K_SCALE;
	if(h <= cfg.fallMinHeight) return;
	if(cfg.fallDeathHeight > 0.0f && h > cfg.fallDeathHeight){
		if(cfg.logDamage) printf("[%s] Sturz aus Hoehe %.1f: ueber Todeshoehe %.1f\n", PLUG_NAME, h, cfg.fallDeathHeight);
		VCALL_INT(c, VT_SETKILL, 1);
		return;
	}
	float x0 = (h - cfg.fallMinHeight) * K_SLOPE;           /* wie Original */
	float x  = x0 * (float)cfg.fallPercent / 100.0f;         /* skaliert    */
	if(cfg.fallLethal && (float)CTRL_I(c, 0x138) * x >= (float)CTRL_I(c, 0x134)){
		if(cfg.logDamage) printf("[%s] Sturz aus Hoehe %.1f: Schaden waere toedlich\n", PLUG_NAME, h);
		VCALL_INT(c, VT_SETKILL, 1);
		return;
	}
	int pct = (int)(x * K_HUNDRED);
	if(cfg.logDamage) printf("[%s] Sturz aus Hoehe %.1f: %d%% (Original %d%%)\n", PLUG_NAME, h, pct, (int)(x0 * K_HUNDRED));
	VCALL_INT(c, VT_SETFALL, pct);
	CTRL_I(c, 0x114) = 1;
	CTRL_I(c, 0xCC)  = (int)(x0 * K_STUN);   /* Benommenheit wie Original */
}

static int installLandingHook(void){
	if(g_landingHooked) return 1;
	DWORD *slot = (DWORD *)(CTRL_VTABLE + VT_LANDING);
	if(*slot != ADDR_LANDING){
		printf("[%s] FEHLER: vtable-Slot Landung zeigt auf %08X statt %08X - andere Spielversion?\n", PLUG_NAME, *slot, ADDR_LANDING);
		return 0;
	}
	g_landingOrig = *slot;
	DWORD nv = (DWORD)(void *)hookLanding;
	if(!writeMem(slot, &nv, 4)){ printf("[%s] FEHLER: vtable nicht beschreibbar\n", PLUG_NAME); return 0; }
	g_landingHooked = 1;
	printf("[%s] Fallschaden-Hook gesetzt (vtable %08X+%02X)\n", PLUG_NAME, CTRL_VTABLE, VT_LANDING);
	return 1;
}

/* --------------------------------------------------------- */
/* Rutschschaden: zwei Immediates                            */
/* --------------------------------------------------------- */

#define ADDR_SLIDE_GRACE 0x00755770   /* 83 BE 28 01 00 00 1E : cmp [esi+0x128], 0x1E */
#define ADDR_SLIDE_PCT   0x0075577E   /* 6A 0A                : push 0xA              */
static const BYTE slideGraceOrig[] = {0x83, 0xBE, 0x28, 0x01, 0x00, 0x00, 0x1E};
static int g_slideOk = -1;   /* -1 ungeprueft, 0 Bytes passen nicht, 1 ok */

static int slideCheck(void){
	if(g_slideOk >= 0) return g_slideOk;
	/* Nur die festen Teile vergleichen, die Immediates koennen schon gepatcht sein */
	g_slideOk = memcmp((void *)ADDR_SLIDE_GRACE, slideGraceOrig, 6) == 0
	         && *(BYTE *)ADDR_SLIDE_PCT == 0x6A;
	if(!g_slideOk) printf("[%s] FEHLER: Rutschschaden-Code sieht anders aus - kein Patch\n", PLUG_NAME);
	return g_slideOk;
}

static void applySlide(void){
	if(!slideCheck()) return;
	BYTE pct   = (BYTE)(cfg.slideEnabled ? cfg.slidePercent : 0);
	BYTE grace = (BYTE)cfg.slideGrace;
	writeMem((void *)(ADDR_SLIDE_GRACE + 6), &grace, 1);
	writeMem((void *)(ADDR_SLIDE_PCT + 1), &pct, 1);
}

/* --------------------------------------------------------- */
/* Einheiten-vtable: SubHP/Kill umleiten (Diagnose, Pferd)   */
/* --------------------------------------------------------- */

#define VT_GETHP    0x130
#define VT_GETMAXHP 0x134
#define VT_SUBHP    0x138
#define VT_SETHP    0x13C
#define VT_KILL     0xCC

typedef int  (__fastcall *FN_UnitGet)(void *u);                                   /* thiscall()            */
typedef int  (__fastcall *FN_UnitSub)(void *u, void *edx, int dmg);               /* thiscall(int)         */
typedef int  (__fastcall *FN_UnitKill)(void *u, void *edx, int a, int b, int c);  /* thiscall(int,int,int) */
typedef void*(__stdcall  *FN_GetHorse)(void *hero);                               /* EC_GetHorse           */

#define UCALL0(u, slot)      ((FN_UnitGet)(*(void ***)(u))[(slot) / 4])(u)
#define UCALL1(u, slot, v)   ((FN_UnitSub)(*(void ***)(u))[(slot) / 4])((u), 0, (v))

/* Eine Klasse = eine vtable. Held und Pferd haben verschiedene. */
typedef struct { void **vt; FN_UnitSub origSub; FN_UnitKill origKill; const char *name; } VtHook;
static VtHook g_hooks[4];
static int g_hookCount = 0;

static void *activeHero(void){
	return (void *)info->TWFuncs->getActiveHero();
}

static FN_GetHorse fn_GetHorse = 0;

/* Zuletzt gerittenes Pferd des Helden, 0 wenn keins oder nicht geladen.
 * EC_GetHorse liefert ohne Pferd den Helden selbst zurueck (Trainer-Fund). */
static void *currentHorse(void){
	void *hero = activeHero();
	if(!hero) return 0;
	if(!fn_GetHorse && info->EarthCApi && info->EarthCApi->functionsAvailable && info->EarthCApi->functions)
		fn_GetHorse = (FN_GetHorse)info->EarthCApi->functions->CUnitBase__EC_GetHorse;
	void *horse = fn_GetHorse ? fn_GetHorse(hero) : *(void **)((char *)hero + 0x62C);
	if(!horse || horse == hero) return 0;
	if(!(*(unsigned char *)((char *)horse + 0x1C) & 0x10)) return 0;   /* nicht geladen */
	return horse;
}

static VtHook *hookFor(void *u){
	void **vt = *(void ***)u;
	for(int i = 0; i < g_hookCount; i++) if(g_hooks[i].vt == vt) return &g_hooks[i];
	return 0;
}

static int __fastcall hookSubHP(void *u, void *edx, int dmg){
	void *ret; __asm__ volatile("mov 4(%%ebp), %0" : "=r"(ret));
	VtHook *h = hookFor(u);
	if(!h) return 0;
	if(cfg.horseImmortal && u == currentHorse()){
		if(cfg.logDamage) printf("[%s] Pferd: SubHP(%d) verworfen, Aufrufer %p\n", PLUG_NAME, dmg, ret);
		return 0;
	}
	if(cfg.logDamage && u == activeHero())
		printf("[%s] SubHP(%d) HP vorher %d, Aufrufer %p\n", PLUG_NAME, dmg, UCALL0(u, VT_GETHP), ret);
	return h->origSub(u, 0, dmg);
}

static int __fastcall hookKill(void *u, void *edx, int a, int b, int c){
	void *ret; __asm__ volatile("mov 4(%%ebp), %0" : "=r"(ret));
	VtHook *h = hookFor(u);
	if(!h) return 0;
	if(cfg.logDamage && (u == activeHero() || u == currentHorse()))
		printf("[%s] %s: Kill(%d,%d,%d) Aufrufer %p\n", PLUG_NAME, u == activeHero() ? "Held" : "Pferd", a, b, c, ret);
	return h->origKill(u, 0, a, b, c);
}

static void hookVtableOf(void *u, const char *name){
	if(!u || hookFor(u) || g_hookCount >= 4) return;
	void **vt = *(void ***)u;
	VtHook *h = &g_hooks[g_hookCount];
	h->vt = vt; h->name = name;
	h->origSub  = (FN_UnitSub)vt[VT_SUBHP / 4];
	h->origKill = (FN_UnitKill)vt[VT_KILL / 4];
	void *nSub = (void *)hookSubHP, *nKill = (void *)hookKill;
	if(!writeMem(&vt[VT_SUBHP / 4], &nSub, 4) || !writeMem(&vt[VT_KILL / 4], &nKill, 4)){
		printf("[%s] Hook %s: vtable nicht beschreibbar\n", PLUG_NAME, name);
		return;
	}
	g_hookCount++;
	printf("[%s] Hook %s gesetzt (vtable %p, SubHP %p, Kill %p)\n", PLUG_NAME, name, vt, h->origSub, h->origKill);
}

/* Jeden Frame: Held loggen (Diagnose), Pferd unsterblich halten. */
static void unitsTick(void){
	if(cfg.logDamage) hookVtableOf(activeHero(), "Held");
	if(cfg.horseImmortal){
		void *horse = currentHorse();
		if(horse){
			hookVtableOf(horse, "Pferd");
			int hp = UCALL0(horse, VT_GETHP), mx = UCALL0(horse, VT_GETMAXHP);
			if(hp < mx && mx > 0) UCALL1(horse, VT_SETHP, mx);
		}
	}
}

/* --------------------------------------------------------- */
/* Lava: Thunk statt "push 5; mov ecx,esi; call eax"          */
/* --------------------------------------------------------- */

#define ADDR_LAVA_CALL 0x0075650F   /* 6A 05 8B CE FF D0 */
static const BYTE lavaOrig[] = {0x6A, 0x05, 0x8B, 0xCE, 0xFF, 0xD0};
static int g_lavaOk = -1;
static int g_lavaFrame = 0;

/* Wird aus dem Thunk mit dem Controller als Argument gerufen (cdecl).
 * Nur Ganzzahlen: die Aufrufstelle hat x87-Werte auf dem Stapel. */
static void __cdecl lavaTick(void *ctrl){
	g_lavaFrame++;
	if(!cfg.lavaEnabled || cfg.lavaPercent <= 0) return;
	if(cfg.lavaEvery > 1 && (g_lavaFrame % cfg.lavaEvery) != 0) return;
	VCALL_INT(ctrl, VT_SETFALL, cfg.lavaPercent);
}

static int installLavaHook(void){
	if(g_lavaOk >= 0) return g_lavaOk;
	if(memcmp((void *)ADDR_LAVA_CALL, lavaOrig, 6) != 0){
		g_lavaOk = 0;
		printf("[%s] FEHLER: Lava-Aufruf sieht anders aus - kein Patch\n", PLUG_NAME);
		return 0;
	}
	/* Thunk: pushad; push esi; call lavaTick; add esp,4; popad; ret */
	BYTE *t = (BYTE *)VirtualAlloc(0, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
	if(!t){ g_lavaOk = 0; return 0; }
	int n = 0;
	t[n++] = 0x60; t[n++] = 0x56; t[n++] = 0xE8;
	*(DWORD *)(t + n) = (DWORD)(void *)lavaTick - (DWORD)(t + n + 4); n += 4;
	t[n++] = 0x83; t[n++] = 0xC4; t[n++] = 0x04; t[n++] = 0x61; t[n++] = 0xC3;
	BYTE jmp[6] = {0xE8, 0, 0, 0, 0, 0x90};
	*(DWORD *)(jmp + 1) = (DWORD)t - (ADDR_LAVA_CALL + 5);
	if(!writeMem((void *)ADDR_LAVA_CALL, jmp, 6)){ g_lavaOk = 0; return 0; }
	g_lavaOk = 1;
	printf("[%s] Lava-Hook gesetzt (Thunk %p)\n", PLUG_NAME, t);
	return 1;
}

/* --------------------------------------------------------- */
/* Pfeifreichweite: Immediate im Ruf-Tick                    */
/* --------------------------------------------------------- */

#define ADDR_WHISTLE_CMP 0x0068188A   /* 3D 00 0A 00 00 : cmp eax, 0xA00 ; dann 0F 8D A9 00 00 00 (jge) */
static const BYTE whistleJge[] = {0x0F, 0x8D, 0xA9, 0x00, 0x00, 0x00};
static DWORD g_whistleFirst = 0;      /* Wert beim ersten Blick (Exe-Stand, evtl. schon gepatcht) */
static int g_whistleOk = -1;

static int whistleCheck(void){
	if(g_whistleOk >= 0) return g_whistleOk;
	g_whistleOk = *(BYTE *)ADDR_WHISTLE_CMP == 0x3D && memcmp((void *)(ADDR_WHISTLE_CMP + 5), whistleJge, 6) == 0;
	if(g_whistleOk) g_whistleFirst = *(DWORD *)(ADDR_WHISTLE_CMP + 1);
	else printf("[%s] FEHLER: Pfeif-Vergleich sieht anders aus - kein Patch\n", PLUG_NAME);
	return g_whistleOk;
}

static void applyWhistle(void){
	if(!whistleCheck()) return;
	DWORD want = cfg.whistleMeters > 0 ? (DWORD)cfg.whistleMeters * 64u : g_whistleFirst;
	if(*(DWORD *)(ADDR_WHISTLE_CMP + 1) != want) writeMem((void *)(ADDR_WHISTLE_CMP + 1), &want, 4);
}

static int whistleMetersNow(void){
	return whistleCheck() ? (int)(*(DWORD *)(ADDR_WHISTLE_CMP + 1) / 64u) : -1;
}

/* --------------------------------------------------------- */
/* Anwenden, Status, Konsole                                 */
/* --------------------------------------------------------- */

static void writeStatus(void){
	char p[MAX_PATH]; pathOf(p, STATUS_NAME);
	FILE *f = fopen(p, "w");
	if(!f) return;
	SYSTEMTIME t; GetLocalTime(&t);
	fprintf(f, "plugin=%s\ntime=%04d-%02d-%02d %02d:%02d:%02d\n", PLUG_NAME, t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond);
	fprintf(f, "fall_hook=%d\nslide_patch=%d\nlava_hook=%d\nwhistle_patch=%d\nhooks=%d\nwhistle_now=%d\n",
		g_landingHooked, g_slideOk == 1, g_lavaOk == 1, g_whistleOk == 1, g_hookCount, whistleMetersNow());
	fprintf(f, "fall=%d,%d,%.2f,%.2f,%d\nslide=%d,%d,%d\nlava=%d,%d,%d\nhorse=%d,%d\nlog=%d\n",
		cfg.fallEnabled, cfg.fallPercent, cfg.fallMinHeight, cfg.fallDeathHeight, cfg.fallLethal,
		cfg.slideEnabled, cfg.slidePercent, cfg.slideGrace, cfg.lavaEnabled, cfg.lavaPercent, cfg.lavaEvery,
		cfg.horseImmortal, cfg.whistleMeters, cfg.logDamage);
	fprintf(f, "autostart=%d,%d,%d\n", cfg.autoStart, cfg.autoMinimized, g_autoResult);
	fclose(f);
}

static void applySettings(const char *why){
	installLandingHook();
	applySlide();
	installLavaHook();
	applyWhistle();
	unitsTick();
	printf("[%s] Einstellungen (%s): Fall %s %d%% min %.1f tot %.1f lethal %d | Rutschen %s %d%% ab %d | Lava %s %d%% alle %d | Pferd unsterblich %d, Pfeife %d m (aktiv %d m) | Log %d\n",
		PLUG_NAME, why, cfg.fallEnabled ? "an" : "AUS", cfg.fallPercent, cfg.fallMinHeight, cfg.fallDeathHeight, cfg.fallLethal,
		cfg.slideEnabled ? "an" : "AUS", cfg.slidePercent, cfg.slideGrace,
		cfg.lavaEnabled ? "an" : "AUS", cfg.lavaPercent, cfg.lavaEvery,
		cfg.horseImmortal, cfg.whistleMeters, whistleMetersNow(), cfg.logDamage);
	writeStatus();
}

static void loadAndApply(const char *why){
	defaults(&cfg);
	if(!readIni(&cfg)){
		writeDefaultIni();
		printf("[%s] %s angelegt (Standardwerte)\n", PLUG_NAME, INI_NAME);
	}
	iniChanged();
	applySettings(why);
}

/* --------------------------------------------------------- */
/* Autostart: das Einstellungs-Tool mit dem Spiel oeffnen     */
/* --------------------------------------------------------- */

#define TOOL_MUTEX "Local\\TW1ExtendedSettings"   /* legt das Tool an, solange es laeuft */

static int toolRunning(void){
	HANDLE m = OpenMutexA(SYNCHRONIZE, FALSE, TOOL_MUTEX);
	if(!m) return 0;
	CloseHandle(m);
	return 1;
}

/* Baut die Befehlszeile. Das Tool bekommt die PID des Spiels, damit es sich mit
 * ihm schliessen kann, und --minimized, damit es dem Spiel den Fokus laesst. */
static int buildToolCommand(char *out, int size, const Settings *s, DWORD pid){
	int n = _snprintf(out, size, "\"%s\"%s%s --from-game %lu%s", s->toolPath,
		s->toolArgs[0] ? " " : "", s->toolArgs, (unsigned long)pid, s->autoMinimized ? " --minimized" : "");
	if(n < 0 || n >= size){ out[size - 1] = 0; return 0; }
	return 1;
}

/* Die ini schreibt das Tool als UTF-8: Pfade mit Umlauten gehen nur ueber die
 * Wide-API richtig durch. */
#ifndef CP_UTF8
#define CP_UTF8 65001   /* fehlt in den Headern von tcc */
WINBASEAPI int WINAPI MultiByteToWideChar(UINT cp, DWORD flags, LPCSTR src, int n, LPWSTR dst, int size);
#endif
static int utf8ToWide(const char *in, wchar_t *out, int size){
	int n = MultiByteToWideChar(CP_UTF8, 0, in, -1, out, size);
	if(n <= 0){ out[0] = 0; return 0; }
	return 1;
}

static void autostartTool(void){
	if(!cfg.autoStart){ g_autoResult = 0; return; }
	if(toolRunning()){
		g_autoResult = 2;
		printf("[%s] Autostart: Einstellungs-Tool laeuft schon
", PLUG_NAME);
		return;
	}
	wchar_t wpath[MAX_PATH];
	if(!cfg.toolPath[0] || !utf8ToWide(cfg.toolPath, wpath, MAX_PATH)
	   || GetFileAttributesW(wpath) == INVALID_FILE_ATTRIBUTES){
		g_autoResult = -1;
		printf("[%s] Autostart: Tool nicht gefunden (%s) - das Tool einmal oeffnen, es traegt seinen Pfad selbst ein
",
			PLUG_NAME, cfg.toolPath[0] ? cfg.toolPath : "ToolPath fehlt");
		return;
	}
	char cmd[3 * MAX_PATH];
	wchar_t wcmd[3 * MAX_PATH], wdir[MAX_PATH];
	if(!buildToolCommand(cmd, sizeof cmd, &cfg, GetCurrentProcessId()) || !utf8ToWide(cmd, wcmd, 3 * MAX_PATH)){
		g_autoResult = -1;
		printf("[%s] Autostart: Befehlszeile zu lang
", PLUG_NAME);
		return;
	}
	wcscpy(wdir, wpath);
	wchar_t *cut = wcsrchr(wdir, L'\\'); if(cut) *cut = 0; else wdir[0] = 0;
	STARTUPINFOW si; PROCESS_INFORMATION pi;
	memset(&si, 0, sizeof si); memset(&pi, 0, sizeof pi);
	si.cb = sizeof si;
	si.dwFlags = STARTF_USESHOWWINDOW;
	si.wShowWindow = cfg.autoMinimized ? SW_SHOWMINNOACTIVE : SW_SHOWNOACTIVATE;
	if(CreateProcessW(NULL, wcmd, NULL, NULL, FALSE, 0, NULL, wdir[0] ? wdir : NULL, &si, &pi)){
		CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
		g_autoResult = 1;
		printf("[%s] Autostart: Einstellungs-Tool gestartet%s
", PLUG_NAME, cfg.autoMinimized ? " (minimiert)" : "");
	}else{
		g_autoResult = -1;
		printf("[%s] Autostart: Start fehlgeschlagen (Fehler %lu): %s
", PLUG_NAME, (unsigned long)GetLastError(), cmd);
	}
}

static int cmd_reload(int unused){ loadAndApply("Konsole"); return 1; }
static int cmd_status(int unused){ applySettings("Status"); return 1; }
static int cmd_log(int on){ cfg.logDamage = on != 0; applySettings("Log"); return cfg.logDamage; }

static int g_frame = 0;

static void frameTick(void *RES){
	g_frame++;
	if((g_frame % 60) == 0 && iniChanged()){
		defaults(&cfg); readIni(&cfg);
		applySettings("Datei geaendert");
	}
	unitsTick();
}

static void initPlugin(void *RES){
	initGameDir();
	loadAndApply("Start");
	autostartTool();
	writeStatus();
	info->addCommand_Advanced("twext.reload", (void *)cmd_reload, TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("twext.status", (void *)cmd_status, TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("twext.log",    (void *)cmd_log,    TW_CMD_INT,  TW_CMD_INT);
	info->addHook_PostDebug((_GenericCallback)frameTick);
	printf("[%s] geladen - Konsole: twext.reload / twext.status / twext.log <0|1>\n", PLUG_NAME);
}

#define REQVER 1
#define PLUGINVER 1
#define PLUGINREV 4

EXPORT int WINAPI InitPlugin(TWSE_INFO* gInfo, _GetFork gf){
	info = gInfo;
	info->addHook_PreMainLoop((_GenericCallback)initPlugin);
	return 0;
}

EXPORT int WINAPI InfoExchange(INFO_EXCHANGE* exch, _GetFork gf){ return 0; }

PLUGIN_INFO THIS_PLUG_INFO = {
	APIVersion: CURVER,
	Version: PLUGINVER,
	Revision: PLUGINREV,
	Name: L"TWExtended",
	Description: L"Adjustable fall, slide and lava damage, immortal horse, whistle range, damage diagnostics, opens the settings tool with the game; settings from tw1_Extendet-settings.ini",
	Credits: L"Built on TWSE by buglord",
	License: LICENSE_CC0,
0};

EXPORT int WINAPI PluginInfo(PLUGIN_INFO** pp_info, _GetFork gf){
	PLUGIN_INFO* p_info = *pp_info;
	*pp_info = &THIS_PLUG_INFO;
	if(p_info->APIVersion < REQVER) return ERR_LOADER_OUT_OF_DATE;
	if(p_info->Version != 1700) return ERR_GAMEVERSION_UNSUPPORTED;
	return 0;
}
