#include <math.h>
#include "gpio.h"
#include "injection_and_flow.h"
#include "stm32f4xx_hal.h"
#include "config.h"
#include "main.h"
#include "tim.h"
#include "usart.h"
#if ENABLE_USB_SERIAL_DEBUG
#include "usb_device.h"
#endif
#include "flow_lut.h"

/* Global flow state instance */
volatile FlowState_t Flow_State = {0};
volatile PumpControl_t Pump_Control;

/* --- External HAL tick function --- */
extern uint32_t HAL_GetTick(void);

/* debug flag */
volatile uint8_t debug_flag_1;
volatile uint16_t debug_ticker_1;

/* Initialization */
void InjectionAndFlow_Init(void)
{
    __disable_irq();

    Flow_State.pulse_count_window = 0;
    Flow_State.pulse_count_total = 0;

    Flow_State.short_term_index = 0;
    Flow_State.short_term_count = 0;

    Flow_State.last_flow_lmin = 0.0f;
    Flow_State.total_litres = 0.0f;

    Pump_Control.duty_pump = 0;
		__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);  // Ensure PWM = 0
    Pump_Control.pump_flag = 0;
    Pump_Control.pump_counter = 0;

		#if RECORD_PULSE_TIMESTAMPS
				Flow_State.pulse_delta_index = 0;
				Flow_State.delta_accumulator = 0;
		#endif
	
		#if ENABLE_PI_CONTROL
				Pump_Control.kp = PI_Kp;    // initial proportional gain
				Pump_Control.ki = PI_Ki;    // initial integral gain
				Pump_Control.pi_integral = 0.0f;
		#endif

    __enable_irq();
		
		//clear the buffer and flags for incoming desired flow requests...
		for (uint16_t i = 0; i < FLOW_SCHEDULE_LEN; i++) {
				Pump_Control.flow_schedule[i] = 0.0f;
		}
		Pump_Control.schedule_head = 0;
		Pump_Control.schedule_tail = 0;
		Pump_Control.instantaneous_desired_flow = 0.0f;
		
		// --- Clear short-term pulse buffer ---
		for (uint16_t i = 0; i < SHORT_TERM_PULSE_BUFFER_SIZE; i++) {
				Flow_State.short_term_pulses[i] = UNPOPULATED_ELEMENT_MARKER;
		}
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
 * Call on every pulse (TIM5 IC interrupt)
 */
void FlowMeter_PulseCallback(void)
{
    uint32_t now = HAL_GetTick();

    /* --- Short-term buffer --- */
    Flow_State.short_term_pulses[Flow_State.short_term_index] = now;
    Flow_State.short_term_index =
        (Flow_State.short_term_index + 1) % SHORT_TERM_PULSE_BUFFER_SIZE;

    if (Flow_State.short_term_count < SHORT_TERM_PULSE_BUFFER_SIZE)
        Flow_State.short_term_count++;

    /* --- Long-term counting --- */
    Flow_State.pulse_count_window++;
    Flow_State.pulse_count_total++;

#if RECORD_PULSE_TIMESTAMPS
    if (Flow_State.pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
        uint32_t d = Flow_State.delta_accumulator;

        if (d > PULSE_DELTA_SOFT_MAX)
            Flow_State.pulse_deltas[Flow_State.pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
        else
            Flow_State.pulse_deltas[Flow_State.pulse_delta_index++] = (uint16_t)d;
    }
    Flow_State.delta_accumulator = 0;
#endif
}

/**
 * Update instantaneous flow (L/min)
 */
void FlowMeter_UpdateInstantaneous(void)
{
    __disable_irq();
    uint16_t count = Flow_State.short_term_count;
    uint16_t index = Flow_State.short_term_index;
    __enable_irq();

    if (count == 0) {
        Flow_State.last_flow_lmin = 0.0f;
        return;
    }

    uint32_t now = HAL_GetTick();
    uint32_t window_start = now - FLOW_WINDOW_MS;

    uint16_t pulses_in_window = 0;
    uint16_t oldest_index =
        (index + SHORT_TERM_PULSE_BUFFER_SIZE - count) % SHORT_TERM_PULSE_BUFFER_SIZE;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index =
            (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        if (Flow_State.short_term_pulses[buf_index] >= window_start)
            pulses_in_window++;
    }

    if (pulses_in_window < 2) {
        Flow_State.last_flow_lmin = 0.0f;
        return;
    }

    uint32_t t_first = 0xFFFFFFFF;
    uint32_t t_last = 0;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index =
            (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        uint32_t t = Flow_State.short_term_pulses[buf_index];
        if (t >= window_start) {
            if (t < t_first) t_first = t;
            if (t > t_last) t_last = t;
        }
    }

    uint32_t delta_ms = t_last - t_first;
    if (delta_ms == 0) delta_ms = 1;

    float litres =
        (float)(pulses_in_window - 1) / FLOW_PULSES_PER_LITRE;

    Flow_State.last_flow_lmin =
        litres / ((float)delta_ms / 60000.0f);
}

/**
 * Update cumulative total volume
 */
void FlowMeter_UpdateTotal(void)
{
    Flow_State.total_litres =
        (float)Flow_State.pulse_count_total / (float)FLOW_PULSES_PER_LITRE;
}

float FlowMeter_GetFlow_Lmin(void)
{
    return Flow_State.last_flow_lmin;
}

float FlowMeter_GetTotalLitres(void)
{
    return Flow_State.total_litres;
}

#if ENABLE_PI_CONTROL
void PumpControl_UpdatePI(void)
{
    float error = Pump_Control.instantaneous_desired_flow - Flow_State.last_flow_lmin;

    // Convert sample time to seconds
    float dt = (float)PUMP_SAMPLE_TIME_MS / 1000.0f;

    // Update integral term
    Pump_Control.pi_integral += error * dt;

    // Compute PI output
    float duty = Pump_Control.kp * error + Pump_Control.ki * Pump_Control.pi_integral;

    // Clamp to limits
    if (duty < PUMP_DUTY_MIN) duty = PUMP_DUTY_MIN;
    if (duty > PUMP_DUTY_MAX) duty = PUMP_DUTY_MAX;

    Pump_Control.duty_pump = (uint32_t)duty;
}
#endif

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
		
		  float flow_diff = Pump_Control.instantaneous_desired_flow - Flow_State.last_flow_lmin;

		
		#if ENABLE_LOOKUP_TABLE
        if (fabsf(flow_diff) >= FLOW_DIFF_LUT_THRESHOLD) {
            // Only use LUT if difference is large
            Pump_Control.duty_pump = FlowLUT_GetDutyForFlow(Pump_Control.instantaneous_desired_flow);

            // Skip PI for this tick
        }
			#endif

        #if ENABLE_PI_CONTROL
            // Use PI controller only when LUT not triggered
            PumpControl_UpdatePI();
        #endif

        // Apply new pump duty
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, Pump_Control.duty_pump);
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

uint8_t FlowSchedule_Push(float flow_lmin)
{
    uint16_t head = Pump_Control.schedule_head;
    uint16_t tail = Pump_Control.schedule_tail;
    uint16_t next = (tail + 1) % FLOW_SCHEDULE_LEN;

    if (next == head)
        return 0; // buffer full

    Pump_Control.flow_schedule[tail] = flow_lmin;
    __DMB(); // ensure write completes before tail moves
    Pump_Control.schedule_tail = next;

    return 1;
}

uint8_t FlowSchedule_PushImmediate(float flow_lmin)
{
    __disable_irq();
    Pump_Control.schedule_head = 0;
    Pump_Control.schedule_tail = 0;

    // Push same value enough times to satisfy lookahead
    for (uint16_t i = 0; i < FLOW_SCHEDULE_MIN_LOOKAHEAD; i++) {
        Pump_Control.flow_schedule[i] = flow_lmin;
    }
    Pump_Control.schedule_tail = FLOW_SCHEDULE_MIN_LOOKAHEAD;
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
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, saw_pwm_duty);
    }
}






