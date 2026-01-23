/**
  ******************************************************************************
  * @file    injection_and_flow.c
  * @brief   Injection pump and flowmeter control module
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "gpio.h"
#include "injection_and_flow.h"
#include "stm32f1xx_hal.h"
#include "config.h"

uint32_t last_pulse_tick = 0;

#if RECORD_PULSE_TIMESTAMPS
    static volatile uint16_t pulse_deltas[LONG_TERM_PULSE_ARRAY_CAPACITY];
    static volatile uint32_t pulse_delta_index = 0;
    static volatile uint32_t delta_accumulator = 0;
#endif

// Long-term pulse counters
volatile uint32_t pulse_count_window = 0;
volatile uint32_t pulse_count_total = 0;

// Short-term memory ring buffer for last N pulses
volatile uint32_t short_term_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];
volatile uint16_t short_term_index = 0;  // next write position
volatile uint16_t short_term_count = 0;  // number of valid entries in buffer

// Flow and volume
float last_flow_lmin = 0.0f;
float total_litres = 0.0f;

volatile uint32_t duty_pump = 0; // maximum 49

/* Initialization */
void InjectionAndFlow_Init(void)
{
    pulse_count_window = 0;
    pulse_count_total = 0;
    last_flow_lmin = 0.0f;
    total_litres = 0.0f;

    short_term_index = 0;
    short_term_count = 0;

#if RECORD_PULSE_TIMESTAMPS
    pulse_delta_index = 0;
    delta_accumulator = 0;
#endif
}

#if RECORD_PULSE_TIMESTAMPS
uint32_t FlowMeter_GetPulseDeltaCount(void)
{
    return pulse_delta_index;
}

const volatile uint16_t* FlowMeter_GetPulseDeltas(void)
{
    return pulse_deltas;
}

void FlowMeter_ResetPulseDeltas(void)
{
    __disable_irq();
    pulse_delta_index = 0;
    delta_accumulator = 0;
    __enable_irq();
}

void FlowMeter_TickHook(void)
{
    delta_accumulator++;

    if (delta_accumulator >= (PULSE_DELTA_SOFT_MAX + 1)) {
        if (pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
            pulse_deltas[pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
        }
        delta_accumulator = 0;
    }
}
#endif

/**
 * Call on every pulse (TIM3 IC interrupt)
 */
void FlowMeter_PulseCallback(void)
{
    uint32_t now = tim6_tick; // current timestamp in ms
		last_pulse_tick = now;


    // --- Short-term buffer ---
    short_term_pulses[short_term_index] = now;
    short_term_index = (short_term_index + 1) % SHORT_TERM_PULSE_BUFFER_SIZE;
    if (short_term_count < SHORT_TERM_PULSE_BUFFER_SIZE) short_term_count++;

    // --- Long-term counting ---
    pulse_count_window++;
    total_litres += 1.0f / FLOW_PULSES_PER_LITRE;

#if RECORD_PULSE_TIMESTAMPS
    if (pulse_delta_index < LONG_TERM_PULSE_ARRAY_CAPACITY) {
        uint32_t d = delta_accumulator;

        if (d > PULSE_DELTA_SOFT_MAX) {
            pulse_deltas[pulse_delta_index++] = PULSE_OVERFLOW_MARKER;
        } else {
            pulse_deltas[pulse_delta_index++] = (uint16_t)d;
        }
    }
    delta_accumulator = 0;
#endif
}

/**
 * Update instantaneous flow (L/min) based on short-term buffer
 */
void FlowMeter_UpdateInstantaneous(void)
{
    __disable_irq();
    uint16_t count = short_term_count;
    uint16_t index = short_term_index;
    __enable_irq();

    if (count == 0) {
        last_flow_lmin = 0.0f;
        return;
    }

    uint32_t now = tim6_tick;
		
    uint32_t window_ticks = flowmeter_window_ticks;

		if ((uint32_t)(now - last_pulse_tick) > window_ticks) {
				last_flow_lmin = 0.0f;
				return;
		}
		
    uint16_t pulses_in_window = 0;
    uint16_t oldest_index =
        (index + SHORT_TERM_PULSE_BUFFER_SIZE - count) % SHORT_TERM_PULSE_BUFFER_SIZE;

    // Count pulses in window (rollover-safe)
    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index = (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        uint32_t t = short_term_pulses[buf_index];

        if ((uint32_t)(now - t) <= window_ticks) {
            pulses_in_window++;
        }
    }

    if (pulses_in_window < 2) {
        last_flow_lmin = 0.0f;
        return;
    }

    uint32_t t_first = 0xFFFFFFFF;
    uint32_t t_last = 0;

    // Find first and last pulse times in window
    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index = (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        uint32_t t = short_term_pulses[buf_index];

        if ((uint32_t)(now - t) <= window_ticks) {
            if (t < t_first) t_first = t;
            if (t > t_last)  t_last  = t;
        }
    }

    uint32_t delta_ticks = t_last - t_first;
    if (delta_ticks == 0) delta_ticks = 1;

    // pulses ? litres
    float litres = (float)(pulses_in_window - 1) / FLOW_PULSES_PER_LITRE;

    // ticks ? seconds
    float time_sec = ((float)delta_ticks * (float)TIM6_TICK_uS) / 1000000.0f;

    // litres/sec ? litres/min
    last_flow_lmin = litres / (time_sec / 60.0f);
}

/**
 * Update cumulative total volume
 */

/*
void FlowMeter_UpdateTotal(void)
{
    total_litres = (float)pulse_count_total / (float)FLOW_PULSES_PER_LITRE;
}
*/

float FlowMeter_GetFlow_Lmin(void)
{
    return last_flow_lmin;
}

float FlowMeter_GetTotalLitres(void)
{
    return total_litres;
}