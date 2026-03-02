#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "mks42d.h"
#include "computer_bridge.h"
#include "comms_app.h"

bool state = 0;
bool stepper_rx_check_start = false;
int32_t stepper_pos = 0;

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
                    goHome(0x03);
                    break;
                case SET_MIDDLE:
                    positionMode2Run(0x03, 100, 50, 1600);
                    break;
                case SET_POSITION:
                    positionMode2Run(0x03, 100, 50, set_pulses);
                    break;
                default:
                    break;
            }
            stepper_cmnd = 0;
        }
        else
        {
            readStepperPosTx(0x03);
            stepper_rx_check_start = true;
        }
    }
    if (stepper_rx_check_flag && stepper_rx_check_start)
    {
        stepper_rx_check_flag = false;
        stepper_rx_check_start = !readStepperPos(0x03);
    }
}