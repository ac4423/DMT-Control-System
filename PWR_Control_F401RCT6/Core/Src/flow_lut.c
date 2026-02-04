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
uint16_t FlowLUT_GetDutyForFlow(uint32_t desired_flow_mlmin)
{
    if (FlowLUT.n_points == 0)
        return PUMP_DUTY_MIN;

    /* Clamp */
    if (desired_flow_mlmin <= FlowLUT.points[0].flow_mlmin)
        return FlowLUT.points[0].duty;
    if (desired_flow_mlmin >= FlowLUT.points[FlowLUT.n_points - 1].flow_mlmin)
        return FlowLUT.points[FlowLUT.n_points - 1].duty;

    /* Linear interpolation */
    for (size_t i = 0; i < FlowLUT.n_points - 1; i++) {
        FlowLUT_Point_t *p0 = &FlowLUT.points[i];
        FlowLUT_Point_t *p1 = &FlowLUT.points[i + 1];

        if (desired_flow_mlmin >= p0->flow_mlmin && desired_flow_mlmin <= p1->flow_mlmin) {

            uint32_t x0 = p0->flow_mlmin;
            uint32_t x1 = p1->flow_mlmin;
            uint16_t y0 = p0->duty;
            uint16_t y1 = p1->duty;

            if (x1 == x0)
                return y0;

            uint32_t num = (desired_flow_mlmin - x0);
            uint32_t den = (x1 - x0);

            uint32_t duty_interp =
                (uint32_t)y0 + ((uint32_t)(y1 - y0) * num) / den;

            return (uint16_t)duty_interp;
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
        uint32_t measured_flow_mlmin = FlowMeter_GetFlow_mLmin();

        /* Store in RAM LUT */
        new_lut[idx].duty = duty;
        new_lut[idx].flow_mlmin = measured_flow_mlmin;
        idx++;
    }

    /* Update LUT pointer */
    FlowLUT_SetPoints(new_lut, idx);
    FlowLUT_SendToUSB(); // optional: send new LUT immediately for debugging
}
