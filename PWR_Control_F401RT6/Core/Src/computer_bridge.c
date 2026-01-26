#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "computer_bridge.h"
#include "uart_hal.h"
#include "motor_control.h"

bool run_state = 0;

static uint8_t txBuffer[64];
static uint8_t rxBuffer[64];

static inline USART_TypeDef* COM_BUS(void) { return USART2; }

void check_start(void)
{
    if (check_start_flag)
    {
        run_state = HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_1);
    }
}

void transmit_data(void)
{
    if (transmit_data_flag && run_state)
    {
        transmit_data_flag = false;
        UartHAL_FlushRx(COM_BUS());
        
        txBuffer[0] = 0xFF;
        txBuffer[1] = 0x00;
        txBuffer[2] = (uint8_t)((timer_sync_count) & 0xFF);
        txBuffer[3] = (uint8_t)((timer_sync_count >> 8) & 0xFF);
        txBuffer[4] = (uint8_t)((timer_sync_count >> 16) & 0xFF);
        txBuffer[5] = (uint8_t)((timer_sync_count >> 24) & 0xFF);
        txBuffer[6] = (uint8_t)((stepper_pos) & 0xFF);
        txBuffer[7] = (uint8_t)((stepper_pos >> 8) & 0xFF);
        txBuffer[8] = (uint8_t)((stepper_pos >> 16) & 0xFF);
        txBuffer[9] = (uint8_t)((stepper_pos >> 24) & 0xFF);
        
        UartHAL_Send(COM_BUS(), txBuffer, 10);
    }
}