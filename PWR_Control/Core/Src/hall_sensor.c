#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "hall_sensor.h"
#include "gpio.h"

bool hall_status = false;

void hall_status_check(void)
{
    if (hall_check_flag)
    {
        hall_check_flag = false;
        hall_status = HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_0);
    }
}