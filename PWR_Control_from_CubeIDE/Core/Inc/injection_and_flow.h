#ifndef INJECTION_AND_FLOW_H
#define INJECTION_AND_FLOW_H

#include "main.h"
#include <stdint.h>
#include "CONFIG.H"

extern volatile uint32_t duty_pump;
extern int pump_flag;
extern uint16_t pump_counter;

void InjectionAndFlow_Init(void);
void FlowMeter_PulseCallback(void);

void FlowMeter_UpdateInstantaneous(void);
void FlowMeter_UpdateTotal(void);

float FlowMeter_GetFlow_Lmin(void);
float FlowMeter_GetTotalLitres(void);

void update_pump_state(void);


extern volatile uint32_t pulse_count_window;
extern volatile uint32_t pulse_count_total;

// Short-term memory ring buffer for last N pulses
extern volatile uint32_t short_term_pulses[SHORT_TERM_PULSE_BUFFER_SIZE];
extern volatile uint16_t short_term_index;  // next write position
extern volatile uint16_t short_term_count;  // number of valid entries in buffer

// Flow and volume
extern float last_flow_lmin;
extern float total_litres;

#if RECORD_PULSE_TIMESTAMPS
	uint32_t FlowMeter_GetPulseDeltaCount(void);
	const volatile uint16_t* FlowMeter_GetPulseDeltas(void);
	void FlowMeter_ResetPulseDeltas(void);
	void FlowMeter_TickHook(void);
#endif

#endif