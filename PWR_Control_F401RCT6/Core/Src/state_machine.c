// #include <comms_legacy.h>
#include "state_machine.h"
#include "config.h"
#include "injection_and_flow.h"
#include "main.h"
#include "tim.h"
#include "mks42d.h"
#include "motor_control.h"

volatile SysState_t cur_state = SYS_STARTUP_SEQUENCE;

/* handshake timeout: configured default here (ms) but could be added to secondary config later */
volatile uint32_t handshake_timeout_ms = DEFAULT_HANDSHAKE_TIMEOUT;

/* store the tick when we entered pairing */
static uint32_t pairing_enter_tick = 0;

/* startup internal variables */
static uint8_t startup_step = 0;
static uint32_t step_timer_tick = 0;

extern volatile uint32_t SYSTEM_TICK;
extern volatile uint16_t telemetry_period_ms;
extern volatile uint8_t self_op_enabled;

/* The startup sequence is similar to your earlier RunStartupSequence but uses ticks */
void RunStartupSequence(void) {
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
                HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, 1);
            }
            break;
        case 2:
            if ((now - step_timer_tick) >= MS_TO_TICKS(5000)) {
                HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2, 1);
                setZero(0x03);
                step_timer_tick = now;
                startup_step = 3;
            }
            break;
        case 3:
            if (readSetZeroAck() == 1) {
                HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, 1);
                step_timer_tick = now;
                startup_step = 4;
            }
            break;
        case 4:
            if ((now - step_timer_tick) >= MS_TO_TICKS(5000)) {
                /* Startup finished -> move to PAIRING */
                /* If self_op_enabled then go to STANDALONE, else go to PAIRING and wait for handshake */
                if (self_op_enabled) {
                    cur_state = SYS_STANDALONE_OPERATION;
                } else {
                    StateMachine_EnterPairing();
                }
                //startup_step = 0;
            }
            break;
        default:
            startup_step = 0;
            break;
    }
}


void StateMachine_Init(void) {
    cur_state = SYS_STARTUP_SEQUENCE;
    // FlowSchedule_Clear();
    startup_step = 0;
    step_timer_tick = SYSTEM_TICK;
    pairing_enter_tick = 0;
    /* ensure safe outputs disabled until configured */
    // e.g. set pump duty = 0; stepper disable here if required
}

SysState_t StateMachine_GetState(void) {
    return cur_state;
}

uint8_t StateMachine_GetStartupStep(void) {
    return startup_step;
}

/* Called by Comms when a primary handshake is validated and will be explicitly ACKed */
void StateMachine_OnHandshakeAccepted(void)
{
    if (cur_state != SYS_PAIRING)
    {
        return; // ignore handshake if not in pairing
    }

    cur_state = SYS_RUNNING_PI;
}

/* Called to trigger fatal error */
void StateMachine_TriggerFatal(void) {
    cur_state = SYS_ERROR_SHUTDOWN;
    FlowSchedule_Clear();
    // user must ensure hardware outputs are disabled by calling appropriate APIs
}

void StateMachine_EnterDebug(void)
{
    /* only allowed to enter debug from SYS_RUNNING_PI */
    if (cur_state == SYS_RUNNING_PI) {
        cur_state = SYS_DEBUG;
    }
}

void StateMachine_ExitDebug(void)
{
    /* only allowed to exit debug back to running PI */
    if (cur_state == SYS_DEBUG) {
        /* Clear all debug enable flags so we don't immediately re-enter SYS_DEBUG */
        pwm_debug_enabled = 0;
        echo_debug_enabled = 0;
        manual_pwm_enabled = 0;
        // manual_pwm_duty = 0;
        solenoid_test_enabled = 0;

        /* restore safe PWM compare to zero to be defensive */
        __HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, 0);

        cur_state = SYS_RUNNING_PI;
    }
}

/* in StateMachine_ProcessTick add a case for SYS_DEBUG and modify SYS_RUNNING_PI check to optionally move into SYS_DEBUG */
void StateMachine_ProcessTick(void) {
    uint32_t now = SYSTEM_TICK;

    switch (cur_state) {
        case SYS_STARTUP_SEQUENCE:
            RunStartupSequence();
            break;

        case SYS_PAIRING:
            if (pairing_enter_tick == 0) pairing_enter_tick = now;
            if ((now - pairing_enter_tick) >= MS_TO_TICKS(handshake_timeout_ms)) {
                cur_state = SYS_STANDALONE_OPERATION;
            }
            break;

        case SYS_RUNNING_PI:
            /* If any debug mode has been enabled at runtime, move to SYS_DEBUG.
               This enforces "only enter SYS_DEBUG from SYS_RUNNING_PI". */
            if (pwm_debug_enabled || usb_serial_debug_enabled || echo_debug_enabled || manual_pwm_enabled) {
                StateMachine_EnterDebug();
                break;
            }

            /* Normal operation controlled by Pi. Flow schedule processed elsewhere. */
            FlowMeter_UpdateInstantaneous();
            FlowMeter_UpdateTotal();

            /* Also update secondary flowmeter */
            FlowMeter2_UpdateInstantaneous();
            FlowMeter2_UpdateTotal();

            /* update pump state using runtime flags (lookup table and PI) */
            if (!pwm_debug_enabled && !manual_pwm_enabled) {
                update_pump_state();

            } else {
                /* if pwm debug or manual pwm was set but we didn't transition (shouldn't happen),
                   ensure safe behavior: do not run PI */
            }
            Update_Solenoid_State(); // this needs be active always -- coupled with the update_pump_state() function;

            // this should set the stepper motor state: 
            motor_read();

            break;

        case SYS_DEBUG:
            /* In debug state: apply debug behaviors only. Exit only via MSG_EXIT_SYS_DEBUG.
               Manual PWM mode takes priority; otherwise if pwm_debug_enabled produce saw-wave.
               Echo and solenoid test run ONLY while in SYS_DEBUG.
            */
        	Update_Solenoid_State();

        	FlowMeter_UpdateInstantaneous();
			FlowMeter_UpdateTotal();

        	FlowMeter2_UpdateInstantaneous();
			FlowMeter2_UpdateTotal();

            if (manual_pwm_enabled) {
                /* ensure manual PWM enforced each tick */
                __HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, Pump_Control.duty_pump);
            } else if (pwm_debug_enabled) {
                GenerateSawWaveDebug();
            }

            /* Echo debug: non-blocking I/O handling */
            if (echo_debug_enabled) {
                extern void EchoDebug_Process(void);
                EchoDebug_Process();
            }

            /* Solenoid test: non-blocking toggling behavior */
            if (solenoid_test_enabled) {
                /* implement a small helper to toggle solenoid pin at ~1s intervals using SYSTEM_TICK */
                static uint32_t last_toggle_tick = 0;
                uint32_t now = SYSTEM_TICK;
                if (last_toggle_tick == 0) last_toggle_tick = now;
                if ((now - last_toggle_tick) >= MS_TO_TICKS(1000)) { // toggle every ~1000 ms
                    last_toggle_tick = now;
                    HAL_GPIO_TogglePin(SOLENOID_GPIO_PORT, SOLENOID_GPIO_PIN);
                }
            }
            break;

        case SYS_STANDALONE_OPERATION:
            /* autonomous operation */
        	// nothing for now
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
