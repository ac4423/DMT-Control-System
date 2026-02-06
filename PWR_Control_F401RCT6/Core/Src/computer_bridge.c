#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include "main.h"
#include "computer_bridge.h"
#include "uart_hal.h"
#include "motor_control.h"
#include "config.h"
#include "state_machine.h"
#include "injection_and_flow.h"
#include "tim.h"

bool run_state = 1;

static uint8_t txBuffer[64];
static uint8_t rxBuffer[64];

static inline USART_TypeDef* COM_BUS(void) { return USART6; }

static uint32_t last_telemetry_ms = 0;

// Initialize communications for Pi (call this during startup)
void ComputerBridge_Init(void) {
    // Ensure USART6 is prepared in MX_USART6_UART_Init() and call UartHAL_Attach there,
    // but Comms_Init here ensures it's attached if not already.
    Comms_Init(USART6);
}
