#include "flowmeter.h"
#include "stm32f1xx_hal.h"

#define PULSES_PER_LITRE 5880.0f

static volatile uint32_t pulse_count_window = 0;
static volatile uint32_t pulse_count_total = 0;

static float last_flow_lmin = 0.0f;
static float total_litres = 0.0f;

void FlowMeter_Init(void)
{
    pulse_count_window = 0;
    pulse_count_total = 0;
    last_flow_lmin = 0.0f;
    total_litres = 0.0f;
}

/**
 * Call on every pulse (TIM3 IC interrupt)
 */
void FlowMeter_PulseCallback(void)
{
    pulse_count_window++;
    pulse_count_total++;
}

/**
 * window_ms = time window for instantaneous flow calc
 */
void FlowMeter_Update(float window_ms)
{
    uint32_t pulses;

    __disable_irq();
    pulses = pulse_count_window;
    pulse_count_window = 0;
    __enable_irq();

    // Convert pulses -> litres in window
    float litres = pulses / PULSES_PER_LITRE;

    // Convert to L/min
    float minutes = window_ms / 60000.0f;
    last_flow_lmin = litres / minutes;

    // Update cumulative volume
    total_litres = pulse_count_total / PULSES_PER_LITRE;
}

float FlowMeter_GetFlow_Lmin(void)
{
    return last_flow_lmin;
}

float FlowMeter_GetTotalLitres(void)
{
    return total_litres;
}