#include "state_machine.h"
#include "config.h"
#include "comms.h"
#include "injection_and_flow.h"
#include "main.h"
#include "tim.h"
#include "mks42d.h"

/* Top-level states now explicitly defined in header (please ensure header updated accordingly) */
/* If your state_machine.h didn't contain these enums, add them:
   typedef enum {
     SYS_STARTUP_SEQUENCE = 0,
     SYS_PAIRING,
     SYS_RUNNING_PI,
     SYS_STANDALONE_OPERATION,
     SYS_ERROR_SHUTDOWN
   } SysState_t;
*/

static volatile SysState_t cur_state = SYS_STARTUP_SEQUENCE;

/* handshake timeout: configured default here (ms) but could be added to secondary config later */
static uint32_t handshake_timeout_ms = 5000;

/* store the tick when we entered pairing */
static uint32_t pairing_enter_tick = 0;

/* startup internal variables */
static uint8_t startup_step = 0;
static uint32_t step_timer_tick = 0;

extern volatile uint32_t SYSTEM_TICK;
extern volatile uint16_t telemetry_period_ms;
extern volatile uint8_t self_op_enabled;

/* The startup sequence is similar to your earlier RunStartupSequence but uses ticks */
static void RunStartupSequence(void) {
	#if SKIP_STARTUP_SEQUENCE
		// Immediately treat startup as complete
		if (self_op_enabled) {
			cur_state = SYS_STANDALONE_OPERATION;
		} else {
			StateMachine_EnterPairing();
		}
		startup_step = 0;
		return;
	#endif

    uint32_t now = SYSTEM_TICK;

    switch (startup_step) {
        case 0:
            goHome(0x03);
            step_timer_tick = now;
            startup_step = 1;
            break;
        case 1:
            if (readGoHomeFinishAck() == 1) {
                step_timer_tick = now;
                startup_step = 2;
            }
            break;
        case 2:
            if ((now - step_timer_tick) >= MS_TO_TICKS(5000)) {
                setZero(0x03);
                step_timer_tick = now;
                startup_step = 3;
            }
            break;
        case 3:
            if (readSetZeroAck() == 1) {
                step_timer_tick = now;
                startup_step = 4;
            }
            break;
        case 4:
            if ((now - step_timer_tick) >= MS_TO_TICKS(1000)) {
                positionMode2Run(0x03, 500, 50, 1600);
                step_timer_tick = now;
                startup_step = 5;
            }
            break;
        case 5:
            if ((now - step_timer_tick) >= MS_TO_TICKS(5000)) {
                /* Startup finished -> move to PAIRING */
                /* If self_op_enabled then go to STANDALONE, else go to PAIRING and wait for handshake */
                if (self_op_enabled) {
                    cur_state = SYS_STANDALONE_OPERATION;
                } else {
                    StateMachine_EnterPairing();
                }
                startup_step = 0;
            }
            break;
        default:
            startup_step = 0;
            break;
    }
}


void StateMachine_Init(void) {
    cur_state = SYS_STARTUP_SEQUENCE;
    FlowSchedule_Clear();
    startup_step = 0;
    step_timer_tick = SYSTEM_TICK;
    pairing_enter_tick = 0;
    /* ensure safe outputs disabled until configured */
    // e.g. set pump duty = 0; stepper disable here if required
}

SysState_t StateMachine_GetState(void) {
    return cur_state;
}

/* Called by Comms when a primary handshake is validated and will be explicitly ACKed */
void StateMachine_OnHandshakeAccepted(void) {
    /* handshake ACK must have already been sent by Comms parser */
    cur_state = SYS_RUNNING_PI;
}

/* Called to trigger fatal error */
void StateMachine_TriggerFatal(void) {
    cur_state = SYS_ERROR_SHUTDOWN;
    FlowSchedule_Clear();
    // user must ensure hardware outputs are disabled by calling appropriate APIs
}

/* call once per main loop iteration (or faster) */
void StateMachine_ProcessTick(void) {
    uint32_t now = SYSTEM_TICK;

    switch (cur_state) {
        case SYS_STARTUP_SEQUENCE:

            RunStartupSequence();
            break;

        case SYS_PAIRING:
            /* handshake timeout starts when we entered pairing */
            if (pairing_enter_tick == 0) pairing_enter_tick = now;
            if ((now - pairing_enter_tick) >= MS_TO_TICKS(handshake_timeout_ms)) {
                /* timed out without valid handshake -> go to standalone operation */
                cur_state = SYS_STANDALONE_OPERATION;
            }
            break;

        case SYS_RUNNING_PI:
            /* Normal operation controlled by Pi. Flow schedule processed elsewhere. */
            break;

        case SYS_STANDALONE_OPERATION:
            /* Run autonomous operation: hand off to flow schedule processing */
            break;

        case SYS_ERROR_SHUTDOWN:
            /* safe shutdown */
            break;

        default:
            break;
    }
}

/* Call this to move from startup sequence into PAIRING explicitly (e.g. after startup finished) */
void StateMachine_EnterPairing(void) {
    cur_state = SYS_PAIRING;
    pairing_enter_tick = SYSTEM_TICK;
}
