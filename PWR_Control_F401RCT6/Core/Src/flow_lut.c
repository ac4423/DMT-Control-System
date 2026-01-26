#include "flow_lut.h"
#include "injection_and_flow.h"
#include "usb_debug.h"
#include "stm32f4xx_hal.h"
#include <stdio.h>
#include "tim.h"
#if ENABLE_USB_SERIAL_DEBUG
#include "usbd_cdc_if.h"
#endif

/* --- General interpolation --- */
uint16_t FlowLUT_GetDutyForFlow(float desired_flow)
{
    if (FlowLUT.n_points == 0)
        return PUMP_DUTY_MIN;

    /* Clamp */
    if (desired_flow <= FlowLUT.points[0].flow_lmin)
        return FlowLUT.points[0].duty;
    if (desired_flow >= FlowLUT.points[FlowLUT.n_points - 1].flow_lmin)
        return FlowLUT.points[FlowLUT.n_points - 1].duty;

    /* Linear interpolation */
    for (size_t i = 0; i < FlowLUT.n_points - 1; i++) {
        FlowLUT_Point_t *p0 = &FlowLUT.points[i];
        FlowLUT_Point_t *p1 = &FlowLUT.points[i + 1];

        if (desired_flow >= p0->flow_lmin && desired_flow <= p1->flow_lmin) {
            float t = (desired_flow - p0->flow_lmin) / (p1->flow_lmin - p0->flow_lmin);
            return (uint16_t)(p0->duty + t * (p1->duty - p0->duty));
        }
    }

    return PUMP_DUTY_MAX; // fallback
}

/* --- Store new LUT in RAM --- */
void FlowLUT_SetPoints(FlowLUT_Point_t *new_points, size_t n)
{
    FlowLUT.points = new_points;
    FlowLUT.n_points = n;
}

/* --- LUT generation / "auto-tune" --- */
void FlowLUT_AutoTune(void)
{
    #define FLOW_LUT_MAX_POINTS ((PUMP_DUTY_MAX - PUMP_DUTY_MIN + CAL_STEP_DUTY) / CAL_STEP_DUTY)
		static FlowLUT_Point_t new_lut[FLOW_LUT_MAX_POINTS];
    size_t idx = 0;

    for (uint16_t duty = PUMP_DUTY_MIN; duty <= PUMP_DUTY_MAX; duty += CAL_STEP_DUTY) {
        if (idx >= FLOW_LUT_MAX_POINTS)
						{break;}; // safety guard

			
				Pump_Control.duty_pump = duty;
        __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, duty);

        /* Wait for stabilization */
        HAL_Delay(CAL_STABILIZE_MS);

        /* Measure flow */
        FlowMeter_UpdateInstantaneous();
        float measured_flow = FlowMeter_GetFlow_Lmin();

        /* Store in RAM LUT */
        new_lut[idx].duty = duty;
        new_lut[idx].flow_lmin = measured_flow;
        idx++;
    }

    /* Update LUT pointer */
    FlowLUT_SetPoints(new_lut, idx);
    // 
		
		// FlowLUT_SendToUSB(); // optional: send new LUT immediately for debugging
}
