#ifndef INJECTION_AND_FLOW_H
#define INJECTION_AND_FLOW_H

#include "main.h"
#include <stdint.h>
#include "CONFIG.H"

typedef struct
{
    // --- Flow pulse counters ---
    volatile uint32_t pulse_count_window;
    volatile uint32_t pulse_count_total;

    // --- Short-term memory ring buffer ---
    volatile uint32_t short_term_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];
    volatile uint16_t short_term_index;
    volatile uint16_t short_term_count;

    // --- Flow and volume ---
    float last_flow_lmin;
    float total_litres;

#if RECORD_PULSE_TIMESTAMPS
    volatile uint16_t pulse_deltas[LONG_TERM_PULSE_ARRAY_CAPACITY];
    volatile uint32_t pulse_delta_index;
    volatile uint32_t delta_accumulator;
#endif

} FlowState_t;

typedef struct {
    // --- Pump output ---
    volatile uint32_t duty_pump;
    int pump_flag;
    uint16_t pump_counter;

    // --- Current active setpoint ---
    float instantaneous_desired_flow; // litres per minute (applied this tick)

    // --- PI controller ---
    float pi_integral;
    float kp;
    float ki;

    // --- Unified flow schedule ring buffer ---
    float flow_schedule[FLOW_SCHEDULE_LEN];  // desired flow for future ticks
    volatile uint16_t schedule_head;         // next slot to consume
    volatile uint16_t schedule_tail;         // next slot to write

} PumpControl_t;

extern volatile PumpControl_t Pump_Control;

/* Global instance */
extern volatile FlowState_t Flow_State;

/* API */
void InjectionAndFlow_Init(void);
void FlowMeter_PulseCallback(void);

void FlowMeter_UpdateInstantaneous(void);
void FlowMeter_UpdateTotal(void);

float FlowMeter_GetFlow_Lmin(void);
float FlowMeter_GetTotalLitres(void);

void update_pump_state(void);

#if RECORD_PULSE_TIMESTAMPS
uint32_t FlowMeter_GetPulseDeltaCount(void);
const volatile uint16_t* FlowMeter_GetPulseDeltas(void);
void FlowMeter_ResetPulseDeltas(void);
void FlowMeter_TickHook(void);
#endif

/* ================= Flow Schedule API ================= */

uint8_t FlowSchedule_Push(float flow_lmin);
uint8_t FlowSchedule_PushImmediate(float flow_lmin);
uint16_t FlowSchedule_Depth(void);
void FlowSchedule_Clear(void);

#endif