#ifndef TWSE_PLUGIN
#define TWSE_PLUGIN
#include "tw_types.h"
#include "EarthCApi.h"

#define EXPORT __attribute__((dllexport))

#define CURVER 1

#define ERR_LOADER_OUT_OF_DATE 1
#define ERR_GAMEVERSION_UNSUPPORTED 2
#define ERR_FORK_INCOMPATIBILITY 3

#define LICENSE_CC0 L"CC0: No Rights Reserved"

typedef struct BYTE_MOD_SET {
	LPVOID dest;
	BYTE *oldBytes;
	BYTE *newBytes;
	size_t len;
} BYTE_MOD_SET;

typedef int(* _SafeReplace)(BYTE_MOD_SET* set);
typedef int(* _SafeReplaceMultiple)(BYTE_MOD_SET* sets, size_t num);
typedef void(* _GenericCallback)(LPVOID Reserved);
typedef void(* _SetGenericCallback)(_GenericCallback);
typedef void(* _AddGameCommandHook)(_GameCommandCall);

typedef void(* _Command)();
typedef int(* _AddCommand)(char *command, _Command commandFunc);
typedef int(* _StringCommand)(char *param);
typedef int(* _AddStringCommand)(char *command, _StringCommand commandFunc);
typedef int(* _AddAdvancedCommand)(char *command, void *func, int input, int output);
typedef int(* _AddAdvancedCommandMM)(char *command, void *func, int input, int output, void* min, void* max);
typedef int(* _AddNamedLocationMM)(char *command, void *ptr, int type, void* min, void* max);
typedef int(* _FuncReplace)(void *dest, void *old_func, void *new_func);
typedef void*(* _GetFork)(wchar_t* forkName);//TODO Verify

typedef TW_String*(* _AllocEmptyTWString)(size_t len);
typedef TW_String*(* _MakeTWString)(char *text);
typedef void(* _freeString)(TW_String* str);

typedef struct TW_FUNCS{
	_GetHero getActiveHero;
	_GameCommandCall sendGameCommandToUser;
	
} TWFUNCS;
typedef struct TW_GLOBALS{
	TW_ExpandingArray_Base* CommandList;
	TW_ExpandingArray_Base* CommandHistoryList;
	
} TWGLOBALS;
struct ECF{
	struct EarthCFunctions* functions;
	int functionsAvailable;
};

typedef struct TWSE_INFO_V1 {
	//version info
	DWORD SE_VERNUM;
	DWORD SE_REVNUM;
	DWORD TW_VERNUM;
	void* RESERVED_A[2];
	//vanilla
	TWFUNCS* TWFuncs; //structure with pointers to Vanilla Functions
	TWGLOBALS* TWGlobals; //structure with pointers to Vanilla Global Values
	struct ECF* EarthCApi; //Created by game, not available initially
	void* RESERVED_B[2];
	//semi vanilla
	_AddCommand addCommand;
	_AddNamedLocationMM addNamedLocation; //signed, unsigned or float only
	_AddStringCommand addCommand_String;
	_AddAdvancedCommand addCommand_Advanced;
	_AddAdvancedCommandMM addCommand_Advanced_MM; //lets you set min-max values
	_AddGameCommandHook addGameCommandToUserHook;
	void* RESERVED_MEM[2];//TODO Alloc and Free
	//TODO .text:0079CB20 tls_allocate_mem_? for alloc?
	_AllocEmptyTWString allocString;
	_MakeTWString makeString;
	_freeString freeString;
	void* RESERVED_C[11];//possibly for other network related functions
	//twse hooks
	_SetGenericCallback addHook_PreMainLoop;
	_SetGenericCallback addHook_PostMainLoop;
	_SetGenericCallback addHook_PreDebug;
	_SetGenericCallback addHook_PostDebug;
	void* RESERVED_D[16];
	//potentially unsafe memory edits
	_SafeReplace replaceByteSet;
	_SafeReplaceMultiple replaceMulipleByteSets;
	_FuncReplace replaceFunctionRelative;
	_FuncReplace replaceFunctionAbsolute;
	void* RESERVED_E[6];
} TWSE_INFO;

typedef struct PLUGIN_INFO_V1 {
	//set to CURVER, lets TWSE and the plugin communicate which API version they were compiled with.
	DWORD APIVersion;
	//PLUGIN_INFO passed to PluginInfo from TWSE contains TWSE_INFO.TW_VERNUM, providing version of the game.
	DWORD Version;
	DWORD Revision; //should update with every build.
	wchar_t *Name; //optional, filename used if not present
	wchar_t *Description; //optional
	wchar_t *Credits; //optional, may be convenient in the future
	wchar_t *License; //optional, may be convenient in the future
	wchar_t **Tags; //optional, array of tag pointers, may be convenient in the future
	
	//More additions may be added in the future, always check APIVersion field to know full structure
	//Newer Versions should not change existing fields
} PLUGIN_INFO;
struct MOD_LIST_ENTRY {
	char* fname;
	PLUGIN_INFO* pinfo;
	HANDLE lib; //can be used for getProcAddr for special cross-mod interactions
};
typedef struct MOD_LIST_ENTRY*(* _getModEntryA)(char*);
typedef struct MOD_LIST_ENTRY*(* _getModEntryW)(wchar_t*);
typedef struct INFO_EXCHANGE {
	_getModEntryA getModEntryByFilename;
	_getModEntryW getModEntryByModName;
	void* RESERVED[3];
	//TODO include functions:
	//- load order/dependancy functions
} INFO_EXCHANGE;

//functions required as of official V1 release
//_GetFork functions should return fork specific equivalents of the first parameter
//replace Plugin_Info pointer with the one from your plugin
EXPORT int WINAPI PluginInfo(PLUGIN_INFO**, _GetFork);
//exchange information between mods and request load order changes
EXPORT int WINAPI InfoExchange(INFO_EXCHANGE*, _GetFork);
//initializes the plugin, perform hooks and overrides
//this step respects load order
EXPORT int WINAPI InitPlugin(TWSE_INFO*, _GetFork);
/* TODO:
 * Remember to unify wording for as Plugin not Mod
 * Consider better standards for NamingSchemes?
 ** _func to F_func?
 ** try to use struct declarations right? without typedefs
 */
#endif