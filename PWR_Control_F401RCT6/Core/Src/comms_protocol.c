/* comms_protocol.c
 *
 * Transport / parser layer.
 * Handles UART binding, framing, CRC, and parses incoming bytes.
 * Delivers complete validated packets to a registered callback.
 *
 * This file intentionally does NOT depend on state machine, flow,
 * or other application logic.
 */

#include "comms_protocol.h"
#include "uart_hal.h"
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include "tim.h"

/* Frame format */
#define COMMS_HDR 0xA5
#define COMMS_MAX_PAYLOAD 128

/* Parser state */
typedef enum { P_IDLE, P_TYPE, P_SEQ, P_LEN, P_PAYLOAD, P_CRC } ParseState_t;

static USART_TypeDef *comms_uart = NULL;

/* Parser runtime state */
static ParseState_t pstate = P_IDLE;
static uint8_t tmp_type = 0;
static uint8_t tmp_seq = 0;
static uint8_t tmp_len = 0;
static uint8_t payload_buf[COMMS_MAX_PAYLOAD];
static uint8_t payload_idx = 0;

/* last-good RX tick (kept internal; compatible with previous behavior) */
static uint32_t last_good_rx_tick = 0;

/* Upper-layer callback */
static CommsProtocol_OnPacket_t packet_cb = NULL;

/* Private helper to read a byte from the HAL wrapper */
static int _read_byte(uint8_t *out) {
    int16_t r = UartHAL_Read(comms_uart);
    if (r < 0) return 0;
    *out = (uint8_t)r;
    return 1;
}

/* Compute XOR CRC over MSGTYPE, SEQ, PAYLOAD */
static uint8_t xor_crc_calc(uint8_t msgType, uint8_t seq, const uint8_t *payload, uint8_t len) {
    uint8_t crc = msgType ^ seq;
    for (uint8_t i = 0; i < len; ++i) crc ^= payload[i];
    return crc;
}

/* Public API */

void CommsProtocol_Init(USART_TypeDef *uart_inst)
{
    comms_uart = uart_inst;
    if (comms_uart) {
        UartHAL_FlushRx(comms_uart);
    }
}

void CommsProtocol_RegisterPacketHandler(CommsProtocol_OnPacket_t cb)
{
    packet_cb = cb;
}

/* Send a framed packet (protocol-layer transmit).
 * Behavior: does nothing if UART not bound. Preserves original frame layout.
 */
void CommsProtocol_Send(uint8_t msgType,
                        uint8_t seq,
                        const uint8_t *payload,
                        uint8_t len)
{
    if (!comms_uart) return;

    uint8_t frame[6 + COMMS_MAX_PAYLOAD];
    uint8_t idx = 0;

    frame[idx++] = COMMS_HDR;
    frame[idx++] = msgType;
    frame[idx++] = seq;
    frame[idx++] = len;

    if (len && payload) {
        memcpy(&frame[idx], payload, len);
        idx += len;
    }

    /* CRC */
    uint8_t crc = xor_crc_calc(msgType, seq, payload ? payload : (const uint8_t *)"\0", len);
    frame[idx++] = crc;

    UartHAL_Send(comms_uart, frame, idx);
}

/* Process incoming bytes; parse frames and deliver validated packets */
void CommsProtocol_Process(void)
{
    if (!comms_uart) return;

    while (UartHAL_RxAvailable(comms_uart))
    {
        uint8_t b;
        if (!_read_byte(&b)) break;

        switch (pstate)
        {
            case P_IDLE:
                if (b == COMMS_HDR) pstate = P_TYPE;
                break;

            case P_TYPE:
                tmp_type = b;
                pstate = P_SEQ;
                break;

            case P_SEQ:
                tmp_seq = b;
                pstate = P_LEN;
                break;

            case P_LEN:
                tmp_len = b;
                payload_idx = 0;
                if (tmp_len == 0) pstate = P_CRC;
                else if (tmp_len <= COMMS_MAX_PAYLOAD) pstate = P_PAYLOAD;
                else pstate = P_IDLE; /* malformed length: abort */
                break;

            case P_PAYLOAD:
                payload_buf[payload_idx++] = b;
                if (payload_idx >= tmp_len) pstate = P_CRC;
                break;

            case P_CRC:
            {
                uint8_t crc_calc = xor_crc_calc(tmp_type, tmp_seq, payload_buf, tmp_len);

                if (crc_calc == b)
                {
                    /* mark last good RX time (keeps parity with legacy) */
                    last_good_rx_tick = SYSTEM_TICK;

                    /* deliver packet to upper layer */
                    if (packet_cb) {
                        packet_cb(tmp_type, tmp_seq, payload_buf, tmp_len);
                    }
                } else {
                    /* CRC mismatch - drop / ignore; upper layer decides if NACK should be sent */
                    if (packet_cb) {
                        /* Optionally deliver a zero-length packet with type indicating CRC error is not desired.
                           We keep parity with legacy: the legacy module sent NACK from application when it saw CRC mismatch.
                           So here we do not send anything; application will not be called for CRC mismatch. */
                    }
                }

                /* reset parser */
                pstate = P_IDLE;
                tmp_len = 0;
                payload_idx = 0;
                break;
            }

            default:
                pstate = P_IDLE;
                break;
        } /* switch */
    } /* while */
}
