#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "mks42d.h"

bool state = 0;

void motor_test(void)
{
    if (motor_flag)
    {
        motor_flag = false;
        state ^= 1;
        if (state)
        {
            positionMode2Run(0x03, 1000, 150, 11000)
        }
        else
        {
            positionMode2Run(0x03, 1000, 150, 1000)
        }
    }
}