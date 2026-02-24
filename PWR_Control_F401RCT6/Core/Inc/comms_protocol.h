#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "stm32f4xx_hal.h"

/* Initialize protocol layer with UART instance */
void CommsProtocol_Init(USART_TypeDef *uart_inst);

/* Process incoming bytes and emit packets upward */
void CommsProtocol_Process(void);

/* Send a framed packet (raw message type + payload) */
void CommsProtocol_Send(uint8_t msgType,
                        uint8_t seq,
                        const uint8_t *payload,
                        uint8_t len);

/* Upper-layer packet callback */
typedef void (*CommsProtocol_OnPacket_t)(uint8_t type,
                                         uint8_t seq,
                                         const uint8_t *payload,
                                         uint8_t len);

void CommsProtocol_RegisterPacketHandler(CommsProtocol_OnPacket_t cb);
