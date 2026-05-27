#include <math.h>
#include <stdlib.h>
#include "gpio.h"
#include "injection_and_flow.h"
#include "stm32f4xx_hal.h"
#include "config.h"
#include "main.h"
#include "tim.h"
#include "usart.h"
// #include "usb_device.h"
#include "flow_lut.h"
#include "comms_app.h" /* for Comms_EnqueueFlowmeterPulse() */
#include "state_machine.h" /* if not already included */

/* Global flow state instances */
volatile FlowState_t Flow_State = {0};
volatile FlowState_t Flow_State2 = {0}; /* secondary flowmeter */
volatile PumpControl_t Pump_Control;

/* --- External HAL tick function --- */
extern uint32_t HAL_GetTick(void);

/* Initialization */
void InjectionAndFlow_Init(void)
{
    __disable_irq();

    Flow_State.pulse_count_window = 0;
    Flow_State.pulse_count_total = 0;

    Flow_State.short_term_index = 0;
    Flow_State.short_term_count = 0;

    Flow_State.last_flow_mlmin = 0;
    Flow_State.total_ml = 0;

    Pump_Control.duty_pump = 0;
    __HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, 0);  // Ensure PWM = 0 (timer5)
    Pump_Control.pump_flag = 0;
    Pump_Control.pump_counter = 0;

    #if RECORD_PULSE_TIMESTAMPS
        Flow_State.pulse_delta_index = 0;
        Flow_State.delta_accumulator = 0;
    #endif

	Pump_Control.kp = DEFAULT_PI_Kp;    // initial proportional gain
	Pump_Control.ki = DEFAULT_PI_Ki;    // initial integral gain
	Pump_Control.pi_integral = 0.0f;

    __enable_irq();

    //clear the buffer and flags for incoming desired flow requests...
    for (uint16_t i = 0; i < FLOW_SCHEDULE_LEN; i++) {
        Pump_Control.flow_schedule[i] = 0;
    }
    Pump_Control.schedule_head = 0;
    Pump_Control.schedule_tail = 0;
    Pump_Control.instantaneous_desired_flow = 0;

    // --- Clear short-term pulse buffer ---
    for (uint16_t i = 0; i < SHORT_TERM_PULSE_BUFFER_SIZE; i++) {
        Flow_State.short_term_pulses[i] = UNPOPULATED_ELEMENT_MARKER;
    }

    // Force solenoid valve CLOSED on startup
    HAL_GPIO_WritePin(SOLENOID_GPIO_PORT, SOLENOID_GPIO_PIN, GPIO_PIN_RESET);

    Pump_Control.solenoid_flag = 0;
    Pump_Control.solenoid_counter = 0;

    /* --- Initialize secondary flowmeter state --- */
    Flow_State2.pulse_count_window = 0;
    Flow_State2.pulse_count_total = 0;
    Flow_State2.short_term_index = 0;
    Flow_State2.short_term_count = 0;
    Flow_State2.last_flow_mlmin = 0;
    Flow_State2.total_ml = 0;

    #if RECORD_PULSE_TIMESTAMPS
        Flow_State2.pulse_delta_index = 0;
        // Flow_State2.delta_accumulator maybe not needed for second if not recording - but set to 0
        Flow_State2.delta_accumulator = 0;
    #endif

    /* Clear short-term pulse buffer for meter2 */
    for (uint16_t i = 0; i < SHORT_TERM_PULSE_BUFFER_SIZE; i++) {
        Flow_State2.short_term_pulses[i] = UNPOPULATED_ELEMENT_MARKER;
    }

    flow2_window_ms = DEFAULT_FLOW2_WINDOW_MS;
    flow2_pulses_per_litre = DEFAULT_FLOW2_PULSES_PER_LITRE;
    flowmeter2_window_ticks = MS_TO_TICKS(flow2_window_ms);
}

#if RECORD_PULSE_TIMESTAMPS
uint32_t FlowMeter_GetPulseDeltaCount(void)
{
    return Flow_State.pulse_delta_index;
}

const volatile uint16_t* FlowMeter_GetPulseDeltas(void)
{
    return Flow_State.pulse_deltas;
}

void FlowMeter_ResetPulseDeltas(void)
{
    __disable_irq();
    Flow_State.pulse_delta_index = 0;
    Flow_State.delta_accumulator = 0;
    __enable_irq();
}

void FlowMeter_TickHook(void)
{
    Flow_State.delta_accumulator++;

    if (Flow_State.delta_accumulator >= (PULSE_DELTA_SOFT_MAX + 1)) {
        if (Flow_State.pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
            Flow_State.pulse_deltas[Flow_State.pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
        }
        Flow_State.delta_accumulator = 0;
    }
}
#endif

/**
 * Call on every pulse (TIM2 CH2 input capture)
 */
void FlowMeter_PulseCallback(void)
{
    uint32_t now = HAL_GetTick(); //otherwise: now = SYS_TICK

    /* --- Short-term buffer --- */
    Flow_State.short_term_pulses[Flow_State.short_term_index] = now;
    Flow_State.short_term_index =
        (Flow_State.short_term_index + 1) % SHORT_TERM_PULSE_BUFFER_SIZE;

    if (Flow_State.short_term_count < SHORT_TERM_PULSE_BUFFER_SIZE)
        Flow_State.short_term_count++;

    /* --- Long-term counting --- */
    Flow_State.pulse_count_window++;
    Flow_State.pulse_count_total++;

    /* --- NEW: enqueue a debug-packet event if enabled and in SYS_DEBUG --- */
    if (flowmeter_pulse_send_debug_enabled) {
        SysState_t st = StateMachine_GetState();
        if (st == SYS_DEBUG) {
            /* capture current tick (we already have 'now' earlier) and total */
            Comms_EnqueueFlowmeterPulse(now, 0, Flow_State.pulse_count_total); // 0 for injeciton pump meter
        }
    }

    if (RECORD_PULSE_TIMESTAMPS) {
    	if (Flow_State.pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
    	        uint32_t d = Flow_State.delta_accumulator;

    	        if (d > PULSE_DELTA_SOFT_MAX)
    	            Flow_State.pulse_deltas[Flow_State.pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
    	        else
    	            Flow_State.pulse_deltas[Flow_State.pulse_delta_index++] = (uint16_t)d;
    	    }
    	    Flow_State.delta_accumulator = 0;
    }

}

/**
 * Update instantaneous flow (mL/min)
 */

// race-free version according to GPT.
/*
void FlowMeter_UpdateInstantaneous(void)
{
    uint16_t count;
    uint16_t index;

    //* Local snapshot buffer (only copy what we need)
    uint32_t local_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];

    //* ---- Atomic Snapshot ----
    __disable_irq();

    count = Flow_State.short_term_count;
    index = Flow_State.short_term_index;

    if (count > SHORT_TERM_PULSE_BUFFER_SIZE)
        count = SHORT_TERM_PULSE_BUFFER_SIZE;

    uint16_t oldest_index =
        (index + SHORT_TERM_PULSE_BUFFER_SIZE - count) % SHORT_TERM_PULSE_BUFFER_SIZE;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index =
            (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;

        local_pulses[i] = Flow_State.short_term_pulses[buf_index];
    }

    __enable_irq();
    //* ---- End Atomic Snapshot ----


    if (count == 0) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    uint32_t now = HAL_GetTick();
    uint32_t window_start = now - flow_window_ms;

    uint16_t pulses_in_window = 0;

    for (uint16_t i = 0; i < count; i++) {
        if (local_pulses[i] >= window_start)
            pulses_in_window++;
    }

    if (pulses_in_window < 2) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    uint32_t t_first = 0xFFFFFFFF;
    uint32_t t_last  = 0;

    for (uint16_t i = 0; i < count; i++) {
        uint32_t t = local_pulses[i];
        if (t >= window_start) {
            if (t < t_first) t_first = t;
            if (t > t_last)  t_last  = t;
        }
    }

    uint32_t delta_ms = t_last - t_first;
    if (delta_ms == 0) delta_ms = 1;

    uint32_t ml =
        ((uint32_t)(pulses_in_window - 1) * 1000U) /
        (uint32_t)flow_pulses_per_litre;

    Flow_State.last_flow_mlmin =
        (uint32_t)(((uint64_t)ml * 60000ULL) /
                   (uint64_t)delta_ms);
}
*/

#include <math.h>  // for isnan, isfinite

void FlowMeter_UpdateInstantaneous(void)
{
    uint16_t count_snapshot;
    uint16_t index_snapshot;

    uint32_t local_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];

    /* -------- Acquire Stable Snapshot -------- */
    while (1)
    {
        __disable_irq();
        count_snapshot = Flow_State.short_term_count;
        index_snapshot = Flow_State.short_term_index;
        __enable_irq();

        if (count_snapshot < 2) {
            Flow_State.last_flow_mlmin = 0;
            return;
        }

        if (count_snapshot > SHORT_TERM_PULSE_BUFFER_SIZE)
            count_snapshot = SHORT_TERM_PULSE_BUFFER_SIZE;

        uint16_t oldest_index =
            (index_snapshot + SHORT_TERM_PULSE_BUFFER_SIZE - count_snapshot)
            % SHORT_TERM_PULSE_BUFFER_SIZE;

        for (uint16_t i = 0; i < count_snapshot; i++) {
            uint16_t buf_index =
                (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;

            local_pulses[i] = Flow_State.short_term_pulses[buf_index];
        }

        __disable_irq();
        uint16_t count_verify = Flow_State.short_term_count;
        uint16_t index_verify = Flow_State.short_term_index;
        __enable_irq();

        if (count_verify == count_snapshot &&
            index_verify == index_snapshot)
        {
            break;
        }

        /* else retry snapshot */
    }
    /* -------- End Snapshot -------- */

    uint32_t now = HAL_GetTick();

    /* sanity: window must be non-zero */
    if (flow_window_ms == 0) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    uint16_t pulses_in_window = 0;
    uint32_t t_first = 0;
    uint32_t t_last  = 0;
    uint8_t first_found = 0;

    /* ---- Wrap-safe windowing ---- */
    for (uint16_t i = 0; i < count_snapshot; i++) {
        uint32_t t = local_pulses[i];

        uint32_t age = now - t;        /* unsigned wrap-safe */

        if (age <= flow_window_ms) {
            if (!first_found) {
                t_first = t;
                first_found = 1;
            }
            t_last = t;
            pulses_in_window++;
        }
    }

    if (pulses_in_window < 2) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    /* Wrap-safe delta; should be >0 since pulses_in_window>=2 */
    uint32_t delta_ms = t_last - t_first;
    if (delta_ms == 0) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    /* Avoid division by zero for pulses-per-litre */
    uint32_t ppl = flow_pulses_per_litre;
    if (ppl == 0) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    /* ---- Frequency -> volumetric flow (float) ---- */
    float delta_s = (float)delta_ms / 1000.0f;
    float frequency = (float)(pulses_in_window - 1) / delta_s;   /* Hz */

    float flow_mlmin = frequency * (1000.0f * 60.0f) / (float)ppl;

    /* Defensive checks: NaN/Inf and clamp negative */
    if (!isfinite(flow_mlmin) || flow_mlmin <= 0.0f) {
        Flow_State.last_flow_mlmin = 0;
        return;
    }

    /* round-to-nearest and store */
    Flow_State.last_flow_mlmin = (uint32_t)(flow_mlmin + 0.5f);
}

/**
 * Update cumulative total volume (mL)
 */
void FlowMeter_UpdateTotal(void)
{
    Flow_State.total_ml =
        ((uint32_t)Flow_State.pulse_count_total * 1000U) / (uint32_t)flow_pulses_per_litre;
}

uint32_t FlowMeter_GetFlow_mLmin(void)
{
    return Flow_State.last_flow_mlmin;
}

uint32_t FlowMeter_GetTotal_mL(void)
{
    return Flow_State.total_ml;
}

void PumpControl_UpdatePI(void)
{
    /*
        PI loop still operates in float internally, but all flow values are now in mL/min integers.
        Convert to float only for controller math.
    */
    float error = (float)Pump_Control.instantaneous_desired_flow - (float)Flow_State.last_flow_mlmin;

    // Convert sample time to seconds
    float dt = (float)pump_sample_time_ms / 1000.0f;

    Pump_Control.pi_integral += error * dt;

    // Compute PI output
    float duty = Pump_Control.kp * error + Pump_Control.ki * Pump_Control.pi_integral;

    // Clamp to limits
    if (duty < PUMP_DUTY_MIN) duty = PUMP_DUTY_MIN;
    if (duty > PUMP_DUTY_MAX) duty = PUMP_DUTY_MAX;

    Pump_Control.duty_pump = (uint32_t)duty;
}

void update_pump_state(void)
{
    if (Pump_Control.pump_flag) {
        Pump_Control.pump_flag = 0;

        // --- Update desired flow from schedule safely with MIN_LOOKAHEAD ---
        uint16_t head = Pump_Control.schedule_head;
        uint16_t tail = Pump_Control.schedule_tail;

        // Compute next head index
        uint16_t next_head = (head + 1) % FLOW_SCHEDULE_LEN;

        // Compute safe tail position (distance must be > MIN_LOOKAHEAD)
        uint16_t distance;
        if (tail >= head)
            distance = tail - head;
        else
            distance = FLOW_SCHEDULE_LEN - (head - tail);

        if (distance > FLOW_SCHEDULE_MIN_LOOKAHEAD) {
            // Safe to advance head and consume next value
            Pump_Control.instantaneous_desired_flow = Pump_Control.flow_schedule[head];
            Pump_Control.schedule_head = next_head;
        } else {
            // Buffer too low: hold last value
            // instantaneous_desired_flow unchanged
        }

        int32_t flow_diff = (int32_t)Pump_Control.instantaneous_desired_flow - (int32_t)Flow_State.last_flow_mlmin;

        if (lookup_table_enabled) {
        	if (abs(flow_diff) >= FLOW_DIFF_LUT_THRESHOLD_MLMIN) {
				// Only use LUT if difference is large
				Pump_Control.duty_pump = FlowLUT_GetDutyForFlow(Pump_Control.instantaneous_desired_flow);

				// Skip PI for this tick
			}
        }

        if (pi_control_enabled) {
        	PumpControl_UpdatePI();
        }
            // Use PI controller

        // Apply new pump duty
        __HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, Pump_Control.duty_pump); // timer5 - channel 2 for PWM output
    }
}

// --------------- GPT-generated API: ------------------- //

inline uint16_t FlowSchedule_Depth(void)
{
    uint16_t head = Pump_Control.schedule_head;
    uint16_t tail = Pump_Control.schedule_tail;

    if (tail >= head)
        return tail - head;
    else
        return FLOW_SCHEDULE_LEN - (head - tail);
}

uint8_t FlowSchedule_Push(uint32_t flow_mlmin)
{
    uint16_t head = Pump_Control.schedule_head;
    uint16_t tail = Pump_Control.schedule_tail;
    uint16_t next = (tail + 1) % FLOW_SCHEDULE_LEN;

    if (next == head)
        return 0; // buffer full

    Pump_Control.flow_schedule[tail] = flow_mlmin;
    __DMB(); // ensure write completes before tail moves
    Pump_Control.schedule_tail = next;

    return 1;
}

uint8_t FlowSchedule_PushImmediate(uint32_t flow_mlmin)
{
    __disable_irq();
    Pump_Control.schedule_head = 0;
    Pump_Control.schedule_tail = 0;

    // Always push at least one entry for immediate requests
    Pump_Control.flow_schedule[0] = flow_mlmin;
    Pump_Control.schedule_tail = 1;

    __enable_irq();

    return 1;
}

void FlowSchedule_Clear(void)
{
    __disable_irq();
    Pump_Control.schedule_head = 0;
    Pump_Control.schedule_tail = 0;
    __enable_irq();
}

//

void Update_Solenoid_State(void)
{
    if (Pump_Control.solenoid_flag) {
        Pump_Control.solenoid_flag = 0;

        if (Pump_Control.duty_pump == 0) {
            HAL_GPIO_WritePin(SOLENOID_GPIO_PORT, SOLENOID_GPIO_PIN, 0);
        } else {
            HAL_GPIO_WritePin(SOLENOID_GPIO_PORT, SOLENOID_GPIO_PIN, 1);
        }
    }
}



// -------------------------------- Debugging: --------------------

void GenerateSawWaveDebug(void)
{
    if (debug_flag_1) {
        debug_flag_1 = 0;

        // Update duty in current direction
        if (saw_direction > 0) {
            if (saw_pwm_duty + SAW_PWM_STEP >= SAW_PWM_MAX) {
                saw_pwm_duty = SAW_PWM_MAX;
                saw_direction = -1;
            } else {
                saw_pwm_duty += SAW_PWM_STEP;
            }
        } else {
            if (saw_pwm_duty <= SAW_PWM_MIN + SAW_PWM_STEP) {
                saw_pwm_duty = SAW_PWM_MIN;
                saw_direction = 1;
            } else {
                saw_pwm_duty -= SAW_PWM_STEP;
            }
        }

        // Apply PWM directly (bypass PI/LUT)
        __HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, saw_pwm_duty);
    }
}

/* --------- second flow meter ------------ */

// config.h (add)
extern volatile uint16_t flow2_window_ms;           /* ms window for instantaneous calc */
extern volatile uint32_t flow2_pulses_per_litre;    /* pulses per litre for meter 2 */

/* (optional) ticks cached */
// extern volatile uint32_t flowmeter2_window_ticks;

/**
 * Call on every pulse from secondary flowmeter (TIMx IC interrupt)
 * - This should be invoked from the TIM IC capture callback for the configured pin/channel.
 */
void FlowMeter2_PulseCallback(void)
{
    uint32_t now = HAL_GetTick();

    /* short-term buffer (mirror primary) */
    Flow_State2.short_term_pulses[Flow_State2.short_term_index] = now;
    Flow_State2.short_term_index = (Flow_State2.short_term_index + 1) % SHORT_TERM_PULSE_BUFFER_SIZE;

    if (Flow_State2.short_term_count < SHORT_TERM_PULSE_BUFFER_SIZE)
        Flow_State2.short_term_count++;

    /* long-term counting */
    Flow_State2.pulse_count_window++;
    Flow_State2.pulse_count_total++;

    /* do not enqueue debug packet for flow2 (per your request) */

#if RECORD_PULSE_TIMESTAMPS
    if (Flow_State2.pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
        uint32_t d = Flow_State2.delta_accumulator;

        if (d > PULSE_DELTA_SOFT_MAX)
            Flow_State2.pulse_deltas[Flow_State2.pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
        else
            Flow_State2.pulse_deltas[Flow_State2.pulse_delta_index++] = (uint16_t)d;
    }
    Flow_State2.delta_accumulator = 0;
#endif
}

void FlowMeter2_UpdateInstantaneous(void)
{
    uint16_t count_snapshot;
    uint16_t index_snapshot;
    uint32_t local_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];

    /* Acquire stable snapshot (same retry approach as primary) */
    while (1)
    {
        __disable_irq();
        count_snapshot = Flow_State2.short_term_count;
        index_snapshot = Flow_State2.short_term_index;
        __enable_irq();

        if (count_snapshot < 2) {
            Flow_State2.last_flow_mlmin = 0;
            return;
        }

        if (count_snapshot > SHORT_TERM_PULSE_BUFFER_SIZE)
            count_snapshot = SHORT_TERM_PULSE_BUFFER_SIZE;

        uint16_t oldest_index =
            (index_snapshot + SHORT_TERM_PULSE_BUFFER_SIZE - count_snapshot)
            % SHORT_TERM_PULSE_BUFFER_SIZE;

        for (uint16_t i = 0; i < count_snapshot; i++) {
            uint16_t buf_index =
                (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;

            local_pulses[i] = Flow_State2.short_term_pulses[buf_index];
        }

        __disable_irq();
        uint16_t count_verify = Flow_State2.short_term_count;
        uint16_t index_verify = Flow_State2.short_term_index;
        __enable_irq();

        if (count_verify == count_snapshot &&
            index_verify == index_snapshot)
        {
            break;
        }

        /* else retry snapshot */
    }

    uint32_t now = HAL_GetTick();

    if (flow2_window_ms == 0) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    uint16_t pulses_in_window = 0;
    uint32_t t_first = 0;
    uint32_t t_last  = 0;
    uint8_t first_found = 0;

    for (uint16_t i = 0; i < count_snapshot; i++) {
        uint32_t t = local_pulses[i];
        uint32_t age = now - t;
        if (age <= flow2_window_ms) {
            if (!first_found) {
                t_first = t;
                first_found = 1;
            }
            t_last = t;
            pulses_in_window++;
        }
    }

    if (pulses_in_window < 2) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    uint32_t delta_ms = t_last - t_first;
    if (delta_ms == 0) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    /* Two pulses with an unrealistically short spacing => huge inferred Hz.
     * At genuine low flow, the first/last pulse in the window are far apart;
     * spikes (~hundreds L/min) are almost always this pathological case. */
    if (pulses_in_window == 2U && delta_ms < 15U) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    uint32_t ppl = flow2_pulses_per_litre;
    if (ppl == 0) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    float delta_s = (float)delta_ms / 1000.0f;
    float frequency = (float)(pulses_in_window - 1) / delta_s;   /* Hz */
    float flow_mlmin = frequency * (1000.0f * 60.0f) / (float)ppl;

    if (!isfinite(flow_mlmin) || flow_mlmin <= 0.0f) {
        Flow_State2.last_flow_mlmin = 0;
        return;
    }

    Flow_State2.last_flow_mlmin = (uint32_t)(flow_mlmin + 0.5f);
}

void FlowMeter2_UpdateTotal(void)
{
    Flow_State2.total_ml =
        ((uint32_t)Flow_State2.pulse_count_total * 1000U) / (uint32_t)flow2_pulses_per_litre;
}

uint32_t FlowMeter2_GetFlow_mLmin(void)
{
    return Flow_State2.last_flow_mlmin;
}

uint32_t FlowMeter2_GetTotal_mL(void)
{
    return Flow_State2.total_ml;
}

uint32_t FlowMeter2_GetPulseTotal(void)
{
    return Flow_State2.pulse_count_total;
}
