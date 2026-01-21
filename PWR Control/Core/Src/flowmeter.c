#include "flowmeter.h"

#define FLOW_K_FACTOR 98.0f   // F = 98 * Q(L/min)

static volatile uint32_t pulse_count = 0;
static float last_frequency = 0.0f;
static float last_flow_lmin = 0.0f;

void FlowMeter_Init(void)
{
    pulse_count = 0;
    last_frequency = 0.0f;
    last_flow_lmin = 0.0f;
}

/**
 * Call this from HAL_TIM_IC_CaptureCallback (TIM3)
 */
void FlowMeter_PulseCallback(void)
{
    pulse_count++;
}

/**
 * Call this periodically (e.g. every 100 ms or 200 ms)
 * dt_ms = elapsed time in milliseconds since last call
 */
void FlowMeter_Update(uint32_t dt_ms)
{
    uint32_t pulses;

    __disable_irq();
    pulses = pulse_count;
    pulse_count = 0;
    __enable_irq();

    // Frequency in Hz
    last_frequency = (pulses * 1000.0f) / dt_ms;

    // Q = F / 98
    last_flow_lmin = last_frequency / FLOW_K_FACTOR;
}

float FlowMeter_GetFrequency(void)
{
    return last_frequency;
}

float FlowMeter_GetFlow_Lmin(void)
{
    return last_flow_lmin;
}