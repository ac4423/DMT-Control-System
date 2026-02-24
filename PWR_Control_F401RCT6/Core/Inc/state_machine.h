#pragma once
#include <stdint.h>

typedef enum {
     SYS_STARTUP_SEQUENCE = 0,
     SYS_PAIRING,
     SYS_RUNNING_PI,
	 SYS_DEBUG,
     SYS_STANDALONE_OPERATION,
     SYS_ERROR_SHUTDOWN
   } SysState_t;

extern volatile uint32_t handshake_timeout_ms;
/* existing prototypes */
void StateMachine_Init(void);
void StateMachine_OnHandshakeAccepted(void);
void StateMachine_TriggerFatal(void);
void StateMachine_ProcessTick(void);
void StateMachine_EnterPairing(void);

/* new APIs for debug state control (use these from comms) */
void StateMachine_EnterDebug(void);  /* only transitions if currently SYS_RUNNING_PI */
void StateMachine_ExitDebug(void);   /* only transitions if currently SYS_DEBUG */

SysState_t StateMachine_GetState(void);
uint8_t StateMachine_GetStartupStep(void);
