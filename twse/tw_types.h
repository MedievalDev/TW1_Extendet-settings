#ifndef TW_TYPES
#define TW_TYPES
//TODO check require: #include <stdlib.h>

//this file is used for TwoWorlds vanilla function signatures and data structures.
//so far, only version 1.7 of the game is supported.
//supporting other versions of the game may require major changes.

//exact type depends on content in data array
typedef struct _TW_expArr{
	void **Vtable;
	void *Data; //pointer to array
	DWORD Entries;
	DWORD Allocated;
	DWORD ExpandStep;
} TW_ExpandingArray_Base;

typedef BOOL (* SortingFunction)(void* a, void* b);
typedef struct _TW_expSArr{
	void **Vtable;
	void *Data; //pointer to array
	DWORD Entries;
	DWORD Allocated;
	DWORD ExpandStep;
	SortingFunction SortFunc;
} TW_ExpandingSortArray_Base;

typedef struct _TW_String{
	DWORD RefA;
	DWORD RefB;
	DWORD MaxLen;
	DWORD Length;
	char Text[]; //.MaxLen+4 bytes in size
} TW_String; //full size: .MaxLen+0x14

union _TW_MM{
	int i;
	unsigned int u;
	float f;
	void *p;
};
#define TW_CMD_FUNC 0x800
#define TW_CMD_LOCATION 0x0
#define TW_CMD_NONE 0x1
#define TW_CMD_INT 0x2
#define TW_CMD_UINT 0x3
#define TW_CMD_FLOAT 0x4
#define TW_CMD_STRING 0x5
typedef struct _TW_Command{
	TW_String* CommandString;
	TW_String* UnknownString;
	DWORD Flags;
	union _TW_MM Min;
	union _TW_MM Max;
	DWORD _UnknownA;
	DWORD _UnknownB;
	void *CommandTarget; //exact type depends on flags
	DWORD _UnknownC;
} TW_Command;

typedef struct _TW_UNK_PARAM{
	char _U_PAD1[0x3C];
	//0x3C
	DWORD WalkSpeed;
	//0x40
	DWORD RunSpeed;
	//0x44
} TW_UNK_Param;
typedef struct _TW_UNITHERO{
	void *Vtable;
	//0x4
	char _U_PAD1[0x06];
	//0xA
	WORD MoveSpeed;
	//0xC
	
} TW_UnitHero;

typedef struct _TW_HERO{
	void *Vtable;
	//0x4
	char _U_PAD1[0x20];
	//0x24
	TW_UNK_Param *_U_Param; //->MESH
	//0x28
	char _U_PAD2[0xE0];
	//0x108
	TW_UnitHero *UnitHero;
	//0x10C
	char _U_PAD3[0x04];
	//0x110
	BYTE RunFlags; // & 0x3
	char _U_PAD4[0x03];
	//0x114
} TW_Hero;

typedef TW_Hero* (*_GetHero)();

//Used for both reciving and sending GameCommandToUser
//returns 1 on success
typedef int (__stdcall * _GameCommandCall)(LPCWSTR playerName, char *data, size_t size);

#endif