#ifndef FLOWMETER_H
#define FLOWMETER_H

#include <stdint.h>

void FlowMeter_Init(void);
void FlowMeter_PulseCallback(void);
void FlowMeter_Update(float window_ms);

float FlowMeter_GetFlow_Lmin(void);
float FlowMeter_GetTotalLitres(void);

#endif