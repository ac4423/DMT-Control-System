#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "mks42d.h"
#include "computer_bridge.h"

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
    if (motor_read_flag && run_state)
    {
        motor_read_flag = false;
        readStepperPosTx(0x03);
        stepper_rx_check_start = true;
    }
    if (stepper_rx_check_flag && stepper_rx_check_start)
    {
        stepper_rx_check_flag = false;
        stepper_rx_check_start = !readStepperPos(0x03);
    }
}