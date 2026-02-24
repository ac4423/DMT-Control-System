#include <comms_legacy.h>
#include <comms_legacy.h>
#include "uart_hal.h"
#include "config.h"
#include "injection_and_flow.h"
#include "state_machine.h"
#include <string.h>
#include <tim.h>
#include <stdbool.h>

/* Message type definitions (choose values that do not conflict with existing ones) */
#define MSG_ACK                 0x01
#define MSG_NACK                0x02
#define MSG_TELEMETRY_PUSH      0x03
#define MSG_HANDSHAKE           0x10
#define MSG_CONFIG              0x11
#define MSG_HANDSHAKE_ACK       0x12
#define MSG_HEARTBEAT           0x13
#define MSG_DESIRED_FLOW        0x20
#define MSG_DESIRED_FLOW_IMMEDIATE 0x21

/* New debug function codes */
#define MSG_SET_PUMP_PWM        0x30  /* payload: [duty:1byte] -> forces SYS_DEBUG if accepted */
#define MSG_EXIT_SYS_DEBUG      0x31  /* no payload; when in SYS_DEBUG returns to SYS_RUNNING_PI */

/* Configurable behavior (default values in config.c can be overwritten by handshake) */
/*
volatile uint16_t telemetry_period_ms;
volatile uint16_t heartbeat_period_ms;
volatile uint8_t send_ack_and_nack_packets;
volatile uint8_t self_op_enabled;
*/
volatile uint16_t heartbeat_counter;

/* state access */
extern SysState_t StateMachine_GetState(void);

/* internal comms state */
static USART_TypeDef *comms_uart = NULL;
static uint8_t seq_counter = 0;

/* For minimal parser */
#define COMMS_HDR 0xA5
#define COMMS_MAX_PAYLOAD 128

/* simple XOR CRC across MSGTYPE..PAYLOAD bytes */
static uint8_t xor_crc(const uint8_t *data, uint8_t len) {
    uint8_t c = 0;
    for (uint8_t i = 0; i < len; ++i) c ^= data[i];
    return c;
}

/* Config callback registration */
static Comms_OnConfig_t config_cb = NULL;
void Comms_RegisterConfigCb(Comms_OnConfig_t cb) {
    config_cb = cb;
}

/*
 * Comms_ApplyConfigTLV
 *   Parse TLV payload buffer and apply recognized tags.
 *   Returns true if at least one tag was applied successfully.
 *
 *   This function preserves the same tag semantics you had:
 *     0x01: telemetry_period_ms (2 bytes LE)
 *     0x02: heartbeat_period_ms (2 bytes LE)
 *     0x03: PI_Kp (4 bytes float LE)
 *     0x04: PI_Ki (4 bytes float LE)
 *     0x05: ENABLE_PI_CONTROL (1 byte)
 *
 *   Unknown tags are ignored. Malformed tag (len overflow) stops parsing early.
 */
/* Comms_ApplyConfigTLV
 *   Parse TLV payload buffer and apply recognized tags.
 *   Returns true if at least one tag was applied successfully.
 */
bool Comms_ApplyConfigTLV(const uint8_t *payload, uint8_t len) {
    if (!payload || len == 0) return false;

    uint8_t idx = 0;
    bool any_applied = false;

    while (idx + 2 <= len) {
        uint8_t tag = payload[idx++];
        uint8_t tlen = payload[idx++];

        if ((uint16_t)idx + (uint16_t)tlen > (uint16_t)len) {
            /* malformed - stop */
            break;
        }

        switch (tag) {
            case CONFIG_TAG_TELEMETRY_PERIOD_MS:
                if (tlen == 2) {
                    uint16_t tp = (uint16_t)payload[idx] | ((uint16_t)payload[idx+1] << 8);
                    telemetry_period_ms = tp;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_HEARTBEAT_PERIOD_MS:
                if (tlen == 2) {
                    uint16_t hb = (uint16_t)payload[idx] | ((uint16_t)payload[idx+1] << 8);
                    heartbeat_period_ms = hb;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_PI_KP:
                if (tlen == 4) {
                    float kp;
                    memcpy(&kp, &payload[idx], 4);
                    PI_Kp = kp;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_PI_KI:
                if (tlen == 4) {
                    float ki;
                    memcpy(&ki, &payload[idx], 4);
                    PI_Ki = ki;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_ENABLE_PI_CONTROL:
                if (tlen == 1) {
                    ENABLE_PI_CONTROL = payload[idx] ? 1 : 0;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            /* --- New debug/runtime tags --- */
            case CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG:
                if (tlen == 1) {
                    usb_serial_debug_enabled = payload[idx] ? 1 : 0;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_SERIAL_SEND_MS:
                if (tlen == 2) {
                    uint16_t v = (uint16_t)payload[idx] | ((uint16_t)payload[idx+1] << 8);
                    serial_send_ms = v;
                    serial_send_ticks_threshold = MS_TO_TICKS(serial_send_ms);
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_PWM_DEBUG:
                if (tlen == 1) {
                    pwm_debug_enabled = payload[idx] ? 1 : 0;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_ENABLE_ECHO_DEBUG:
                if (tlen == 1) {
                    echo_debug_enabled = payload[idx] ? 1 : 0;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            /* --- Flow/pump params --- */
            case CONFIG_TAG_FLOW_WINDOW_MS:
                if (tlen == 2) {
                    uint16_t v = (uint16_t)payload[idx] | ((uint16_t)payload[idx+1] << 8);
                    flow_window_ms = v;
                    flowmeter_window_ticks = MS_TO_TICKS(flow_window_ms);
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_FLOW_PULSES_PER_LITRE:
                if (tlen == 4) {
                    uint32_t v = (uint32_t)payload[idx] |
                                 ((uint32_t)payload[idx+1] << 8) |
                                 ((uint32_t)payload[idx+2] << 16) |
                                 ((uint32_t)payload[idx+3] << 24);
                    flow_pulses_per_litre = v;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_ENABLE_LOOKUP_TABLE:
                if (tlen == 1) {
                    enable_lookup_table = payload[idx] ? 1 : 0;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_PUMP_SAMPLE_TIME_MS:
                if (tlen == 2) {
                    uint16_t v = (uint16_t)payload[idx] | ((uint16_t)payload[idx+1] << 8);
                    pump_sample_time_ms = v;
                    pump_ticks_threshold = MS_TO_TICKS(pump_sample_time_ms);
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            default:
                /* unknown tag -> ignore */
                break;
        }

        idx += tlen;
    }

    return any_applied;
}

/* --- frame builder --- */
/* Frame layout (outgoing):
   [HDR=0xA5][MSGTYPE][SEQ][LEN][PAYLOAD...][CRC]
   For payloads we include timestamp as first 4 bytes in all outgoing informative packets where required.
*/

static void _send_frame(uint8_t msgType, uint8_t seq, const uint8_t *payload, uint8_t len) {
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
    uint8_t crc = 0;
    /* CRC = XOR(MSGTYPE, SEQ, PAYLOAD...) */
    crc = msgType ^ seq;
    for (uint8_t i = 0; i < len; ++i) crc ^= ((payload) ? payload[i] : 0);
    frame[idx++] = crc;
    UartHAL_Send(comms_uart, frame, idx);
}

/* Public API */
void Comms_Init(USART_TypeDef *uart_inst) {
	/* Configurable behavior (default values in config.c can be overwritten by handshake) */

	heartbeat_counter = 0;
    comms_uart = uart_inst;
    if (comms_uart) {
        // UartHAL_Attach(comms_uart);
    	UartHAL_FlushRx(comms_uart);
        // Send 100 heartbeats immediately on init (debug burst)
        for (int i = 0; i < 1
        ; i++) {
            Comms_SendHeartbeat();
            HAL_Delay(10);
        // UartHAL_EnableRxIRQ(comms_uart, 1);  // re-enable RX interrupt
        }
    }
    // UartHAL_FlushRx(uart_inst);
}

/* Extern handshake callback */
static Comms_OnHandshake_t handshake_cb = NULL;
void Comms_RegisterHandshakeCb(Comms_OnHandshake_t cb) { handshake_cb = cb; }

/* Parser state and helpers (kept same structure as before) */
typedef enum { P_IDLE, P_TYPE, P_SEQ, P_LEN, P_PAYLOAD, P_CRC } ParseState_t;
static ParseState_t pstate = P_IDLE;
static uint8_t tmp_type = 0;
static uint8_t tmp_seq = 0;
static uint8_t tmp_len = 0;
static uint8_t payload_buf[COMMS_MAX_PAYLOAD];
static uint8_t payload_idx = 0;
static uint32_t last_good_rx_tick = 0;

static int _read_byte(uint8_t *out) {
    int16_t r = UartHAL_Read(comms_uart);
    if (r < 0) return 0;
    *out = (uint8_t)r;
    return 1;
}

/* Helper to write 32-bit timestamp to a buffer little endian */
static inline void write_u32_le(uint8_t *buf, uint32_t v) {
    buf[0] = (uint8_t)(v & 0xFF);
    buf[1] = (uint8_t)((v >> 8) & 0xFF);
    buf[2] = (uint8_t)((v >> 16) & 0xFF);
    buf[3] = (uint8_t)((v >> 24) & 0xFF);
}

/* Helper to read u32 LE from received payload */
static inline uint32_t read_u32_le(const uint8_t *buf) {
    return (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
}

/* Packet sends that include timestamp and state */
void Comms_SendAck(uint8_t seq) {
    if (!comms_uart) return;
    if (!send_ack_and_nack_packets) return;

    uint8_t payload[5];
    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)StateMachine_GetState();
    _send_frame(MSG_ACK, seq, payload, sizeof(payload));
}

void Comms_SendNack(uint8_t seq) {
    if (!comms_uart) return;
    if (!send_ack_and_nack_packets) return;

    uint8_t payload[5];
    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)StateMachine_GetState();
    _send_frame(MSG_NACK, seq, payload, sizeof(payload));
}

/* Telemetry: timestamp(4), state(1), flow(4), total_ml(4) -> total 13 bytes */
void Comms_SendTelemetry(void) {
    if (!comms_uart) return;
    uint8_t payload[13];
    uint32_t ts = SYSTEM_TICK;
    uint32_t flow = FlowMeter_GetFlow_mLmin();
    uint32_t total = FlowMeter_GetTotal_mL();
    write_u32_le(&payload[0], ts);
    payload[4] = (uint8_t)StateMachine_GetState();
    write_u32_le(&payload[5], flow);
    write_u32_le(&payload[9], total);
    _send_frame(MSG_TELEMETRY_PUSH, seq_counter++, payload, sizeof(payload));
}

/* Heartbeat: timestamp(4), state(1), optional free field (e.g. heartbeat counter) -> 5 bytes */

void Comms_SendHeartbeat(void)
{
    if (!comms_uart) return;

    SysState_t st = StateMachine_GetState();

    uint8_t payload[8];

    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)st;

    if (st == SYS_STARTUP_SEQUENCE) {
        payload[5] = StateMachine_GetStartupStep();
    } else {
        payload[5] = 0;
    }

    // 16-bit heartbeat counter (little endian)
    payload[6] = (uint8_t)(heartbeat_counter & 0xFF);
    payload[7] = (uint8_t)((heartbeat_counter >> 8) & 0xFF);

    heartbeat_counter++;

    _send_frame(MSG_HEARTBEAT, seq_counter++, payload, 8);
}

/* Parser: extended to handle handshake and config requests and flow requests*/
void Comms_Process(void)
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
                else
                {
                    if (tmp_len <= COMMS_MAX_PAYLOAD) pstate = P_PAYLOAD;
                    else
                    {
                        pstate = P_IDLE;
                    }
                }
                break;

            case P_PAYLOAD:
                payload_buf[payload_idx++] = b;
                if (payload_idx >= tmp_len) pstate = P_CRC;
                break;

            case P_CRC:
            {
                /* compute XOR CRC over MSGTYPE and SEQ and payload */
                uint8_t crc_calc = tmp_type ^ tmp_seq;
                for (uint8_t i = 0; i < tmp_len; ++i) crc_calc ^= payload_buf[i];

                if (crc_calc == b)
                {
                    last_good_rx_tick = SYSTEM_TICK;

                    switch (tmp_type)
                    {

                    case MSG_HANDSHAKE:
						{
							SysState_t st = StateMachine_GetState();

							if (st != SYS_PAIRING)
							{
								// handshake not allowed in any other state
								if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
								break;
							}

							if (tmp_len >= 5)
							{
								uint16_t hb = (uint16_t)payload_buf[0] | ((uint16_t)payload_buf[1] << 8);
								uint16_t tp = (uint16_t)payload_buf[2] | ((uint16_t)payload_buf[3] << 8);
								uint8_t send_ack = payload_buf[4];

								heartbeat_period_ms = hb;
								telemetry_period_ms = tp;
								send_ack_and_nack_packets = send_ack ? 1 : 0;

								uint8_t ack_payload[6];
								write_u32_le(&ack_payload[0], SYSTEM_TICK);
								ack_payload[4] = (uint8_t)st;
								ack_payload[5] = 0;

								_send_frame(MSG_HANDSHAKE_ACK, tmp_seq, ack_payload, sizeof(ack_payload));

								if (handshake_cb) handshake_cb(hb, send_ack);

								StateMachine_OnHandshakeAccepted();
							}
							else
							{
								if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
							}
							break;
						}

                    case MSG_CONFIG:
						{
							SysState_t st = StateMachine_GetState();

							if (st != SYS_PAIRING && st != SYS_RUNNING_PI)
							{
								if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
								break;
							}

							bool applied = Comms_ApplyConfigTLV(payload_buf, tmp_len);

							if (applied) {
								if (send_ack_and_nack_packets) Comms_SendAck(tmp_seq);
							} else {
								if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
							}
						}
						break;

                        /* case MSG_TERMS_UPDATE: // legacy single-packet update (kept for backward compatibility)
                            if (tmp_len >= 3)
                            {
                                uint16_t tp = (uint16_t)payload_buf[0] | ((uint16_t)payload_buf[1] << 8);
                                uint8_t sa = payload_buf[2];

                                telemetry_period_ms = tp;
                                send_ack_and_nack_packets = sa ? 1 : 0;

                                if (send_ack_and_nack_packets) Comms_SendAck(tmp_seq);
                            }
                            else
                            {
                                if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                            }
                            break; */

                        case MSG_DESIRED_FLOW:
                            if (tmp_len >= 4)
                            {
                                uint32_t flow = (uint32_t)payload_buf[0] |
                                                ((uint32_t)payload_buf[1] << 8) |
                                                ((uint32_t)payload_buf[2] << 16) |
                                                ((uint32_t)payload_buf[3] << 24);

                                uint8_t ok = FlowSchedule_Push(flow);

                                if (send_ack_and_nack_packets)
                                {
                                    if (ok) Comms_SendAck(tmp_seq);
                                    else Comms_SendNack(tmp_seq);
                                }
                            }
                            else
                            {
                                if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                            }
                            break;

                        case MSG_DESIRED_FLOW_IMMEDIATE:
                            if (tmp_len >= 4)
                            {
                                uint32_t flow = (uint32_t)payload_buf[0] |
                                                ((uint32_t)payload_buf[1] << 8) |
                                                ((uint32_t)payload_buf[2] << 16) |
                                                ((uint32_t)payload_buf[3] << 24);

                                FlowSchedule_PushImmediate(flow);

                                if (send_ack_and_nack_packets) Comms_SendAck(tmp_seq);
                            }
                            else
                            {
                                if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                            }
                            break;

                        case MSG_SET_PUMP_PWM:
                            /* payload: [duty:1byte] */
                            if (tmp_len >= 1) {
                                SysState_t st = StateMachine_GetState();
                                if (st != SYS_RUNNING_PI) {
                                    if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                                    break;
                                }

                                uint8_t duty = payload_buf[0];
                                if (duty > PUMP_DUTY_MAX) duty = PUMP_DUTY_MAX;

                                /* Apply immediate manual PWM duty and mark manual mode */
                                manual_pwm_duty = duty;
                                manual_pwm_enabled = 1;

                                /* set timer compare immediately; injection_and_flow uses same timer */
                                __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, manual_pwm_duty);

                                /* Enter SYS_DEBUG (state machine enforces allowed transitions) */
                                StateMachine_EnterDebug();

                                if (send_ack_and_nack_packets) Comms_SendAck(tmp_seq);
                            } else {
                                if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                            }
                            break;

                        case MSG_EXIT_SYS_DEBUG:
                            /* no payload, only valid in SYS_DEBUG */
                            {
                                SysState_t st = StateMachine_GetState();
                                if (st == SYS_DEBUG) {
                                    StateMachine_ExitDebug();
                                    if (send_ack_and_nack_packets) Comms_SendAck(tmp_seq);
                                } else {
                                    if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
                                }
                            }
                            break;

                        default:
							if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
							break;
                    } // switch tmp_type
                }
                else
                {
                    /* CRC mismatch */
                    if (send_ack_and_nack_packets) Comms_SendNack(tmp_seq);
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
        } // switch pstate
    } // while bytes
}

/* Comms tick: called frequently (main loop). Handles heartbeat and telemetry scheduling */
void Comms_Tick(void) {
    static uint32_t last_heartbeat_tick = 0;
    static uint32_t last_telemetry_tick = 0;

    uint32_t now = SYSTEM_TICK;

    /* Heartbeat must be sent even before handshake to indicate device alive and current state */
    uint32_t hb_period_ticks = MS_TO_TICKS(heartbeat_period_ms);
    if (hb_period_ticks == 0) hb_period_ticks = MS_TO_TICKS(DEFAULT_HEARTBEAT_PERIOD_MS); // this looks like it is for safety...

    if ((now - last_heartbeat_tick) >= hb_period_ticks) {
        last_heartbeat_tick = now;
        Comms_SendHeartbeat();
    }

    /* Only send telemetry once we've left startup/pairing */
	SysState_t st = StateMachine_GetState();
	if (st != SYS_RUNNING_PI && st != SYS_STANDALONE_OPERATION) {
		return;   // no telemetry yet
	}

    /* Telemetry controlled by telemetry_period_ms (secondary config or default) */
    uint32_t tel_period_ticks = MS_TO_TICKS(telemetry_period_ms);
    if (tel_period_ticks > 0 && (now - last_telemetry_tick) >= tel_period_ticks) {
        last_telemetry_tick = now;
        Comms_SendTelemetry();
    }
}
