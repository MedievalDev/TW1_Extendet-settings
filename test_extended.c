/* Offline-Test: INI-Leser und Landungsroutine mit nachgebautem Controller. */
#define TWEXT_TEST 1
#include "tw_extended.c"
#undef printf

static int calls_kill = 0, calls_fall = 0, last_fall = -1;
static void __fastcall fakeKill(void *c, void *e, int v){ calls_kill++; }
static void __fastcall fakeFall(void *c, void *e, int v){ calls_fall++; last_fall = v; }
static void *fakeVt[64];
static char ctrl[0x200];

static void reset_ctrl(float sturz, int hp, int maxhp){
	memset(ctrl, 0, sizeof ctrl);
	*(void ***)ctrl = (void **)fakeVt;
	CTRL_F(ctrl, 0xC4) = sturz; CTRL_I(ctrl, 0x134) = hp; CTRL_I(ctrl, 0x138) = maxhp;
	calls_kill = calls_fall = 0; last_fall = -1;
}
static int fails = 0;
#define CHECK(c) do{ if(!(c)){ fails++; fprintf(stderr, "FAIL %d: %s\n", __LINE__, #c);} }while(0)

int main(){
	fakeVt[VT_SETKILL / 4] = (void *)fakeKill; fakeVt[VT_SETFALL / 4] = (void *)fakeFall;
	defaults(&cfg);
	/* Original-Verhalten: Sturzwert 120 -> Hoehe 12 -> (12-8)*0.0588*100 = 23% */
	reset_ctrl(120.0f, 500, 500); hookLanding(ctrl);
	CHECK(calls_fall == 1 && last_fall == 23 && calls_kill == 0);
	CHECK(CTRL_I(ctrl, 0x114) == 1 && CTRL_I(ctrl, 0xCC) == 7);
	/* unter Mindesthoehe */
	reset_ctrl(70.0f, 500, 500); hookLanding(ctrl); CHECK(calls_fall == 0 && calls_kill == 0);
	/* ueber Todeshoehe */
	reset_ctrl(260.0f, 500, 500); hookLanding(ctrl); CHECK(calls_kill == 1 && calls_fall == 0);
	/* Schaden waere toedlich: 23% von 500 = 115 >= 100 HP */
	reset_ctrl(120.0f, 100, 500); hookLanding(ctrl); CHECK(calls_kill == 1 && calls_fall == 0);
	/* Skalierung 50% -> 11% */
	cfg.fallPercent = 50; reset_ctrl(120.0f, 500, 500); hookLanding(ctrl); CHECK(last_fall == 11);
	/* Skalierung 0% -> 0, kein Tod trotz wenig HP */
	cfg.fallPercent = 0; reset_ctrl(120.0f, 1, 500); hookLanding(ctrl); CHECK(last_fall == 0 && calls_kill == 0);
	/* Todeshoehe 0 = nie */
	cfg.fallPercent = 100; cfg.fallDeathHeight = 0; cfg.fallLethal = 0; reset_ctrl(400.0f, 5000, 5000); hookLanding(ctrl);
	CHECK(calls_kill == 0 && last_fall == (int)((40 - 8) * 0.05882353f * 100));
	/* Lethal aus: nur Prozent, kein Kill-Flag */
	cfg.fallDeathHeight = 25; cfg.fallLethal = 0; reset_ctrl(120.0f, 100, 500); hookLanding(ctrl);
	CHECK(calls_kill == 0 && last_fall == 23);
	/* ganz aus */
	cfg.fallEnabled = 0; reset_ctrl(260.0f, 500, 500); hookLanding(ctrl); CHECK(calls_kill == 0 && calls_fall == 0 && CTRL_I(ctrl, 0x114) == 0);
	/* Mindesthoehe 12: Sturzwert 120 -> Hoehe 12 -> nichts */
	cfg.fallEnabled = 1; cfg.fallMinHeight = 12; reset_ctrl(120.0f, 500, 500); hookLanding(ctrl); CHECK(calls_fall == 0);

	/* INI-Leser */
	strcpy(g_gameDir, ".\\");
	FILE *f = fopen(INI_NAME, "w");
	fprintf(f, "; test\n[FallDamage]\nEnabled = 0 ; aus\nPercent=250\nMinHeight=3.5\nDeathHeight=0\nLethal=0\n[SlideDamage]\nEnabled=1\nPercent=999\nGraceTicks=5\n[LavaDamage]\nEnabled=0\nPercent=250\nEveryFrames=7\n[Horse]\nImmortal=1\nWhistleRangeMeters=250\n[Diagnose]\nLogDamage=1\n");
	fclose(f);
	defaults(&cfg); CHECK(readIni(&cfg) == 1);
	CHECK(cfg.fallEnabled == 0 && cfg.fallPercent == 250 && cfg.fallMinHeight == 3.5f && cfg.fallDeathHeight == 0 && cfg.fallLethal == 0);
	CHECK(cfg.slideEnabled == 1 && cfg.slidePercent == 100 && cfg.slideGrace == 5 && cfg.logDamage == 1);
	CHECK(cfg.horseImmortal == 1 && cfg.whistleMeters == 250);
	CHECK(cfg.lavaEnabled == 0 && cfg.lavaPercent == 100 && cfg.lavaEvery == 7);
	remove(INI_NAME);
	/* Standarddatei schreiben und wieder lesen */
	writeDefaultIni(); defaults(&cfg); cfg.fallPercent = 1; CHECK(readIni(&cfg) == 1 && cfg.fallPercent == 100 && cfg.slideGrace == 30 && cfg.whistleMeters == 0 && cfg.horseImmortal == 0 && cfg.lavaPercent == 5 && cfg.lavaEvery == 1);
	/* Lava-Tick: Prozent und Takt */
	defaults(&cfg); cfg.lavaEvery = 3; cfg.lavaPercent = 9; reset_ctrl(0, 500, 500);
	for(int i = 0; i < 6; i++) lavaTick(ctrl);
	CHECK(calls_fall == 2 && last_fall == 9);
	cfg.lavaEnabled = 0; reset_ctrl(0, 500, 500); lavaTick(ctrl); CHECK(calls_fall == 0);
	/* Autostart: Standard aus, Pfade mit ; und # bleiben ganz */
	writeDefaultIni(); defaults(&cfg); cfg.autoStart = 1; CHECK(readIni(&cfg) == 1 && cfg.autoStart == 0 && cfg.autoMinimized == 1 && cfg.toolPath[0] == 0);
	f = fopen(INI_NAME, "w");
	fprintf(f, "[Diagnose]\nToolPath=C:\\falsch.exe\n[Autostart]\nEnabled=1 ; an\nMinimized=0\n"
	           "ToolPath=C:\\Spiele\\Mods;#1\\tw1_Extendet-settings.exe\nToolArgs = \"C:\\a b\\tool.py\"\n");
	fclose(f);
	defaults(&cfg); CHECK(readIni(&cfg) == 1);
	CHECK(cfg.autoStart == 1 && cfg.autoMinimized == 0);
	CHECK(strcmp(cfg.toolPath, "C:\\Spiele\\Mods;#1\\tw1_Extendet-settings.exe") == 0);
	CHECK(strcmp(cfg.toolArgs, "\"C:\\a b\\tool.py\"") == 0);
	{
		char cmd[3 * MAX_PATH];
		CHECK(buildToolCommand(cmd, sizeof cmd, &cfg, 4242));
		CHECK(strcmp(cmd, "\"C:\\Spiele\\Mods;#1\\tw1_Extendet-settings.exe\" \"C:\\a b\\tool.py\" --from-game 4242") == 0);
		cfg.autoMinimized = 1; cfg.toolArgs[0] = 0;
		CHECK(buildToolCommand(cmd, sizeof cmd, &cfg, 7));
		CHECK(strcmp(cmd, "\"C:\\Spiele\\Mods;#1\\tw1_Extendet-settings.exe\" --from-game 7 --minimized") == 0);
		CHECK(!buildToolCommand(cmd, 20, &cfg, 7));
	}
	remove(INI_NAME);
	fprintf(stderr, fails ? "FEHLER: %d\n" : "ALLE TESTS OK\n", fails);
	return fails != 0;
}
