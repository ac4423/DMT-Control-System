#pragma once
#include <stdint.h>
#include "stm32f4xx_hal.h" // adjust for your STM family
#include <stdbool.h>

// Public API
void Comms_Init(USART_TypeDef *uart_inst); // binds to an USART, e.g. USART6
void Comms_Process(void);                  // call often in main loop
void Comms_SendTelemetry(void);            // send telemetry now
void Comms_SendAck(uint8_t seq);
void Comms_SendNack(uint8_t seq);
void Comms_SendHeartbeat(void);

// Registering optional callback for telemetry packing or events (not required)
typedef void (*Comms_OnHandshake_t)(uint16_t telemetry_ms, uint8_t send_ack);
void Comms_RegisterHandshakeCb(Comms_OnHandshake_t cb);

extern volatile uint16_t heartbeat_counter;

/* in comms.h (add) */
typedef void (*Comms_OnConfig_t)(uint8_t tag, const uint8_t *value, uint8_t len);

/* Register callback to be notified for each applied tag */
void Comms_RegisterConfigCb(Comms_OnConfig_t cb);

/* Apply TLV payload buffer (returns true if at least one recognised tag applied) */
bool Comms_ApplyConfigTLV(const uint8_t *payload, uint8_t len);

