#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "mks42d.h"
#include "computer_bridge.h"
#include "comms_app.h"
#include "config.h"

bool state = 0;
bool stepper_rx_check_start = false;
int32_t stepper_pos = 0;

#define OSCILLATE_DEFAULT_LOW_PULSES   8192   // 150 mm with GUI scale
#define OSCILLATE_DEFAULT_HIGH_PULSES  12288  // 225 mm with GUI scale
#define OSCILLATE_DEFAULT_SPEED_RPM    150
#define OSCILLATE_COMMAND_PERIOD_MS    1000
#define STEPPER_SLAVE_ADDR             0x03
#define STEPPER_ACCEL                  150

extern volatile uint32_t SYSTEM_TICK;

static bool oscillate_enabled = false;
static int32_t oscillate_low_target = OSCILLATE_DEFAULT_LOW_PULSES;
static int32_t oscillate_high_target = OSCILLATE_DEFAULT_HIGH_PULSES;
static int32_t oscillate_target = OSCILLATE_DEFAULT_HIGH_PULSES;
static uint16_t oscillate_speed = OSCILLATE_DEFAULT_SPEED_RPM;
static uint32_t oscillate_command_tick = 0;

static void StepperOscillate_IssueTarget(int32_t target)
{
    oscillate_target = target;
    oscillate_command_tick = SYSTEM_TICK;
    stepper_rx_check_start = false;
    positionMode2Run(STEPPER_SLAVE_ADDR, oscillate_speed, STEPPER_ACCEL, oscillate_target);
}

static void StepperOscillate_IssueNextTarget(void)
{
    int32_t next_target = (oscillate_target == oscillate_high_target)
        ? oscillate_low_target
        : oscillate_high_target;

    StepperOscillate_IssueTarget(next_target);
}

void StepperOscillate_Start(int32_t low_pulses, int32_t high_pulses, uint16_t speed_rpm)
{
    if (low_pulses == high_pulses) {
        low_pulses = OSCILLATE_DEFAULT_LOW_PULSES;
        high_pulses = OSCILLATE_DEFAULT_HIGH_PULSES;
    }
    if (low_pulses > high_pulses) {
        int32_t tmp = low_pulses;
        low_pulses = high_pulses;
        high_pulses = tmp;
    }
    if (speed_rpm == 0) {
        speed_rpm = OSCILLATE_DEFAULT_SPEED_RPM;
    }

    oscillate_low_target = low_pulses;
    oscillate_high_target = high_pulses;
    oscillate_speed = speed_rpm;
    oscillate_enabled = true;

    StepperOscillate_IssueTarget(oscillate_high_target);
}

void StepperOscillate_Stop(void)
{
    oscillate_enabled = false;
    stepper_rx_check_start = false;
}

static void StepperOscillate_Process(void)
{
    if (!oscillate_enabled) {
        return;
    }

    if ((SYSTEM_TICK - oscillate_command_tick) >= MS_TO_TICKS(OSCILLATE_COMMAND_PERIOD_MS)) {
        StepperOscillate_IssueNextTarget();
    }
}

static void Stepper_ReadPositionResponse(void)
{
    stepper_rx_check_start = !readStepperPos(0x03);
}

static void Stepper_ReadTelemetryPosition(void)
{
    readStepperPosTx(STEPPER_SLAVE_ADDR);
    stepper_rx_check_start = true;
}

void motor_test(void)
{
    if (motor_flag)
    {
        motor_flag = false;
        state ^= 1;
        if (state)
        {
            positionMode2Run(0x03, 1000, 150, 3100);
        }
        else
        {
            positionMode2Run(0x03, 1000, 150, 100);
        }
    }
}

void motor_read(void)
{
    if (motor_read_flag)
    {
        motor_read_flag = false;
        if (stepper_cmnd != 0)
        {
            switch (stepper_cmnd)
            {
                case GO_HOME:
                    StepperOscillate_Stop();
                    goHome(0x03);
                    break;
                case SET_ZERO:
                    StepperOscillate_Stop();
                    setZero(0x03);
                    break;
                case OSCILLATE_START:
                    StepperOscillate_Start(
                        oscillate_low_pulses,
                        oscillate_high_pulses,
                        oscillate_speed_rpm
                    );
                    break;
                case OSCILLATE_STOP:
                    StepperOscillate_Stop();
                    break;
                case SET_MIDDLE:
                    StepperOscillate_Stop();
                    positionMode2Run(0x03, 100, 150, 1600);
                    break;
                case SET_POSITION:
                    StepperOscillate_Stop();
                    positionMode2Run(0x03, 100, 150, set_pulses);
                    break;
                default:
                    break;
            }
            stepper_cmnd = 0;
        }
        else if (oscillate_enabled)
        {
            StepperOscillate_Process();
        }
        else
        {
            Stepper_ReadTelemetryPosition();
        }
    }
    if (stepper_rx_check_flag && stepper_rx_check_start)
    {
        stepper_rx_check_flag = false;
        Stepper_ReadPositionResponse();
    }
}
