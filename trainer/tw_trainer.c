/*
 * TW Trainer - Two Worlds 1 Trainer Plugin for TWSE (Two Worlds Script Extender)
 *
 * Nutzt die eingebauten Vanilla-Konsolenbefehle des Spiels (AddGold,
 * AddExperiencePoints, AddSkillPoints, heal, ...) ueber die CommandList
 * aus TWGlobals und legt Hotkeys + eigene Konsolenbefehle darauf.
 *
 * Godmode laeuft ueber die EarthC-API (CUnitBase::EC_SetHP / EC_SetMana):
 * Die HP (und optional Mana) des Helden werden jeden Frame auf das
 * Maximum gesetzt. Funktionszeiger kommen bevorzugt aus
 * info->EarthCApi; als Fallback dienen die festen Adressen aus dem
 * EarthC API Dump (Spielversion 1.7).
 *
 * Getestet gegen: Two Worlds 1, Version 1.7 (Steam).
 * Build: i386-win32-tcc -shared -o TWTrainer.dll tw_trainer.c
 *
 * Hotkeys (im Spiel, Strg muss gehalten werden, da F1-F8 belegt sind):
 *   Strg+F1 - Heilen (heal)
 *   Strg+F2 - +10.000 Gold (AddGold)
 *   Strg+F3 - +5.000 Erfahrung (AddExperiencePoints)
 *   Strg+F4 - +10 Fertigkeitspunkte (AddSkillPoints)
 *   Strg+F5 - +10 Parameterpunkte (AddParamPoints)
 *   Strg+F6 - Super-Speed umschalten (x4 Laufgeschwindigkeit)
 *   Strg+F7 - Godmode umschalten (HP jeden Frame voll)
 *   Strg+F8 - Unendlich Mana umschalten (mit Godmode unabhaengig)
 *   Strg+F9 - Fallschaden an/aus (Vanilla-Befehl "hitfall")
 *   Strg+F10- anvisiertes Ziel toeten (Vanilla-Befehl "kill")
 *   Strg+F11- Helden wiederbeleben und HP auffuellen
 *   Strg+F12- Zeitraffer an/aus (gamerate 5x)
 *
 * Hinweis: Der Cheat-Modus des Spiels ("TwoWorldsCheats") wird beim
 * ersten Frame automatisch aktiviert - ohne ihn ignorieren die Vanilla-
 * Befehle (AddGold etc.) ihre Aufrufe. Manuell: trainer.cheats
 *
 * Teleport-Netz: Beim Start wird CUnitBase::EC_IsTeleportEnabled so
 * gepatcht, dass jeder Teleporter als aktiviert gilt - das komplette
 * Teleport-Netz ist sofort nutzbar.
 *
 * Konsolenbefehle (Spiel-Konsole):
 *   trainer.gold <n>      - n Gold hinzufuegen
 *   trainer.setgold <n>   - Gold auf n setzen
 *   trainer.exp <n>       - n Erfahrungspunkte hinzufuegen
 *   trainer.skill <n>     - n Fertigkeitspunkte hinzufuegen
 *   trainer.param <n>     - n Parameterpunkte hinzufuegen
 *   trainer.str <n>       - Staerke setzen
 *   trainer.heal          - vollstaendig heilen
 *   trainer.speed <n>     - Laufgeschwindigkeit direkt setzen
 *   trainer.god           - Godmode an/aus
 *   trainer.mana          - Unendlich Mana an/aus
 *   trainer.infgold [n]   - Unendlich Gold an/aus (Standard 16395). Der
 *                            Betrag wird jeden Frame zurueckgeschrieben,
 *                            Kaeufe ziehen ihn also nicht dauerhaft ab.
 *                            Mit n eigener Betrag, 0 schaltet aus.
 *   trainer.cheats        - Cheat-Modus manuell (erneut) aktivieren
 *   trainer.teleports     - Teleport-Patch manuell anwenden (laueft
 *                            automatisch beim Plugin-Start)
 *   trainer.exec <cmd> [n]- beliebigen Vanilla-Befehl aufrufen, z.B.
 *                            trainer.exec AddGold 5000
 */
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>
#include "twse_plugin.h"   /* Include-Verzeichnis twse\ oder ..\twse\ aus dem Build-Skript */

static TWSE_INFO* info;

/* --------------------------------------------------------- */
/* Ausgabe                                                    */
/* --------------------------------------------------------- */

/* Alles geht zusaetzlich nach TWTrainer.log im Spielordner. Das
 * Konsolenfenster von -TWSEdebug ist nach dem Beenden des Spiels weg,
 * die Datei bleibt - nur so laesst sich hinterher nachsehen, was
 * passiert ist. */
static FILE *g_logFile = 0;
static int g_logTried = 0;

/* Absoluter Pfad neben der Spiel-EXE. Ein relativer Name reicht nicht: das
 * Arbeitsverzeichnis des Spiels ist zur Laufzeit nicht zwingend der
 * Spielordner, dann entsteht die Datei woanders oder gar nicht. */
static void openLog(void){
	char path[MAX_PATH];
	DWORD n = GetModuleFileNameA(NULL, path, MAX_PATH);
	if(n > 0 && n < MAX_PATH){
		int cut = -1;
		for(DWORD i = 0; i < n; i++)
			if(path[i] == '\\') cut = (int)i;
		if(cut >= 0){
			path[cut + 1] = 0;
			strcat(path, "TWTrainer.log");
			g_logFile = fopen(path, "a");
		}
	}
	if(g_logFile == 0)
		g_logFile = fopen("TWTrainer.log", "a");
	if(g_logFile){
		fprintf(g_logFile, "\n=== TWTrainer Log ===\n");
		fflush(g_logFile);
	}
}

static void twlog(const char *fmt, ...){
	va_list ap;
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);

	if(!g_logTried){
		g_logTried = 1;
		openLog();
	}
	if(g_logFile){
		va_start(ap, fmt);
		vfprintf(g_logFile, fmt, ap);
		va_end(ap);
		fflush(g_logFile);
	}
}

/* Ab hier schreibt jedes printf in Konsole und Datei zugleich. */
#define printf twlog

/* --------------------------------------------------------- */
/* Vanilla-Befehle ueber die CommandList suchen und aufrufen */
/* --------------------------------------------------------- */

/* CommandList ist ein TW_ExpandingArray_Base aus TW_Command* Zeigern.
 * Layout durch extract_commands.c aus dem Misc-Repo bestaetigt. */
static TW_Command* findCommand(const char *name){
	TW_ExpandingArray_Base *list = info->TWGlobals->CommandList;
	if(list == 0 || list->Data == 0) return 0;
	TW_Command **arr = (TW_Command **)list->Data;
	for(DWORD i = 0; i < list->Entries; i++){
		TW_Command *cmd = arr[i];
		if(cmd == 0 || cmd->CommandString == 0) continue;
		if(stricmp(cmd->CommandString->Text, name) == 0)
			return cmd;
	}
	return 0;
}

/* Ruft einen Vanilla-Befehl vom Typ Function(INT) -> INT auf.
 * Rueckgabe: 1 bei Erfolg, 0 wenn Befehl nicht gefunden/kein Funktionsbefehl. */
static int callIntCommand(const char *name, int value){
	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] Befehl nicht gefunden: %s\n", name);
		return 0;
	}
	if(!(cmd->Flags & TW_CMD_FUNC)){
		printf("[TWTrainer] %s ist kein Funktionsbefehl (Flags=0x%X)\n", name, cmd->Flags);
		return 0;
	}
	typedef int (*CmdIntFunc)(int);
	int result = ((CmdIntFunc)cmd->CommandTarget)(value);
	printf("[TWTrainer] %s(%d) -> %d\n", name, value, result);
	return 1;
}

/* Ruft einen Vanilla-Befehl vom Typ Function() -> INT auf. */
static int callVoidCommand(const char *name){
	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] Befehl nicht gefunden: %s\n", name);
		return 0;
	}
	if(!(cmd->Flags & TW_CMD_FUNC)){
		printf("[TWTrainer] %s ist kein Funktionsbefehl (Flags=0x%X)\n", name, cmd->Flags);
		return 0;
	}
	typedef int (*CmdVoidFunc)();
	int result = ((CmdVoidFunc)cmd->CommandTarget)();
	printf("[TWTrainer] %s() -> %d\n", name, result);
	return 1;
}

/* Ruft einen Vanilla-Befehl vom Typ Function(STRING) -> INT auf. */
static int callStringCommand(const char *name, char *param){
	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] Befehl nicht gefunden: %s\n", name);
		return 0;
	}
	if(!(cmd->Flags & TW_CMD_FUNC)){
		printf("[TWTrainer] %s ist kein Funktionsbefehl (Flags=0x%X)\n", name, cmd->Flags);
		return 0;
	}
	typedef int (*CmdStrFunc)(char *);
	int result = ((CmdStrFunc)cmd->CommandTarget)(param);
	printf("[TWTrainer] %s(\"%s\") -> %d\n", name, param, result);
	return 1;
}

/* Diagnose: zeigt, wohin ein Vanilla-Befehl zeigt und welche Flags er hat.
 * Damit laesst sich die Zielfunktion anschliessend in der EXE ansehen. */
static void dumpCommandAddr(const char *name){
	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] cmd '%s': nicht vorhanden\n", name);
		return;
	}
	printf("[TWTrainer] cmd '%s': Target=0x%08X Flags=0x%X %s\n",
		name, (unsigned int)cmd->CommandTarget, cmd->Flags,
		(cmd->Flags & TW_CMD_FUNC) ? "(Funktion)" : "(Variable)");
}

/* Die Cheat-Befehle (hitfall, gamerate, ...) pruefen am Funktionsanfang
 * alle dieselben globalen Schalter und steigen sonst wirkungslos aus.
 * Aus der Disassembly von hitfall (0x576840) und gamerate (0x57B010). */
#define GATE_A (*(int *)0x00A8FD70)
#define GATE_B (*(int *)0x00A90CA8)
#define GATE_C (*(int *)0x00AB4174)
#define GATE_D (*(int *)0x00A8FD84)
#define GATE_E (*(int *)0x00AB4018)

static void dumpGateFlags(const char *when){
	printf("[TWTrainer] Gates %s: A(0xA8FD70)=%d B(0xA90CA8)=0x%X "
		"C(0xAB4174)=%d D(0xA8FD84)=%d E(0xAB4018)=%d\n",
		when, GATE_A, (unsigned int)GATE_B, GATE_C, GATE_D, GATE_E);
}

/* --------------------------------------------------------- */
/* Konsolenzeilen und Skriptdateien ausfuehren               */
/* --------------------------------------------------------- */

/* Die CommandList enthaelt zwei Sorten Eintraege:
 *   - Funktionsbefehle (Flags & TW_CMD_FUNC), z.B. AddGold, ec.dbg
 *   - benannte Speicherstellen (ohne das Bit), z.B. Engine.FarPlane -
 *     dort zeigt CommandTarget direkt auf die Variable.
 * Der Datentyp steht in den unteren Flag-Bits (TW_CMD_INT/UINT/FLOAT/...). */
static int execLine(const char *rawline){
	char line[512];
	int i = 0;
	while(rawline[i] != 0 && rawline[i] != '\r' && rawline[i] != '\n' && i < 511){
		line[i] = rawline[i]; i++;
	}
	line[i] = 0;

	/* fuehrende Leerzeichen weg, Leerzeilen und Kommentare ueberspringen */
	char *p = line;
	while(*p == ' ' || *p == '\t') p++;
	if(*p == 0 || *p == '#' || (*p == '/' && p[1] == '/')) return 1;

	char name[128];
	int n = 0;
	while(p[n] != 0 && p[n] != ' ' && p[n] != '\t' && n < 127){ name[n] = p[n]; n++; }
	name[n] = 0;
	char *rest = p + n;
	while(*rest == ' ' || *rest == '\t') rest++;

	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] script: unbekannter Befehl '%s'\n", name);
		return 0;
	}
	int type = cmd->Flags & 0xF;
	void *target = cmd->CommandTarget;
	if(target == 0){
		printf("[TWTrainer] script: '%s' hat kein Ziel (Flags=0x%X)\n", name, cmd->Flags);
		return 0;
	}

	if(cmd->Flags & TW_CMD_FUNC){
		switch(type){
			case TW_CMD_NONE:   ((int (*)())target)(); break;
			case TW_CMD_INT:
			case TW_CMD_UINT:   ((int (*)(int))target)(atoi(rest)); break;
			case TW_CMD_FLOAT:  ((int (*)(float))target)((float)atof(rest)); break;
			case TW_CMD_STRING: ((int (*)(char *))target)(rest); break;
			default:
				printf("[TWTrainer] script: '%s' unbekannter Funktionstyp (Flags=0x%X)\n",
					name, cmd->Flags);
				return 0;
		}
		return 1;
	}

	/* benannte Speicherstelle - Wert direkt schreiben */
	if(*rest == 0){
		printf("[TWTrainer] script: '%s' braucht einen Wert\n", name);
		return 0;
	}
	/* Wert schreiben und sofort zurueckvergleichen. Wenn die Werte aus
	 * test.txt nicht wirken, sieht man hier, ob sie gar nicht ankommen oder
	 * spaeter vom Spiel wieder ueberschrieben werden. */
	switch(type){
		case TW_CMD_INT: {
			int want = atoi(rest);
			*(int *)target = want;
			int got = *(int *)target;
			if(got != want)
				printf("[TWTrainer] script: '%s' nicht uebernommen (gesetzt %d, "
					"gelesen %d)\n", name, want, got);
			break;
		}
		case TW_CMD_UINT: {
			unsigned int want = (unsigned int)strtoul(rest, 0, 0);
			*(unsigned int *)target = want;
			if(*(unsigned int *)target != want)
				printf("[TWTrainer] script: '%s' nicht uebernommen\n", name);
			break;
		}
		case TW_CMD_FLOAT: {
			float want = (float)atof(rest);
			*(float *)target = want;
			if(*(float *)target != want)
				printf("[TWTrainer] script: '%s' nicht uebernommen\n", name);
			break;
		}
		default:
			printf("[TWTrainer] script: '%s' unbekannter Variablentyp (Flags=0x%X)\n",
				name, cmd->Flags);
			return 0;
	}
	return 1;
}

/* Liest einen benannten Wert zurueck - damit laesst sich pruefen, ob eine
 * Einstellung aus test.txt spaeter vom Spiel wieder ueberschrieben wurde. */
static int showValue(const char *name){
	TW_Command *cmd = findCommand(name);
	if(cmd == 0){
		printf("[TWTrainer] '%s' unbekannt\n", name);
		return 0;
	}
	int type = cmd->Flags & 0xF;
	void *t = cmd->CommandTarget;
	if(t == 0 || (cmd->Flags & TW_CMD_FUNC)){
		printf("[TWTrainer] '%s' ist keine Variable (Flags=0x%X)\n", name, cmd->Flags);
		return 0;
	}
	if(type == TW_CMD_FLOAT)
		printf("[TWTrainer] %s = %d (float, gerundet)\n", name, (int)(*(float *)t));
	else
		printf("[TWTrainer] %s = %d\n", name, *(int *)t);
	return 1;
}

/* Fuehrt eine Datei zeilenweise als Konsolenbefehle aus. */
static int runScript(const char *path){
	FILE *fh = fopen(path, "r");
	if(fh == 0){
		printf("[TWTrainer] script: '%s' nicht gefunden\n", path);
		return 0;
	}
	char buf[512];
	int ok = 0, fail = 0;
	while(fgets(buf, sizeof(buf), fh) != 0){
		if(execLine(buf)) ok++; else fail++;
	}
	fclose(fh);
	printf("[TWTrainer] script '%s': %d Zeilen ausgefuehrt, %d fehlgeschlagen\n", path, ok, fail);
	return fail == 0;
}

/* --------------------------------------------------------- */
/* EarthC-Spiel-Funktionen (Godmode)                         */
/* --------------------------------------------------------- */

typedef int  (__stdcall *FN_GetInt)(void* thisObj);
typedef void (__stdcall *FN_SetInt)(void* thisObj, int v);
typedef void (__stdcall *FN_Void)(void* thisObj);

/* Feste Adressen aus dem EarthC API Dump (Two Worlds 1.7) als Fallback,
 * falls info->EarthCApi (noch) nicht verfuegbar ist. */
#define ADDR_GetMaxHP    0x006714D0  /* CUnitBase::EC_GetMaxHP()      */
#define ADDR_GetHP       0x006714B0  /* CUnitBase::EC_GetHP()         */
#define ADDR_SetHP       0x0069ED40  /* CUnitBase::EC_SetHP(int)      */
#define ADDR_GetMaxMana  0x00639480  /* CUnit::EC_GetMaxMana()        */
#define ADDR_GetMana     0x00639450  /* CUnit::EC_GetMana()           */
#define ADDR_SetMana     0x0069ED60  /* CUnitBase::EC_SetMana(int)    */
#define ADDR_GetMoney    0x006A18C0  /* CUnitBase::EC_GetMoney()      */
#define ADDR_SetMoney    0x006A18F0  /* CUnitBase::EC_SetMoney(int)   */
#define ADDR_HealPoison  0x0069EDC0  /* CUnitBase::EC_HealPoison()    */
#define ADDR_KillObject  0x0069EE30  /* CUnitBase::EC_KillObject()    */
#define ADDR_Resurrect   0x0069DCD0  /* CUnitBase::EC_ResurrectUnit() */
#define ADDR_ResetFog       0x00633EC0 /* CPlayerInterface::EC_ResetGraphicFogOfWar */
#define ADDR_GetMission     0x00671D50 /* CUnitBase::EC_GetMission()     */
#define ADDR_GetWorldWidth  0x00671D10 /* CUnitBase::EC_GetWorldWidth()  */
#define ADDR_GetWorldHeight 0x00671D30 /* CUnitBase::EC_GetWorldHeight() */

static FN_GetInt fn_GetMaxHP   = (FN_GetInt)ADDR_GetMaxHP;
static FN_GetInt fn_GetHP      = (FN_GetInt)ADDR_GetHP;
static FN_SetInt fn_SetHP      = (FN_SetInt)ADDR_SetHP;
static FN_GetInt fn_GetMaxMana = (FN_GetInt)ADDR_GetMaxMana;
static FN_GetInt fn_GetMana    = (FN_GetInt)ADDR_GetMana;
static FN_SetInt fn_SetMana    = (FN_SetInt)ADDR_SetMana;
static FN_GetInt fn_GetMoney   = (FN_GetInt)ADDR_GetMoney;
static FN_SetInt fn_SetMoney   = (FN_SetInt)ADDR_SetMoney;
static FN_Void   fn_HealPoison = (FN_Void)ADDR_HealPoison;
static FN_Void   fn_KillObject = (FN_Void)ADDR_KillObject;
static FN_Void   fn_Resurrect  = (FN_Void)ADDR_Resurrect;


/* Teleport des Spiels, benutzt in ActionTeleportHero (PQuestActions.ech):
 *   int SetImmediatePosition(int nX, int nY, int nZ, int nAlpha,
 *                            int bSetIfNotFree)
 * X und Y werden uebernommen, die Hoehe nicht: das Spiel setzt den Helden
 * immer auf den Boden am Zielpunkt. Ein Flugmodus ist damit nicht moeglich
 * (nachgemessen), Teleportieren dagegen schon. */
typedef int (__stdcall *FN_SetImmPos)(void *thisObj, int x, int y, int z,
	int alpha, int setIfNotFree);

static FN_SetImmPos fn_SetImmPos    = 0;
static FN_GetInt    fn_GetLocationX = 0;
static FN_GetInt    fn_GetLocationY = 0;
static FN_GetInt    fn_GetLocationZ = 0;
static FN_GetInt    fn_GetDirAlpha  = 0;

/* Pferd holen.
 *
 * Das Rufen selbst steckt in der Engine, nicht im Skript - der ganze
 * Skriptbaum kennt dazu nur eine Warteschleife in Units/Other.ech, die
 * fragt, ob IsCallingHorse() fertig ist. Eine Reichweite steht nirgends im
 * Skript oder im Par, und CallCallHorse() nimmt keinen Parameter.
 *
 * Statt die Reichweite zu suchen, wird hier das Ergebnis erzeugt: sobald der
 * Held zu pfeifen anfaengt, setzt der Trainer das Pferd neben ihn. Das wirkt
 * auf jede Entfernung und benutzt weiter das Pfeifen des Spiels. */
typedef void* (__stdcall *FN_HorsePtr)(void *thisObj);
static FN_HorsePtr  fn_GetHorse       = 0;
static FN_GetInt    fn_IsCallingHorse = 0;

/* Fertigkeiten. Die Schlosslogik steht im SDK in Common/Lock.ech:
 *   Diff = Schlossstufe - GetSkill(eSkillLockPicking)
 *   Diff < -8 -> 99% Chance, Diff 0 -> 40%, Diff > 5 -> 0%
 * Ein hoher Skillwert macht damit jedes Schloss praktisch sicher.
 * Achtung: ohne Dietriche im Inventar steigt die Funktion vorher aus,
 * unabhaengig vom Skill. */
typedef void* (__stdcall *FN_GetValues)(void *thisObj);
typedef void  (__stdcall *FN_SetSkill)(void *values, int index, int value);
typedef int   (__stdcall *FN_GetSkill)(void *values, int index);
typedef int   (__stdcall *FN_KeyCount)(void *thisObj, int a, int b);

static FN_GetValues fn_GetUnitValues = 0;
static FN_SetSkill  fn_SetSkill      = 0;
static FN_GetSkill  fn_GetSkill      = 0;
static FN_KeyCount  fn_KeyArtefacts  = 0;

/* Reihenfolge aus Documentation/EarthC/object.htm, ab eSkillAttack = 0 */
#define SKILL_LOCKPICKING 15
#define SKILL_COUNT       38

/* Schloesser und Tueren. Diese Zeiger kommen ausschliesslich aus der
 * EarthC-API - feste Adressen gibt es dafuer bewusst nicht, damit nichts
 * auf geratenen Offsets aufsetzt. Sind sie 0, meldet trainer.unlock das. */
typedef void* (__stdcall *FN_GetUnitIdx)(void *thisObj, int index);
typedef void  (__stdcall *FN_UnitInt)(void *thisObj, int value);
typedef void  (__stdcall *FN_UnitPtr)(void *thisObj, void *other);

static FN_GetInt    fn_SearchUnitsCount = 0;
static FN_GetUnitIdx fn_GetSearchUnit   = 0;
static FN_GetInt    fn_IsGate           = 0;
static FN_GetInt    fn_IsGateOpen       = 0;
static FN_GetInt    fn_IsContainer      = 0;
static FN_GetInt    fn_GetLockLevel     = 0;
static FN_GetInt    fn_GetLockFlags     = 0;
static FN_UnitInt   fn_SetGateLock      = 0;
static FN_UnitInt   fn_SetGateUnlockPar = 0;
static FN_UnitPtr   fn_ClickOnGate      = 0;
static FN_GetInt    fn_IsTeleport       = 0;
static FN_UnitInt   fn_EnableTeleport   = 0;

typedef void  (__stdcall *FN_ResetFog)(void *iface, void *mission, int x, int y, int range);
typedef void* (__stdcall *FN_GetPtr)(void *thisObj);

static FN_ResetFog fn_ResetFog       = (FN_ResetFog)ADDR_ResetFog;
static FN_GetPtr   fn_GetMission     = (FN_GetPtr)ADDR_GetMission;
static FN_GetInt   fn_GetWorldWidth  = (FN_GetInt)ADDR_GetWorldWidth;
static FN_GetInt   fn_GetWorldHeight = (FN_GetInt)ADDR_GetWorldHeight;

static int g_ecResolved = 0;

/* Bevorzugt die Zeiger aus der EarthC-API des Spiels uebernehmen
 * (versionsunabhaengiger als feste Adressen).
 * Die API wird erst vom Spiel selbst angelegt und ist im PreMainLoop
 * haeufig noch nicht bereit - darum wird bis zum Erfolg jeden Frame
 * erneut aufgeloest. Bis dahin greifen die festen Adressen. */
static void resolveGameFuncs(){
	if(g_ecResolved) return;
	if(!(info->EarthCApi && info->EarthCApi->functionsAvailable && info->EarthCApi->functions))
		return;
	struct EarthCFunctions *ec = info->EarthCApi->functions;
	fn_GetMaxHP   = ec->CUnitBase__EC_GetMaxHP;
	fn_GetHP      = ec->CUnitBase__EC_GetHP;
	fn_SetHP      = ec->CUnitBase__EC_SetHP;
	fn_GetMaxMana = ec->CUnit__EC_GetMaxMana;
	fn_GetMana    = ec->CUnit__EC_GetMana;
	fn_SetMana    = ec->CUnitBase__EC_SetMana;
	fn_HealPoison = ec->CUnitBase__EC_HealPoison;
	fn_KillObject = ec->CUnitBase__EC_KillObject;
	fn_Resurrect  = ec->CUnitBase__EC_ResurrectUnit;
	fn_SearchUnitsCount = (FN_GetInt)ec->CUnitBase__EC_GetSearchUnitsCount;
	fn_GetSearchUnit    = (FN_GetUnitIdx)ec->CUnitBase__EC_GetSearchUnit;
	fn_IsGate           = (FN_GetInt)ec->CUnitBase__EC_IsGate;
	fn_IsGateOpen       = (FN_GetInt)ec->CUnitBase__EC_IsGateOpen;
	fn_IsContainer      = (FN_GetInt)ec->CUnitBase__EC_IsContainer;
	fn_GetLockLevel     = (FN_GetInt)ec->CUnitBase__EC_GetLockLevel;
	fn_GetLockFlags     = (FN_GetInt)ec->CUnitBase__EC_GetLockFlags;
	fn_SetGateLock      = (FN_UnitInt)ec->CUnitBase__EC_SetGateLockForUnits;
	fn_SetGateUnlockPar = (FN_UnitInt)ec->CUnitBase__EC_SetGateUnlockParamsForUnits;
	fn_ClickOnGate      = (FN_UnitPtr)ec->CUnit__EC_CommandClickEventOnGate;
	fn_IsTeleport       = (FN_GetInt)ec->CUnitBase__EC_IsTeleport;
	fn_EnableTeleport   = (FN_UnitInt)ec->CUnitBase__EC_EnableTeleport;
	fn_SetImmPos    = (FN_SetImmPos)ec->CUnitBase__EC_SetImmediatePosition;
	fn_GetUnitValues = (FN_GetValues)ec->CUnit__EC_GetUnitValues;
	fn_SetSkill      = (FN_SetSkill)ec->CUnitValues__EC_SetSkill;
	fn_GetSkill      = (FN_GetSkill)ec->CUnitValues__EC_GetSkill;
	fn_KeyArtefacts  = (FN_KeyCount)ec->CUnitBase__EC_GetKeyArtefactsInInventoryCount;
	fn_GetLocationX = (FN_GetInt)ec->CUnitBase__EC_GetLocationX;
	fn_GetLocationY = (FN_GetInt)ec->CUnitBase__EC_GetLocationY;
	fn_GetLocationZ = (FN_GetInt)ec->CUnitBase__EC_GetLocationZ;
	fn_GetDirAlpha  = (FN_GetInt)ec->CUnitBase__EC_GetDirectionAlpha;
	fn_GetHorse       = (FN_HorsePtr)ec->CUnitBase__EC_GetHorse;
	fn_IsCallingHorse = (FN_GetInt)ec->CUnit__EC_IsCallingHorse;
	fn_ResetFog       = (FN_ResetFog)ec->CPlayerInterface__EC_ResetGraphicFogOfWar;
	fn_GetMission     = (FN_GetPtr)ec->CUnitBase__EC_GetMission;
	fn_GetWorldWidth  = (FN_GetInt)ec->CUnitBase__EC_GetWorldWidth;
	fn_GetWorldHeight = (FN_GetInt)ec->CUnitBase__EC_GetWorldHeight;
	g_ecResolved  = 1;
	printf("[TWTrainer] EarthC-API uebernommen (Godmode bereit)\n");
}

/* --------------------------------------------------------- */
/* Godmode / unendlich Mana                                  */
/* --------------------------------------------------------- */

static int g_godmode = 0;
static int g_infMana = 0;

/* Unendlich Gold: wie beim Godmode das Leben wird der Betrag jeden Frame
 * zurueckgeschrieben. Einmaliges Hochsetzen genuegt nicht, weil Kaeufe ihn
 * abziehen - der feste Wert muss hoch genug sein, damit auch Teures
 * bezahlbar bleibt. 16395 ist in der Praxis erprobt; das Feld ist ein
 * vorzeichenbehafteter 32-Bit-Wert, viel groessere Betraege koennten in
 * der Anzeige oder beim Handel ueberlaufen. */
#define GOLD_AMOUNT 16395
static int g_infGold = 0;
static int g_goldAmount = GOLD_AMOUNT;

static void godmodeTick(){
	if(!g_godmode && !g_infMana && !g_infGold) return;
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0) return;
	if(g_godmode){
		fn_SetHP(hero, fn_GetMaxHP(hero));
	}
	if(g_infMana){
		fn_SetMana(hero, fn_GetMaxMana(hero));
	}
	if(g_infGold){
		/* nur schreiben, wenn noetig - spart einen Aufruf pro Frame und
		 * laesst dem Spiel Ruhe, solange nichts ausgegeben wurde */
		if(fn_GetMoney(hero) != g_goldAmount){
			fn_SetMoney(hero, g_goldAmount);
		}
	}
}

static int toggleGodmode(){
	g_godmode = !g_godmode;
	if(g_godmode){
		TW_Hero* hero = info->TWFuncs->getActiveHero();
		if(hero) fn_HealPoison(hero); /* einmalig entgiften */
		printf("[TWTrainer] Godmode AN\n");
	}else{
		printf("[TWTrainer] Godmode AUS\n");
	}
	return g_godmode;
}

static int toggleInfMana(){
	g_infMana = !g_infMana;
	printf("[TWTrainer] Unendlich Mana %s\n", g_infMana ? "AN" : "AUS");
	return g_infMana;
}

/* trainer.infgold      - unendlich Gold an/aus (Betrag GOLD_AMOUNT)
 * trainer.infgold <n>  - an, mit eigenem Betrag; 0 schaltet aus
 * Nicht zu verwechseln mit trainer.gold, das einmalig n Gold addiert. */
static int toggleInfGold(int amount){
	if(amount > 0){
		g_goldAmount = amount;
		g_infGold = 1;
	}else if(amount == 0 && g_infGold){
		g_infGold = 0;
	}else{
		g_infGold = !g_infGold;
	}
	if(g_infGold){
		TW_Hero* hero = info->TWFuncs->getActiveHero();
		if(hero) fn_SetMoney(hero, g_goldAmount);   /* sofort sichtbar */
		printf("[TWTrainer] Unendlich Gold AN (%d)\n", g_goldAmount);
	}else{
		printf("[TWTrainer] Unendlich Gold AUS\n");
	}
	return g_infGold;
}

/* --------------------------------------------------------- */
/* Fallschaden / Toeten und Wiederbeleben                    */
/* --------------------------------------------------------- */

/* ACHTUNG: "hitfall" ist KEIN Schalter, sondern fuegt Fallschaden ZU - es
 * gehoert zur Reihe hitHP / hitMana / hitPoison. Im Test loeste
 * "trainer.fall 0" den Sturzschaden-Effekt aus, statt ihn abzustellen.
 * Der Befehl heisst deshalb jetzt, was er tut. Fallschaden wirklich
 * abschalten geht nur ueber einen Patch der Berechnung selbst. */
static int g_fallDamage = 1;   /* nur Anzeige, bis der Patch steht */

static int hitFall(int amount){
	printf("[TWTrainer] hitfall(%d): fuegt Fallschaden ZU (kein Schalter)\n", amount);
	return callIntCommand("hitfall", amount);
}

/* Toetet das anvisierte Ziel. Der Vanilla-Befehl "kill" wirkt auf das
 * aktuelle Ziel, "killh" dagegen auf den Helden - deshalb hier "kill". */
static int killTarget(){
	return callVoidCommand("kill");
}

/* Belebt den Helden wieder und fuellt die HP auf. */
static int reviveHero(){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){
		printf("[TWTrainer] Kein aktiver Held\n");
		return 0;
	}
	fn_Resurrect(hero);
	fn_SetHP(hero, fn_GetMaxHP(hero));
	printf("[TWTrainer] Held wiederbelebt\n");
	return 1;
}

/* Toetet den Helden selbst (zum Testen von Tod/Respawn).
 * Godmode wird dafuer abgeschaltet, sonst fuellt der Tick die HP im
 * selben Frame wieder auf und der Held stirbt nie. */
static int killHero(){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){
		printf("[TWTrainer] Kein aktiver Held\n");
		return 0;
	}
	if(g_godmode){
		g_godmode = 0;
		printf("[TWTrainer] Godmode fuer den Tod abgeschaltet\n");
	}
	fn_KillObject(hero);
	printf("[TWTrainer] Held getoetet\n");
	return 1;
}

/* --------------------------------------------------------- */
/* Fog of War der Karte aufdecken                            */
/* --------------------------------------------------------- */

/* Nachbau von (SDK, Network/TownCampaign.ec):
 *   GetPlayerInterface(GetLocalPlayerNum())
 *     .ResetGraphicFogOfWar(GetMission(0), nX, nY, nRange)
 *
 * GetPlayerInterface und GetLocalPlayerNum ignorieren ihr this-Objekt
 * komplett und lesen nur Globale - laut Disassembly von 0x4C73A0 und
 * 0x4C73D0. Deshalb wird die Kette hier direkt nachgebildet, statt sich
 * ein CScriptObject beschaffen zu muessen:
 *   [0xA74F00] Array von Spielern, [0xA74F04] deren Anzahl,
 *   [0xA74E34] Index des lokalen Spielers, Interface liegt bei Spieler+4.
 * ResetGraphicFogOfWar prueft selbst, ob das Interface zum lokalen
 * Spieler gehoert ([this+4] == [0xA74E34]).
 *
 * Die mission kommt vom Helden (CUnitBase::EC_GetMission) und ist damit
 * die aktuell geladene - der Aufruf wirkt also nur auf das Map-Tile,
 * in dem man gerade steht. */
#define PLAYER_ARRAY (*(void ***)0x00A74F00)
#define PLAYER_COUNT (*(int *)0x00A74F04)
#define LOCAL_PLAYER (*(int *)0x00A74E34)

static void* getLocalPlayerInterface(){
	int idx = LOCAL_PLAYER;
	if(idx < 0 || idx >= PLAYER_COUNT) return 0;
	void **players = PLAYER_ARRAY;
	if(players == 0) return 0;
	void *player = players[idx];
	if(player == 0) return 0;
	return *(void **)((char *)player + 4);
}

/* range <= 0: Radius so gross waehlen, dass das ganze Tile aufgedeckt wird
 * (wie im SDK-Skript: groessere Weltkante mal zwei). */
static int clearFogOfWar(int range){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){
		printf("[TWTrainer] Fog: kein aktiver Held (erst Spielstand laden)\n");
		return 0;
	}
	void *iface = getLocalPlayerInterface();
	if(iface == 0){
		printf("[TWTrainer] Fog: kein PlayerInterface (Spieler %d von %d)\n",
			LOCAL_PLAYER, PLAYER_COUNT);
		return 0;
	}
	void *mission = fn_GetMission(hero);
	if(mission == 0){
		printf("[TWTrainer] Fog: keine Mission am Helden\n");
		return 0;
	}
	int w = fn_GetWorldWidth(hero);
	int h = fn_GetWorldHeight(hero);
	if(range <= 0) range = (w > h ? w : h) * 2;
	fn_ResetFog(iface, mission, w / 2, h / 2, range);
	printf("[TWTrainer] Fog of War aufgedeckt (Welt %dx%d, Radius %d)\n", w, h, range);
	return 1;
}
/* --------------------------------------------------------- */
/* Fertigkeiten setzen (u.a. Schlossknacken)                 */
/* --------------------------------------------------------- */

static void* heroValues(void){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){
		printf("[TWTrainer] skill: kein aktiver Held\n");
		return 0;
	}
	if(fn_GetUnitValues == 0){
		printf("[TWTrainer] skill: EarthC-API nicht verfuegbar\n");
		return 0;
	}
	void *v = fn_GetUnitValues(hero);
	if(v == 0) printf("[TWTrainer] skill: keine Wertestruktur am Helden\n");
	return v;
}

static int setSkill(int index, int value){
	void *v = heroValues();
	if(v == 0 || fn_SetSkill == 0) return 0;
	int before = fn_GetSkill ? fn_GetSkill(v, index) : -1;
	fn_SetSkill(v, index, value);
	int after = fn_GetSkill ? fn_GetSkill(v, index) : -1;
	printf("[TWTrainer] Skill %d: %d -> %d (gesetzt %d)\n",
		index, before, after, value);
	if(after != value)
		printf("[TWTrainer] Hinweis: Das Spiel hat den Wert angepasst "
			"(Obergrenze oder Neuberechnung)\n");
	return after;
}

/* Setzt Schlossknacken hoch. 0 als Wert bedeutet: Vorgabe 100 nehmen -
 * damit ist die Differenz zu jedem Schloss (max. Stufe 7) weit unter -8,
 * also 99% Erfolgschance, der Bestwert den die Formel hergibt. */
static int setLockpicking(int value){
	if(value <= 0) value = 100;
	int now = setSkill(SKILL_LOCKPICKING, value);

	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero && fn_KeyArtefacts){
		int keys = fn_KeyArtefacts(hero, 0, 0);
		printf("[TWTrainer] Dietriche im Inventar: %d\n", keys);
		if(keys <= 0)
			printf("[TWTrainer] ACHTUNG: Ohne Dietrich oeffnet sich kein Schloss, "
				"egal wie hoch der Skill ist. Mit trainer.item besorgen.\n");
	}
	return now;
}

/* Listet alle Fertigkeiten mit ihrem aktuellen Wert - damit laesst sich
 * ablesen, welcher Index welche Fertigkeit ist. */
static int listSkills(void){
	void *v = heroValues();
	if(v == 0 || fn_GetSkill == 0) return 0;
	printf("[TWTrainer] Fertigkeiten des Helden:\n");
	for(int i = 0; i < SKILL_COUNT; i++){
		int val = fn_GetSkill(v, i);
		if(val != 0 || i == SKILL_LOCKPICKING)
			printf("[TWTrainer]   %2d = %d%s\n", i, val,
				i == SKILL_LOCKPICKING ? "   <- laut Doku Schlossknacken" : "");
	}
	return 1;
}

/* --------------------------------------------------------- */
/* Schloesser aufsperren                                     */
/* --------------------------------------------------------- */

/* Geht die Units durch, die das Spiel rund um den Helden fuehrt
 * (CUnitBase::GetSearchUnitsCount / GetSearchUnit), und hebt bei jedem
 * Gate die Sperre auf. Die roten, per Quest verriegelten Tueren haengen
 * an SetGateLockForUnits - deshalb wird der Wert als Parameter
 * durchgereicht, damit sich beide Varianten (0 und 1) ausprobieren
 * lassen, ohne neu zu bauen.
 *
 * openToo: zusaetzlich einen Tuerklick ausloesen, also wirklich oeffnen. */
static int unlockAround(int lockValue, int openToo){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){
		printf("[TWTrainer] unlock: kein aktiver Held\n");
		return 0;
	}
	if(fn_SearchUnitsCount == 0 || fn_GetSearchUnit == 0 || fn_IsGate == 0){
		printf("[TWTrainer] unlock: EarthC-API nicht verfuegbar\n");
		return 0;
	}
	int count = fn_SearchUnitsCount(hero);
	printf("[TWTrainer] unlock: %d Units in Reichweite\n", count);
	if(count <= 0){
		printf("[TWTrainer] unlock: keine Units - naeher rangehen oder Ziel anvisieren\n");
		return 0;
	}

	int gates = 0, containers = 0;
	for(int i = 0; i < count; i++){
		void *u = fn_GetSearchUnit(hero, i);
		if(u == 0) continue;
		int isGate = fn_IsGate(u);
		int isCont = fn_IsContainer ? fn_IsContainer(u) : 0;
		if(!isGate && !isCont) continue;
		int lvl   = fn_GetLockLevel  ? fn_GetLockLevel(u)  : -1;
		int flags = fn_GetLockFlags  ? fn_GetLockFlags(u)  : -1;
		printf("[TWTrainer]   #%d %s LockLevel=%d LockFlags=0x%X%s\n", i,
			isGate ? "Gate" : "Container", lvl, flags,
			(isGate && fn_IsGateOpen && fn_IsGateOpen(u)) ? " (offen)" : "");
		if(isGate){
			if(fn_SetGateLock)      fn_SetGateLock(u, lockValue);
			if(fn_SetGateUnlockPar) fn_SetGateUnlockPar(u, lockValue);
			if(openToo && fn_ClickOnGate) fn_ClickOnGate(hero, u);
			gates++;
		}else{
			containers++;
		}
	}
	printf("[TWTrainer] unlock: %d Gates entsperrt, %d Container gefunden\n",
		gates, containers);
	return gates + containers;
}

/* --------------------------------------------------------- */
/* Testhilfen: Zeitraffer, Tageszeit, Rettung                */
/* --------------------------------------------------------- */

static int setGameRate(int rate){
	if(rate < 1) rate = 1;
	callIntCommand("gamerate", rate);
	printf("[TWTrainer] Spielgeschwindigkeit %dx\n", rate);
	return rate;
}

/* --------------------------------------------------------- */
/* Alle Teleporter aktivieren (Byte-Patch)                   */
/* --------------------------------------------------------- */

/* CUnitBase::EC_IsTeleportEnabled (0x614D00, Version 1.7) prueft nach dem
 * Typ-Check (nur echte Teleport-Objekte) das "aktiviert"-Flag in Bit 19
 * von [this+0x1C]:
 *
 *   0x614D1E: 8B 46 1C    mov eax, [esi+0x1C]
 *   0x614D21: C1 E8 13    shr eax, 0x13
 *   0x614D24: 83 E0 01    and eax, 1
 *
 * Ersetzen durch "mov eax, 1" -> jeder Teleporter gilt als aktiviert,
 * das gesamte Teleport-Netz ist von Anfang an nutzbar.
 * Bytes aus TwoWorlds.exe 1.7 verifiziert. */
/* Drei Abfragen entscheiden ueber einen Teleporter, nicht nur eine:
 *   CUnitBase::EC_IsTeleportEnabled      0x614D00, prueft Bit 19
 *   CUnitBase::EC_IsTeleportActiveSource 0x6A03F0, prueft Bit 21
 *   CUnitBase::EC_IsTeleportActiveTarget 0x6A0430, prueft Bit 22
 * Alle drei sind gleich aufgebaut; die Bitpruefung sitzt jeweils 0x1E
 * hinter dem Funktionsanfang, direkt nach dem Typ-Check. Frueher wurde nur
 * die erste gepatcht - deshalb blieben die Teleporter gesperrt. */
static BYTE tpNew[] = {0xB8, 0x01, 0x00, 0x00, 0x00, 0x90, 0x90, 0x90, 0x90};
static BYTE tpOldEnabled[] = {0x8B, 0x46, 0x1C, 0xC1, 0xE8, 0x13, 0x83, 0xE0, 0x01};
static BYTE tpOldSource[]  = {0x8B, 0x46, 0x1C, 0xC1, 0xE8, 0x15, 0x83, 0xE0, 0x01};
static BYTE tpOldTarget[]  = {0x8B, 0x46, 0x1C, 0xC1, 0xE8, 0x16, 0x83, 0xE0, 0x01};
static int g_tpPatched = 0;

static int applyTeleportsPatch(){
	if(g_tpPatched) return 1;
	BYTE_MOD_SET sets[3] = {
		{(LPVOID)0x00614D1E, tpOldEnabled, tpNew, sizeof(tpNew)},
		{(LPVOID)0x006A040E, tpOldSource,  tpNew, sizeof(tpNew)},
		{(LPVOID)0x006A044E, tpOldTarget,  tpNew, sizeof(tpNew)}
	};
	const char *names[3] = {"IsTeleportEnabled", "IsTeleportActiveSource",
		"IsTeleportActiveTarget"};
	int done = 0;
	for(int i = 0; i < 3; i++){
		if(info->replaceByteSet(&sets[i]) == 0){
			done++;
		}else{
			printf("[TWTrainer] Teleport-Patch %s: Bytes passen nicht\n", names[i]);
		}
	}
	if(done == 0){
		printf("[TWTrainer] FEHLER: kein Teleport-Patch angewendet\n");
		return 0;
	}
	g_tpPatched = (done == 3);
	printf("[TWTrainer] Teleporter freigeschaltet (%d von 3 Abfragen gepatcht)\n", done);
	return 1;
}

static int cmd_teleports(int unused){ return applyTeleportsPatch(); }

/* --------------------------------------------------------- */
/* Onscreen-Debug-Buffer (Overlay)                           */
/* --------------------------------------------------------- */

/* Aus der Disassembly von debug_onscreen_print_to_buffer (0x6EAD60)
 * und dem Renderer DBG_PRINT (0x6EAE20), Version 1.7:
 *
 *   [0xAA8F88] char*  Basiszeiger des Textpuffers
 *   [0xAA8F84] int    Bytes pro Zeile (Stride)
 *   [0xAA8F7C] int    Anzahl Zeilen
 *   [0xAA8F70] int    Anzahl Spalten
 *   [0xAB41D8] int    Gate: ist das 0, rendert DBG_PRINT gar nichts
 *   [0xA5EE28] int    zweites Gate, nur fuer print_to_buffer
 *
 * Zeile n liegt bei bufferBase + stride*n, der Renderer gibt je Zeile
 * bis zum ersten Nullbyte aus. */
#define DBG_BUFFER   (*(char **)0x00AA8F88)
#define DBG_STRIDE   (*(int *)0x00AA8F84)
#define DBG_LINES    (*(int *)0x00AA8F7C)
#define DBG_COLS     (*(int *)0x00AA8F70)
#define DBG_GATE     (*(int *)0x00AB41D8)
#define DBG_GATE2    (*(int *)0x00A5EE28)

static void dumpDebugGlobals(){
	printf("[TWTrainer] Debug-Buffer: base=0x%08X stride=%d lines=%d cols=%d gate=%d gate2=%d\n",
		(unsigned int)DBG_BUFFER, DBG_STRIDE, DBG_LINES, DBG_COLS, DBG_GATE, DBG_GATE2);
}

static int g_overlay = 1;
static char g_lastAction[64] = "";

/* Erste Overlay-Zeile. Weiter unten als 0, damit der Text nicht hinter der
 * Lebensleiste oben links liegt. */
#define OVL_LINE 5

/* Schreibt eine Zeile in den Onscreen-Puffer (nullterminiert, geclippt). */
static void dbgSetLine(int line, const char *text){
	char *base = DBG_BUFFER;
	int stride = DBG_STRIDE;
	if(base == 0 || stride <= 1) return;
	if(line < 0 || line >= DBG_LINES) return;
	int max = DBG_COLS;
	if(max > stride - 1) max = stride - 1;
	char *dst = base + (unsigned int)stride * line;
	int i = 0;
	while(text[i] != 0 && i < max){ dst[i] = text[i]; i++; }
	dst[i] = 0;
}

/* --------------------------------------------------------- */
/* Direkter Zugriff auf den Helden (Speed, wie herorunmode)  */
/* --------------------------------------------------------- */

/* Drei Stufen: aus -> 4x -> 6x -> aus, durchgesetzt jeden Frame.
 *
 * Shift ist davon getrennt und wirkt als Flanke: beim Druecken einmal
 * mal 1,4 auf den aktuellen Wert, beim Loslassen exakt zurueck. Frueher
 * lief das ueber einen Dauerfaktor - dabei wurde beim Loslassen der schon
 * erhoehte Wert als neue Basis uebernommen, und die Geschwindigkeit
 * schaukelte sich mit jedem Sprint weiter hoch. */
static WORD g_normalSpeed = 0;          /* unveraenderte Laufgeschwindigkeit */
static int g_speedMode = 0;             /* 0 = aus, 1 = 4x, 2 = 6x */
static int g_sprinting = 0;
static WORD g_preSprint = 0;            /* Wert unmittelbar vor dem Sprint */
static int g_lastFactor = 1;
static const int SPEED_FACTOR[3] = {1, 4, 6};
/* Sprint als Bruch, damit 1,4x ohne Fliesskomma geht */
#define SPRINT_NUM 14
#define SPRINT_DEN 10
#define SPEED_MAX 60000

static int setHeroSpeed(int speed){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0 || hero->UnitHero == 0) return 0;
	g_speedMode = 0;
	g_lastFactor = 1;
	g_normalSpeed = (WORD)speed;
	hero->UnitHero->MoveSpeed = (WORD)speed;
	return speed;
}

static int cycleSpeed(){
	g_speedMode = (g_speedMode + 1) % 3;
	printf("[TWTrainer] Laufgeschwindigkeit %dx\n", SPEED_FACTOR[g_speedMode]);
	return SPEED_FACTOR[g_speedMode];
}

/* Laeuft jeden Frame */
static void speedTick(){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0 || hero->UnitHero == 0) return;

	int shift = (GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0;
	int factor = SPEED_FACTOR[g_speedMode];

	/* Stufe durchsetzen - waehrend eines Sprints nicht, sonst wuerde der
	 * Sprintwert jeden Frame ueberschrieben. */
	if(!g_sprinting){
		if(factor == 1){
			if(g_lastFactor != 1 && g_normalSpeed != 0)
				hero->UnitHero->MoveSpeed = g_normalSpeed;   /* Stufe zurueck */
			else
				g_normalSpeed = hero->UnitHero->MoveSpeed;   /* Basis mitfuehren */
		}else{
			if(g_normalSpeed == 0)
				g_normalSpeed = hero->UnitHero->MoveSpeed;
			DWORD want = (DWORD)g_normalSpeed * (DWORD)factor;
			if(want > SPEED_MAX) want = SPEED_MAX;
			if(hero->UnitHero->MoveSpeed != (WORD)want)
				hero->UnitHero->MoveSpeed = (WORD)want;
		}
		g_lastFactor = factor;
	}

	/* Sprint: einmal drauf, beim Loslassen exakt auf den gemerkten Wert
	 * zurueck - das ist die Division ohne Rundungsdrift. */
	if(shift && !g_sprinting){
		g_preSprint = hero->UnitHero->MoveSpeed;
		DWORD w = (DWORD)g_preSprint * SPRINT_NUM / SPRINT_DEN;
		if(w > SPEED_MAX) w = SPEED_MAX;
		hero->UnitHero->MoveSpeed = (WORD)w;
		g_sprinting = 1;
	}else if(!shift && g_sprinting){
		hero->UnitHero->MoveSpeed = g_preSprint;
		g_sprinting = 0;
	}
}

/* Laeuft im PreDebug-Hook, also direkt bevor das Spiel den Puffer rendert. */
static void drawOverlay(void *RES){
	if(!g_overlay) return;
	/* Ohne dieses Gate rendert DBG_PRINT den Puffer gar nicht erst */
	if(DBG_GATE == 0) DBG_GATE = 1;
	char line[224];
	sprintf(line, "TWTrainer 6.2   God:%s   Speed:%dx%s%s%s",
		g_godmode ? "AN " : "aus",
		SPEED_FACTOR[g_speedMode],
		g_sprinting ? " +Sprint" : "",
		g_lastAction[0] ? "   >> " : "",
		g_lastAction);
	dbgSetLine(OVL_LINE, line);
	dbgSetLine(OVL_LINE + 1,
		"Num0 Anzeige   Num1/ue Schlossknacken   Num2/oe Godmode   "
		"Num3 Speed   Num4/ae Ziel toeten   Num5 Gold");
	dbgSetLine(OVL_LINE + 2,
		"Shift = Sprint (x1,4)   |   alles andere ueber die Konsole: trainer.*");
}

static int cmd_overlay(int unused){
	g_overlay = !g_overlay;
	if(!g_overlay){
		dbgSetLine(OVL_LINE, ""); dbgSetLine(OVL_LINE + 1, ""); dbgSetLine(OVL_LINE + 2, "");
	}
	printf("[TWTrainer] Overlay %s\n", g_overlay ? "AN" : "AUS");
	return g_overlay;
}

/* --------------------------------------------------------- */
/* Eigene Konsolenbefehle (Function(INT) -> INT)             */
/* --------------------------------------------------------- */

/* trainer.tp <x> <y> - Teleport in vollen Weltkoordinaten. Die Hoehe setzt
 * das Spiel selbst auf den Boden am Zielpunkt; vorgeben laesst sie sich
 * nicht, im Test blieb Z bei jedem Versuch unveraendert.
 * Ohne Parameter wird nur die aktuelle Position ausgegeben. */
static int cmd_tp(char *param){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){ printf("[TWTrainer] tp: kein Held\n"); return 0; }
	if(fn_SetImmPos == 0){ printf("[TWTrainer] tp: API fehlt\n"); return 0; }
	int x = fn_GetLocationX(hero), y = fn_GetLocationY(hero);
	int z = fn_GetLocationZ(hero), a = fn_GetDirAlpha(hero);

	int nx = 0, ny = 0;
	if(sscanf(param, "%d %d", &nx, &ny) < 2){
		printf("[TWTrainer] Position: %d %d (Hoehe %d)\n", x, y, z);
		printf("[TWTrainer] Nutzung: trainer.tp <x> <y>\n");
		return x;
	}
	int res = fn_SetImmPos(hero, nx, ny, z, a, 1);
	printf("[TWTrainer] tp %d/%d -> %d/%d (Rueckgabe %d)\n", x, y,
		fn_GetLocationX(hero), fn_GetLocationY(hero), res);
	return res;
}

static int cmd_gold(int n)      { return callIntCommand("AddGold", n); }
static int cmd_setgold(int n)   { return callIntCommand("SetGold", n); }
static int cmd_exp(int n)       { return callIntCommand("AddExperiencePoints", n); }
static int cmd_skill(int n)     { return callIntCommand("AddSkillPoints", n); }
static int cmd_param(int n)     { return callIntCommand("AddParamPoints", n); }
static int cmd_strength(int n)  { return callIntCommand("SetStrength", n); }
static int cmd_speed(int n)     { return setHeroSpeed(n); }
static int cmd_heal(int unused) { return callVoidCommand("heal"); }
static int cmd_god(int unused)  { return toggleGodmode(); }
static int cmd_mana(int unused) { return toggleInfMana(); }
static int cmd_infgold(int n)   { return toggleInfGold(n); }
static int cmd_cheats(int unused){ return callVoidCommand("TwoWorldsCheats"); }
static int cmd_fall(int amount) { return hitFall(amount); }
static int cmd_gates(int unused){ dumpGateFlags("jetzt"); return 1; }
static int cmd_unlock(int unused){ return unlockAround(0, 0); }
static int cmd_lockpick(int v)  { return setLockpicking(v); }

/* trainer.tpon - schaltet Teleporter in Reichweite dauerhaft frei.
 * Anders als der Byte-Patch, der nur die Abfragen austrickst, setzt
 * EnableTeleport das Flag am Objekt selbst - das landet damit auch im
 * Savegame und wirkt ohne Trainer weiter. */
static int cmd_tpon(int unused){
	TW_Hero* hero = info->TWFuncs->getActiveHero();
	if(hero == 0){ printf("[TWTrainer] tpon: kein Held\n"); return 0; }
	if(fn_SearchUnitsCount == 0 || fn_GetSearchUnit == 0 || fn_IsTeleport == 0
			|| fn_EnableTeleport == 0){
		printf("[TWTrainer] tpon: EarthC-API nicht verfuegbar\n");
		return 0;
	}
	int count = fn_SearchUnitsCount(hero);
	int found = 0;
	for(int i = 0; i < count; i++){
		void *u = fn_GetSearchUnit(hero, i);
		if(u == 0 || !fn_IsTeleport(u)) continue;
		fn_EnableTeleport(u, 1);
		found++;
	}
	printf("[TWTrainer] tpon: %d Units geprueft, %d Teleporter freigeschaltet\n",
		count, found);
	if(found == 0)
		printf("[TWTrainer] tpon: keiner in Reichweite - naeher an den Teleporter\n");
	return found;
}

/* trainer.get <name> - aktuellen Wert einer Engine-Variablen anzeigen */
static int cmd_get(char *param){
	while(*param == ' ') param++;
	char name[128];
	if(sscanf(param, "%127s", name) < 1){
		printf("[TWTrainer] Nutzung: trainer.get <name>, z.B. trainer.get Engine.FarPlane\n");
		return 0;
	}
	return showValue(name);
}
static int cmd_skilllist(int unused){ return listSkills(); }

/* trainer.setskill <index> <wert> */
static int cmd_setskill(char *param){
	int idx = -1, val = 0;
	if(sscanf(param, "%d %d", &idx, &val) < 2){
		printf("[TWTrainer] Nutzung: trainer.setskill <index> <wert>\n");
		printf("[TWTrainer]   Indizes zeigt trainer.skilllist, "
			"Schlossknacken ist %d\n", SKILL_LOCKPICKING);
		return 0;
	}
	return setSkill(idx, val);
}
static int cmd_unlockopen(int unused){ return unlockAround(0, 1); }
static int cmd_unlockval(int v) { return unlockAround(v, 0); }
static int cmd_kill(int unused) { return killTarget(); }
static int cmd_killme(int unused){ return killHero(); }
static int cmd_revive(int unused){ return reviveHero(); }
static int cmd_cheatgate(int value){
	GATE_C = value;
	printf("[TWTrainer] Gate C (0xAB4174) = %d gesetzt\n", GATE_C);
	return GATE_C;
}
static int cmd_rate(int rate)   { return setGameRate(rate); }
static int cmd_time(int t)      { return callIntCommand("time", t); }
static int cmd_rescue(int unused){ return callVoidCommand("rescue"); }
static int cmd_fog(int range)   { return clearFogOfWar(range); }
static int cmd_skills(int n)    { return callIntCommand("InitSkills", n); }
static int cmd_hitHP(int n)     { return callIntCommand("hitHP", n); }
static int cmd_hitMana(int n)   { return callIntCommand("hitMana", n); }

static int cmd_hitPoison(int n) { return callIntCommand("hitPoison", n); }
static int cmd_healH(int unused){ return callVoidCommand("healH"); }
static int cmd_school(int n)    { return callIntCommand("StartMagicSchool", n); }
static int cmd_greatgame(int unused){ return callVoidCommand("ThisIsGreatGame"); }

/* String-Befehle: Objekte spawnen, Magie freischalten, Animation testen */
static int cmd_create(char *param){ return callStringCommand("Create", param); }
static int cmd_createed(char *param){ return callStringCommand("CreateEd", param); }
static int cmd_magic(char *param) { return callStringCommand("InitMagic", param); }
static int cmd_anim(char *param)  { return callStringCommand("PlayUnitAnim", param); }
static int cmd_item(char *param)  { return callStringCommand("ec.AddInventory", param); }
static int cmd_bskill(char *param){ return callStringCommand("AddBasicSkill", param); }
static int cmd_bpoint(char *param){ return callStringCommand("AddBasicPoint", param); }
static int cmd_head(char *param)  { return callStringCommand("SetHeadMesh", param); }
static int cmd_neck(char *param)  { return callStringCommand("SetNeckMesh", param); }

/* EarthC-Bruecke: ec.dbg nimmt beliebige Debug-Kommandos entgegen */
static int cmd_ec(char *param)    { return callStringCommand("ec.dbg", param); }

/* Quest-Steuerung zur Laufzeit - alles Function(STRING) der EarthC-Bruecke.
 * Die Parameter werden unveraendert durchgereicht, z.B.
 *   trainer.quest.state 385 2 */
static int cmd_qstate(char *param) { return callStringCommand("ec.SetQuestState", param); }
static int cmd_qadd(char *param)   { return callStringCommand("ec.AddQuest", param); }
static int cmd_qremove(char *param){ return callStringCommand("ec.RemoveQuest", param); }
static int cmd_qpos(char *param)   { return callStringCommand("ec.SetQuestPosition", param); }

/* trainer.line <beliebige Konsolenzeile> - nutzt denselben Parser wie das
 * Autostart-Skript und kann daher auch Engine-Variablen setzen. */
static int cmd_line(char *param){ return execLine(param); }

/* trainer.script <datei> - Konsolenbefehle aus einer Datei ausfuehren */
static int cmd_script(char *param){
	while(*param == ' ' || *param == '\t') param++;
	if(*param == 0) param = "test.txt";
	return runScript(param);
}

/* trainer.exec <befehl> [wert] - generischer Aufruf */
static int cmd_exec(char *param){
	char name[128] = {0};
	int value = 0;
	int fields = sscanf(param, "%127s %d", name, &value);
	if(fields < 1){
		printf("[TWTrainer] Nutzung: trainer.exec <befehl> [wert]\n");
		return 0;
	}
	if(fields >= 2)
		return callIntCommand(name, value);
	return callVoidCommand(name);
}


/* --------------------------------------------------------- */
/* Pferd herholen                                            */
/* --------------------------------------------------------- */
/* Wird jeden Frame geprueft. Faengt der Held an zu pfeifen, wird das Pferd
 * einmal neben ihn gesetzt - nicht jeden Frame, sonst klebt es am Spieler
 * und laesst sich nicht besteigen.
 *
 * Der Versatz von 150 Einheiten haelt es aus dem Helden heraus; das Spiel
 * setzt es beim Positionieren ohnehin auf den Boden. Richtung ist die
 * Blickrichtung des Helden, damit es vor ihm steht.
 *
 * Ehrlich zur Unsicherheit: ob GetHorse() das Tier auch dann liefert, wenn
 * es weit weg oder in einer anderen Zone ist, konnte ich nicht messen. Wenn
 * nicht, meldet das Log "kein Pferd" und wir wissen es. */
static int g_pfiffZuvor = 0;
static int g_holePferd = 1;

static void horseTick(TW_Hero *hero){
	if(!g_holePferd || hero == 0) return;
	if(fn_IsCallingHorse == 0 || fn_GetHorse == 0 || fn_SetImmPos == 0) return;
	int pfeift = fn_IsCallingHorse(hero) != 0;
	if(pfeift && !g_pfiffZuvor){
		void *pferd = fn_GetHorse(hero);
		if(pferd == 0){
			printf("[TWTrainer] Pfiff: kein Pferd gefunden
");
		}else if(pferd != (void*)hero){
			int a = fn_GetDirAlpha(hero);
			/* 256 Schritte auf den Vollkreis, grob in acht Richtungen */
			static const int dx[8] = { 150, 106, 0,-106,-150,-106,  0, 106};
			static const int dy[8] = {   0, 106,150, 106,   0,-106,-150,-106};
			int i = ((a + 16) >> 5) & 7;
			int x = fn_GetLocationX((TW_Hero*)hero) + dx[i];
			int y = fn_GetLocationY((TW_Hero*)hero) + dy[i];
			int z = fn_GetLocationZ((TW_Hero*)hero);
			int res = fn_SetImmPos(pferd, x, y, z, a, 1);
			printf("[TWTrainer] Pferd geholt -> %d %d (res %d)
", x, y, res);
			strcpy(g_lastAction, "Pferd geholt");
		}
	}
	g_pfiffZuvor = pfeift;
}

static int cmd_horse(int an){
	g_holePferd = (an < 0) ? !g_holePferd : (an != 0);
	printf("[TWTrainer] Pferd beim Pfeifen holen: %s
",
		g_holePferd ? "AN" : "AUS");
	return g_holePferd;
}

/* Diagnose: die ersten Bytes von CallCallHorse ins Log, damit sich der
 * Rufradius im Maschinencode suchen laesst. Liest nur, aendert nichts. */
static int cmd_horsedump(int unused){
	(void)unused;
	if(!(info->EarthCApi && info->EarthCApi->functionsAvailable
	     && info->EarthCApi->functions)){
		printf("[TWTrainer] horsedump: API noch nicht da
");
		return 0;
	}
	unsigned char *p =
		(unsigned char*)info->EarthCApi->functions->CUnit__EC_CallCallHorse;
	printf("[TWTrainer] CallCallHorse @ %p
", (void*)p);
	for(int z = 0; z < 12; z++){
		char zeile[128]; int n = 0;
		for(int i = 0; i < 16; i++)
			n += sprintf(zeile + n, "%02x ", p[z*16 + i]);
		printf("[TWTrainer]   +%03x  %s
", z*16, zeile);
	}
	return 1;
}

/* --------------------------------------------------------- */
/* Hotkeys ueber den Debug-Hook (laeuft wiederholt)          */
/* --------------------------------------------------------- */
/* WICHTIG: addHook_PostMainLoop ist KEIN Per-Frame-Hook.
 * TWSE ruft die MainLoop-Hooks in MainLoopHook() so auf:
 *   callAllHooksAndRemove(&PreML);   // einmal vor dem Spiel
 *   TwoWorldsMainLoop();             // gesamte Spielschleife
 *   callAllHooksAndRemove(&PostML);  // erst beim Beenden
 * Wiederholt aufgerufen werden nur die Debug-Hooks: sie haengen am
 * Onscreen-Debug-Render-Call und nutzen callAllHooks() ohne Remove.
 * Darum haengt checkHotkeys an addHook_PostDebug. */

/* Nur noch das, was der Trainer wirklich besser kann als die Spielkonsole:
 * Godmode, Laufgeschwindigkeit, Ziel toeten, Schlossknacken. Gold, EP,
 * Skillpunkte und Heilen sind reine Vanilla-Befehle und daher raus - die
 * gibt es weiterhin ueber die Konsole (trainer.exec oder direkt).
 * Sprint bleibt unveraendert auf Shift. */
/* NUR_SPRINT: die Fassung, die mit der Kira-Kampagne ausgeliefert wird.
 * Uebrig bleibt Shift als Sprint - das ist eine Spielerweiterung, kein
 * Cheat. Alles andere waere in einer veroeffentlichten Mod fehl am Platz:
 * Godmode, unendlich Gold und Ziel-toeten gehoeren in ein Trainer-Plugin,
 * das man bewusst dazulegt, nicht in eine Kampagne.
 *
 * Die Tabelle darunter bleibt stehen. Ueber -DNUR_SPRINT=0 laesst sich die
 * volle Fassung bauen, ohne die Quelle anzufassen - der Installer bringt
 * beide DLLs mit und legt je nach Testmodus-Haken die eine oder die andere
 * ab. Eine zweite Quelldatei, die auseinanderlaufen kann, waere schlechter. */
#ifndef NUR_SPRINT
#define NUR_SPRINT 1
#endif

/* Je Aktion eine Taste auf dem Ziffernblock und, wo es Marco gebraucht hat,
 * eine Zweittaste auf dem Buchstabenfeld - das Surface hat keinen
 * Ziffernblock.
 *
 * Die Umlaut-Codes sind LAYOUTABHAENGIG. Die Werte hier gelten fuer das
 * deutsche QWERTZ-Layout:
 *     VK_OEM_1 (0xBA) = ue      VK_OEM_3 (0xC0) = oe
 *     VK_OEM_7 (0xDE) = ae
 * Auf einem anderen Layout liegen dort andere Zeichen; der Ziffernblock
 * bleibt in jedem Fall gueltig.
 *
 * Kein Strg davor, wie bei den Ziffernblocktasten auch: die F-Tasten
 * gehoeren dem Spiel und Strg+Buchstabe faengt es selbst ab. Wer im Spiel
 * gerade Text eingibt - etwa beim Benennen eines Spielstands - loest damit
 * auch den Trainer aus. Das gilt fuer den Ziffernblock genauso und ist
 * bewusst so gelassen; die Alternative waere ein Modifikator, den das Spiel
 * schluckt. */
#define NUM_HOTKEYS 6
#define KEIN_ZWEIT 0
static const int hotkeyVK[NUM_HOTKEYS][2] = {
	{VK_NUMPAD0, KEIN_ZWEIT},  /* Overlay ein/aus             */
	{VK_NUMPAD1, VK_OEM_1},    /* Schlossknacken auf 100   ue */
	{VK_NUMPAD2, VK_OEM_3},    /* Godmode                  oe */
	{VK_NUMPAD3, KEIN_ZWEIT},  /* Laufgeschwindigkeit 4/6/aus */
	{VK_NUMPAD4, VK_OEM_7},    /* anvisiertes Ziel toeten  ae */
	{VK_NUMPAD5, KEIN_ZWEIT}   /* unendlich Gold              */
};
static int hotkeyDown[NUM_HOTKEYS] = {0, 0, 0, 0, 0, 0};

static void runHotkey(int idx){
	switch(idx){
		case 0:
			g_overlay = !g_overlay;
			if(!g_overlay){
				dbgSetLine(OVL_LINE, ""); dbgSetLine(OVL_LINE + 1, "");
				dbgSetLine(OVL_LINE + 2, "");
				DBG_GATE = 0;   /* sonst bleibt die Debug-Anzeige des Spiels stehen */
			}
			printf("[TWTrainer] Overlay %s\n", g_overlay ? "AN" : "AUS");
			break;
		case 1: setLockpicking(100); strcpy(g_lastAction, "Schlossknacken 100"); break;
		case 2: toggleGodmode();     strcpy(g_lastAction, "Godmode umgeschaltet"); break;
		case 3: sprintf(g_lastAction, "Speed %dx", cycleSpeed()); break;
		case 4: killTarget();        strcpy(g_lastAction, "Ziel getoetet"); break;
		case 5: sprintf(g_lastAction, "Unendlich Gold %s",
			toggleInfGold(-1) ? "AN" : "AUS"); break;
	}
}

static int g_cheatsActivated = 0;
static int g_frameHookSeen = 0;
static int g_gatesInGame = 0;
static int g_delDown = 0;
static int g_np1Down = 0;

static void checkHotkeys(void *RES){
	TW_Hero* heroNow = info->TWFuncs->getActiveHero();

	/* Einmalige Bestaetigung, dass der Hook ueberhaupt wiederholt laeuft */
	if(!g_frameHookSeen){
		g_frameHookSeen = 1;
		printf("[TWTrainer] Frame-Hook aktiv (Hotkeys/Godmode laufen)\n");
		dumpDebugGlobals();
		dumpGateFlags("im Menue");
	}
	/* Sobald ein Spielstand geladen ist, die Gates messen - im Hauptmenue
	 * sind viele Zustaende noch 0. */
	if(!g_gatesInGame && heroNow != 0){
		g_gatesInGame = 1;
		dumpGateFlags("im Spiel");
	}
	/* EarthC-API nachtraeglich uebernehmen, sobald das Spiel sie bereitstellt */
	resolveGameFuncs();

	/* Cheat-Modus und Autostart-Skript laufen NICHT im Hauptmenue, sondern
	 * erst wenn ein Spielstand geladen ist: vorher gibt es keinen Helden,
	 * und das Laden setzt Engine-Werte ohnehin wieder zurueck.
	 * Geht es zurueck ins Menue, wird zurueckgesetzt - beim naechsten
	 * geladenen Spielstand laeuft das Skript also erneut. */
	if(heroNow == 0){
		g_cheatsActivated = 0;
		g_gatesInGame = 0;
	}else if(!g_cheatsActivated){
		g_cheatsActivated = 1;
		/* Grafik IMMER. Diese Zeilen standen frueher in test.txt, zusammen
		 * mit drei Cheat-Befehlen - und weil das Abspecken den Aufruf von
		 * test.txt mit ausgeklammert hat, waeren Spielern der ausgelieferten
		 * Fassung Sichtweite, Graseinstellungen und der Occlusion-Fix
		 * verlorengegangen. Genau der Leucht-Artefakt, den Marco extra
		 * abgestellt hatte, waere zurueckgewesen.
		 *
		 * Getrennt statt gemeinsam: Engine.* braucht den Cheat-Modus nicht -
		 * autoexecEditor.con des SDK setzt Engine.FarPlane ohne jeden
		 * Cheat-Befehl davor. Sollte es doch klemmen, meldet runScript die
		 * fehlgeschlagenen Zeilen ins Log, dann sieht man es sofort. */
		runScript("kira_grafik.txt");
#if !NUR_SPRINT
		/* Schaltet die Konsolenbefehle des Spiels frei und faehrt das
		 * Cheat-Skript. In der Sprint-Fassung bleibt beides aus. */
		callVoidCommand("TwoWorldsCheats");
		runScript("test.txt");
#endif
	}
	/* Alle Tasten brauchen kein Strg: die F-Tasten gehoeren dem Spiel,
	 * Strg+Buchstabe faengt es selbst ab, und Entf sowie Bild-hoch/runter
	 * sind die Kamera. Ziffernblock und die drei Umlaute sind frei. */
	int ctrl = 0;  /* nicht mehr noetig, bleibt fuer runHotkey-Kompatibilitaet */
	(void)ctrl;
#if !NUR_SPRINT
	for(int i = 0; i < NUM_HOTKEYS; i++){
		int zweit = hotkeyVK[i][1];
		int pressed = (GetAsyncKeyState(hotkeyVK[i][0]) & 0x8000) != 0
		           || (zweit != KEIN_ZWEIT
		               && (GetAsyncKeyState(zweit) & 0x8000) != 0);
		if(pressed && !hotkeyDown[i]){ /* Flanke: nur einmal pro Tastendruck */
			runHotkey(i);
		}
		hotkeyDown[i] = pressed;
	}
#endif
	horseTick(heroNow);
	/* Godmode / unendlich Mana / Speed jeden Frame aufrechterhalten */
	godmodeTick();
	speedTick();
}

/* --------------------------------------------------------- */
/* Plugin-Registrierung                                      */
/* --------------------------------------------------------- */

static void initCommands(void *RES){
	/* EarthC-Funktionszeiger aufloesen (Godmode). Klappt hier oft noch
	 * nicht - checkHotkeys versucht es dann jeden Frame erneut. */
	resolveGameFuncs();
	if(!g_ecResolved)
		printf("[TWTrainer] EarthC-API noch nicht bereit, vorerst feste Adressen (1.7)\n");

	/* Eigene Befehle in der Spiel-Konsole registrieren */
	/* Pferd. horse schaltet das Herholen beim Pfeifen an oder aus,
	 * horsedump legt den Maschinencode des Ruf-Befehls ins Log. */
	info->addCommand_Advanced("trainer.horse",    (void *)cmd_horse,
		TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.horsedump",(void *)cmd_horsedump,
		TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.gold",    (void *)cmd_gold,     TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.setgold", (void *)cmd_setgold,  TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.exp",     (void *)cmd_exp,      TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.skill",   (void *)cmd_skill,    TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.param",   (void *)cmd_param,    TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.str",     (void *)cmd_strength, TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.speed",   (void *)cmd_speed,    TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.heal",    (void *)cmd_heal,     TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.god",     (void *)cmd_god,      TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.mana",    (void *)cmd_mana,     TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.infgold", (void *)cmd_infgold,  TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.cheats",  (void *)cmd_cheats,   TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.teleports",(void *)cmd_teleports,TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.overlay", (void *)cmd_overlay,  TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.fall",    (void *)cmd_fall,     TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.kill",    (void *)cmd_kill,     TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.killme",  (void *)cmd_killme,   TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.revive",  (void *)cmd_revive,   TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.rate",    (void *)cmd_rate,     TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.time",    (void *)cmd_time,     TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.rescue",  (void *)cmd_rescue,   TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.fog",     (void *)cmd_fog,      TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.gates",   (void *)cmd_gates,    TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.unlock",  (void *)cmd_unlock,   TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.lockpick",(void *)cmd_lockpick, TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_String("trainer.get", cmd_get);
	info->addCommand_Advanced("trainer.tpon",    (void *)cmd_tpon,     TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.skilllist",(void *)cmd_skilllist,TW_CMD_NONE,TW_CMD_INT);
	info->addCommand_String("trainer.setskill", cmd_setskill);
	info->addCommand_Advanced("trainer.unlockopen",(void *)cmd_unlockopen,TW_CMD_NONE,TW_CMD_INT);
	info->addCommand_Advanced("trainer.unlockval",(void *)cmd_unlockval,TW_CMD_INT, TW_CMD_INT);
	info->addCommand_Advanced("trainer.cheatgate",(void *)cmd_cheatgate,TW_CMD_INT, TW_CMD_INT);
	info->addCommand_String("trainer.tp", cmd_tp);
	info->addCommand_Advanced("trainer.skills",  (void *)cmd_skills,   TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.hithp",   (void *)cmd_hitHP,    TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.hitmana", (void *)cmd_hitMana,  TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.hitpoison",(void *)cmd_hitPoison,TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.healh",   (void *)cmd_healH,    TW_CMD_NONE, TW_CMD_INT);
	info->addCommand_Advanced("trainer.school",  (void *)cmd_school,   TW_CMD_INT,  TW_CMD_INT);
	info->addCommand_Advanced("trainer.greatgame",(void *)cmd_greatgame,TW_CMD_NONE,TW_CMD_INT);
	info->addCommand_String("trainer.create",   cmd_create);
	info->addCommand_String("trainer.created",  cmd_createed);
	info->addCommand_String("trainer.magic",    cmd_magic);
	info->addCommand_String("trainer.anim",     cmd_anim);
	info->addCommand_String("trainer.item",     cmd_item);
	info->addCommand_String("trainer.bskill",   cmd_bskill);
	info->addCommand_String("trainer.bpoint",   cmd_bpoint);
	info->addCommand_String("trainer.head",     cmd_head);
	info->addCommand_String("trainer.neck",     cmd_neck);
	info->addCommand_String("trainer.ec",       cmd_ec);
	info->addCommand_String("trainer.line",     cmd_line);
	/* Quests zur Laufzeit steuern */
	info->addCommand_String("trainer.quest.state",  cmd_qstate);
	info->addCommand_String("trainer.quest.add",    cmd_qadd);
	info->addCommand_String("trainer.quest.remove", cmd_qremove);
	info->addCommand_String("trainer.quest.pos",    cmd_qpos);
	info->addCommand_String("trainer.exec", cmd_exec);
	info->addCommand_String("trainer.script", cmd_script);

	/* Teleport-Netz von Anfang an komplett freischalten */
	applyTeleportsPatch();

	/* Hotkeys/Godmode wiederholt pruefen - siehe Kommentar bei checkHotkeys:
	 * PostMainLoop feuert erst beim Spielende, PostDebug dagegen laufend. */
	info->addHook_PostDebug((_GenericCallback)checkHotkeys);

	/* Overlay direkt vor dem Rendern des Debug-Puffers schreiben */
	info->addHook_PreDebug((_GenericCallback)drawOverlay);

	printf("[TWTrainer] geladen - Hotkeys Strg+F1..F8 aktiv, Konsole: trainer.*\n");
}

#define REQVER 1
#define PLUGINVER 3
#define PLUGINREV 28

EXPORT int WINAPI InitPlugin(TWSE_INFO* gInfo, _GetFork gf){
	info = gInfo;
	info->addHook_PreMainLoop((_GenericCallback)initCommands);
	return 0;
}

EXPORT int WINAPI InfoExchange(INFO_EXCHANGE* exch, _GetFork gf){ return 0; }

PLUGIN_INFO THIS_PLUG_INFO = {
	APIVersion: CURVER,
	Version: PLUGINVER,
	Revision: PLUGINREV,
	Name: L"TW Trainer",
	Description: L"Trainer: Gold, EP, Skillpunkte, Heilung, Speed, Godmode und Mana per Hotkey (F1-F8) oder Konsole (trainer.*)",
	Credits: L"Erstellt mit TWSE von buglord",
	License: LICENSE_CC0,
0};

EXPORT int WINAPI PluginInfo(PLUGIN_INFO** pp_info, _GetFork gf){
	PLUGIN_INFO* p_info = *pp_info;
	*pp_info = &THIS_PLUG_INFO;
	if(p_info->APIVersion < REQVER){
		return ERR_LOADER_OUT_OF_DATE;
	}
	if(p_info->Version != 1700){
		return ERR_GAMEVERSION_UNSUPPORTED; /* nur Spielversion 1.7 */
	}
	return 0;
}
