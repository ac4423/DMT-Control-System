#ifndef INJECTION_AND_FLOW_H
#define INJECTION_AND_FLOW_H

#include "main.h"
#include <stdint.h>
#include "config.h"

#define SOLENOID_GPIO_PORT GPIOB
#define SOLENOID_GPIO_PIN  GPIO_PIN_12

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
    uint32_t last_flow_mlmin; // this has been renamed
    uint32_t total_ml;

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
    uint32_t instantaneous_desired_flow; // litres per minute (applied this tick)

    // --- PI controller ---
    float pi_integral;
    float kp;
    float ki;

    // --- Unified flow schedule ring buffer ---
    uint32_t flow_schedule[FLOW_SCHEDULE_LEN];  // desired flow for future ticks
    volatile uint16_t schedule_head;         // next slot to consume
    volatile uint16_t schedule_tail;         // next slot to write

    volatile uint8_t solenoid_flag;
    volatile uint32_t solenoid_counter;

} PumpControl_t;

extern volatile PumpControl_t Pump_Control;

/* Global instance */
extern volatile FlowState_t Flow_State;

/* debug flag */
extern volatile uint8_t debug_flag_1;
extern volatile uint16_t debug_ticker_1;

/* API */
void InjectionAndFlow_Init(void);
void FlowMeter_PulseCallback(void);

void FlowMeter_UpdateInstantaneous(void);
void FlowMeter_UpdateTotal(void);

uint32_t FlowMeter_GetFlow_mLmin(void);
uint32_t FlowMeter_GetTotal_mL(void);

void update_pump_state(void);

#if RECORD_PULSE_TIMESTAMPS
uint32_t FlowMeter_GetPulseDeltaCount(void);
const volatile uint16_t* FlowMeter_GetPulseDeltas(void);
void FlowMeter_ResetPulseDeltas(void);
void FlowMeter_TickHook(void);
#endif

/* ================= Flow Schedule API ================= */

uint8_t FlowSchedule_Push(uint32_t flow_lmin); /// add to ring buffer
uint8_t FlowSchedule_PushImmediate(uint32_t flow_lmin); // set the immediate flow rate (only required once)
uint16_t FlowSchedule_Depth(void);
void FlowSchedule_Clear(void);

/* ================= Other Functions ================= */

void PumpControl_UpdatePI(void);
void Update_Solenoid_State(void);

/* ================= Debugging ================= */

void GenerateSawWaveDebug(void);

#endif

/* ================= Coolant Loop Flowmeter ================= */

// injection_and_flow.h (additions)

/* Secondary flowmeter API and state (mirror primary) */
extern volatile FlowState_t Flow_State2;

/* Initialize second flowmeter state - called from InjectionAndFlow_Init() */
void FlowMeter2_Init(void);

/* ISR callback to be called by TIM IC handler for meter 2 */
void FlowMeter2_PulseCallback(void);

/* Instantaneous & total updates (called from StateMachine tick) */
void FlowMeter2_UpdateInstantaneous(void);
void FlowMeter2_UpdateTotal(void);

/* Accessors */
uint32_t FlowMeter2_GetFlow_mLmin(void);
uint32_t FlowMeter2_GetTotal_mL(void);
uint32_t FlowMeter2_GetPulseTotal(void);
