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

// --- External HAL tick function ---
extern uint32_t HAL_GetTick(void);

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
    uint32_t now = HAL_GetTick(); // current timestamp in ms

    // --- Short-term buffer ---
    short_term_pulses[short_term_index] = now;
    short_term_index = (short_term_index + 1) % SHORT_TERM_PULSE_BUFFER_SIZE;
    if (short_term_count < SHORT_TERM_PULSE_BUFFER_SIZE) short_term_count++;

    // --- Long-term counting ---
    pulse_count_window++;
    pulse_count_total++;

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

    uint32_t now = HAL_GetTick();
    uint32_t window_start = now - FLOW_WINDOW_MS;

    // Count pulses in the short-term buffer that are inside the window
    uint16_t pulses_in_window = 0;
    uint16_t oldest_index = (index + SHORT_TERM_PULSE_BUFFER_SIZE - count) % SHORT_TERM_PULSE_BUFFER_SIZE;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index = (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        if (short_term_pulses[buf_index] >= window_start) {
            pulses_in_window++;
        }
    }

    if (pulses_in_window < 2) {
        last_flow_lmin = 0.0f; // not enough pulses to calculate flow
        return;
    }

    // Time span of pulses in the window
    uint32_t t_first = 0xFFFFFFFF;
    uint32_t t_last = 0;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t buf_index = (oldest_index + i) % SHORT_TERM_PULSE_BUFFER_SIZE;
        uint32_t t = short_term_pulses[buf_index];
        if (t >= window_start) {
            if (t < t_first) t_first = t;
            if (t > t_last) t_last = t;
        }
    }

    uint32_t delta_ms = t_last - t_first;
    if (delta_ms == 0) delta_ms = 1;

    // Convert pulses to litres
    float litres = (float)(pulses_in_window - 1) / FLOW_PULSES_PER_LITRE;

    // Convert to L/min
    last_flow_lmin = litres / ((float)delta_ms / 60000.0f);
}

/**
 * Update cumulative total volume
 */
void FlowMeter_UpdateTotal(void)
{
    total_litres = (float)pulse_count_total / (float)FLOW_PULSES_PER_LITRE;
}

float FlowMeter_GetFlow_Lmin(void)
{
    return last_flow_lmin;
}

float FlowMeter_GetTotalLitres(void)
{
    return total_litres;
}