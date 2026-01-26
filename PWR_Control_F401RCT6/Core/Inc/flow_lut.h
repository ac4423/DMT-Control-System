#pragma once
#include <stdint.h>
#include <stddef.h>

void FlowLUT_SendToUSB(void);

/* --- Duty limits --- */
#define PUMP_DUTY_MIN     0U
#define PUMP_DUTY_MAX     49U

/* --- Calibration parameters --- */
#define CAL_STEP_DUTY     5U       // duty increment during calibration
#define CAL_STABILIZE_MS  500      // wait time at each duty for flow to stabilize

/* --- Lookup table structure --- */
typedef struct {
    float flow_lmin;    // L/min
    uint16_t duty;      // 0..49
} FlowLUT_Point_t;

typedef struct {
    size_t n_points;
    FlowLUT_Point_t *points;
} FlowLUT_t;

/* --- Hard-coded LUT example --- */
#define LUT_SIZE 6
static FlowLUT_Point_t FlowLUT_Hardcoded[LUT_SIZE] = {
    {0.0f, 0},
    {2.0f, 10},
    {5.0f, 20},
    {8.0f, 30},
    {12.0f, 40},
    {15.0f, 49}
};

static FlowLUT_t FlowLUT = {LUT_SIZE, FlowLUT_Hardcoded};

uint16_t FlowLUT_GetDutyForFlow(float desired_flow);