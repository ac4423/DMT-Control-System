#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "stm32f4xx_hal.h" // adjust for your STM family

// Public API
void Comms_Init(USART_TypeDef *uart_inst); // binds to an USART, e.g. USART6
void Comms_Process(void);                  // call often in main loop
void Comms_SendTelemetry(void);            // send telemetry now
void Comms_SendAck(uint8_t seq);
void Comms_SendNack(uint8_t seq);
void Comms_SendHeartbeat(void);
void Comms_Tick(void);

extern uint8_t stepper_cmnd;
#define GO_HOME                 0x01
#define SET_MIDDLE              0x02
#define SET_POSITION            0x03
extern uint32_t set_pulses;

// Registering optional callback for telemetry packing or events (not required)
typedef void (*Comms_OnHandshake_t)(uint16_t telemetry_ms, uint8_t send_ack);
void Comms_RegisterHandshakeCb(Comms_OnHandshake_t cb);

extern volatile uint16_t heartbeat_counter;

