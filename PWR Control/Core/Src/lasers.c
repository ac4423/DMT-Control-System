#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "lasers.h"
#include "hall_sensor.h"

void lasers_shutdown(void)
{
    if (lasers_flag)
    {
        lasers_flag = false;
        if (hall_status)
        {
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, 1);
        }
        else
        {
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, 0);
        }
    }
}