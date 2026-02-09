#pragma once
#include <stdint.h>

typedef enum {
     SYS_STARTUP_SEQUENCE = 0,
     SYS_PAIRING,
     SYS_RUNNING_PI,
     SYS_STANDALONE_OPERATION,
     SYS_ERROR_SHUTDOWN
   } SysState_t;

void RunStartupSequence(void);
   
void StateMachine_Init(void);
void StateMachine_ProcessTick(void); // call in main loop
void StateMachine_OnHandshakeAccepted(void);
SysState_t StateMachine_GetState(void);
void StateMachine_TriggerFatal(void); // force error/shutdown
void StateMachine_EnterPairing(void);

extern volatile uint32_t handshake_timeout_ms;

uint8_t StateMachine_GetStartupStep(void);

