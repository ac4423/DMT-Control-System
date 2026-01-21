#ifndef FLOWMETER_H
#define FLOWMETER_H

#include "stm32f1xx_hal.h"
#include <stdint.h>

void FlowMeter_Init(void);
void FlowMeter_PulseCallback(void);   // call from TIM3 interrupt
void FlowMeter_Update(uint32_t dt_ms); // call periodically
float FlowMeter_GetFrequency(void);
float FlowMeter_GetFlow_Lmin(void);

#endif