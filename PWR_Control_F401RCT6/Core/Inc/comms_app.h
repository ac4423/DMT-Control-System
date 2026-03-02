#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "stm32f4xx_hal.h"

/* Initialize application layer (internally calls CommsProtocol_Init) */
void Comms_Init(USART_TypeDef *uart_inst);

/* Called frequently in main loop */
void Comms_Process(void);

/* Periodic scheduler for heartbeat and telemetry */
void Comms_Tick(void);

/* Application-level packet send helpers */
void Comms_SendTelemetry(void);
void Comms_SendAck(uint8_t seq);
void Comms_SendNack(uint8_t seq);
void Comms_SendHeartbeat(void);

/* --- Handshake callback --- */
typedef void (*Comms_OnHandshake_t)(uint16_t telemetry_ms, uint8_t send_ack);
void Comms_RegisterHandshakeCb(Comms_OnHandshake_t cb);

/* --- Config TLV callback --- */
typedef void (*Comms_OnConfig_t)(uint8_t tag,
                                 const uint8_t *value,
                                 uint8_t len);

void Comms_RegisterConfigCb(Comms_OnConfig_t cb);

/* Apply TLV payload */
bool Comms_ApplyConfigTLV(const uint8_t *payload, uint8_t len);

/* Application-owned state */
extern volatile uint16_t heartbeat_counter;

/* Debug Functionality */

/* Non-blocking echo debug: called only when in SYS_DEBUG and echo_debug_enabled == 1 */
void EchoDebug_Process(void);

/* new: send & enqueue for flowmeter pulse debug */
void Comms_SendFlowmeterPulseDebug(uint32_t ts, uint8_t meter_id, uint32_t pulse_total);
void Comms_EnqueueFlowmeterPulse(uint32_t ts, uint8_t meter_id, uint32_t pulse_total);

static void Comms_DrainFlowPulseQueue(void);
                                 
extern uint8_t stepper_cmnd;
#define GO_HOME                 0x01
#define SET_MIDDLE              0x02
#define SET_POSITION            0x03
extern uint32_t set_pulses;
