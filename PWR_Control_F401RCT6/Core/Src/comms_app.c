/* comms_app.c
 *
 * Application-layer comms: message types, handshake, TLV parsing, telemetry,
 * heartbeat, command handling (flow, immediate flow, debug/PWM), ACK/NACK, etc.
 *
 * Uses comms_protocol to send frames and receive parsed packets.
 */

#include "comms_app.h"
#include "comms_protocol.h"
#include "uart_hal.h"
#include "config.h"
#include "injection_and_flow.h"
#include "state_machine.h"
#include <string.h>
#include <tim.h>
#include <stdbool.h>
#include <stdint.h>

/* Message type definitions (preserve original values) */
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

/* Application-owned state (preserve legacy) */
volatile uint16_t heartbeat_counter;

/* Sequence counter (legacy behavior) */
static uint8_t seq_counter = 0;

/* Callbacks (legacy registration) */
static Comms_OnHandshake_t handshake_cb = NULL;
static Comms_OnConfig_t config_cb = NULL;

/* Register callbacks */
void Comms_RegisterHandshakeCb(Comms_OnHandshake_t cb) { handshake_cb = cb; }
void Comms_RegisterConfigCb(Comms_OnConfig_t cb) { config_cb = cb; }

/* Helper to write/read 32-bit little-endian */
static inline void write_u32_le(uint8_t *buf, uint32_t v) {
    buf[0] = (uint8_t)(v & 0xFF);
    buf[1] = (uint8_t)((v >> 8) & 0xFF);
    buf[2] = (uint8_t)((v >> 16) & 0xFF);
    buf[3] = (uint8_t)((v >> 24) & 0xFF);
}

static inline uint32_t read_u32_le(const uint8_t *buf) {
    return (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
}

/* ---------------- TLV config parser (preserve exactly original tags & effects) ---------------- */

/* Apply TLV payload buffer and apply recognized tags.
 * Returns true if at least one tag was applied successfully.
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
                    Pump_Control.kp = kp;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_PI_KI:
                if (tlen == 4) {
                    float ki;
                    memcpy(&ki, &payload[idx], 4);
                    Pump_Control.ki = ki;
                    any_applied = true;
                    if (config_cb) config_cb(tag, &payload[idx], tlen);
                }
                break;

            case CONFIG_TAG_ENABLE_PI_CONTROL:
                if (tlen == 1) {
                    pi_control_enabled = payload[idx] ? 1 : 0;
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
                	lookup_table_enabled = payload[idx] ? 1 : 0;
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

/* ---------------- Frame sends (application building payloads) ---------------- */

/* ACK / NACK (include timestamp and state just like legacy) */
void Comms_SendAck(uint8_t seq) {
    if (!send_ack_and_nack_packets) return;

    uint8_t payload[5];
    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)StateMachine_GetState();
    CommsProtocol_Send(MSG_ACK, seq, payload, sizeof(payload));
}

void Comms_SendNack(uint8_t seq) {
    if (!send_ack_and_nack_packets) return;

    uint8_t payload[5];
    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)StateMachine_GetState();
    CommsProtocol_Send(MSG_NACK, seq, payload, sizeof(payload));
}

/* Telemetry (timestamp, state, flow, total) */
void Comms_SendTelemetry(void) {
    uint8_t payload[13];
    uint32_t ts = SYSTEM_TICK;
    uint32_t flow = FlowMeter_GetFlow_mLmin();
    uint32_t total = FlowMeter_GetTotal_mL();
    write_u32_le(&payload[0], ts);
    payload[4] = (uint8_t)StateMachine_GetState();
    write_u32_le(&payload[5], flow);
    write_u32_le(&payload[9], total);
    CommsProtocol_Send(MSG_TELEMETRY_PUSH, seq_counter++, payload, sizeof(payload));
}

/* Heartbeat (timestamp, state, optional startup step, 16-bit counter) */
void Comms_SendHeartbeat(void)
{
    uint8_t payload[8];
    SysState_t st = StateMachine_GetState();

    write_u32_le(&payload[0], SYSTEM_TICK);
    payload[4] = (uint8_t)st;

    if (st == SYS_STARTUP_SEQUENCE) {
        payload[5] = StateMachine_GetStartupStep();
    } else {
        payload[5] = 0;
    }

    payload[6] = (uint8_t)(heartbeat_counter & 0xFF);
    payload[7] = (uint8_t)((heartbeat_counter >> 8) & 0xFF);

    heartbeat_counter++;

    CommsProtocol_Send(MSG_HEARTBEAT, seq_counter++, payload, 8);
}

/* ---------------- Application packet handler (complete parity with legacy) ---------------- */

static void Comms_OnPacket(uint8_t type, uint8_t seq, const uint8_t *payload, uint8_t len)
{
    /* Note: behavior parity with legacy implementation, including state checks
       and when ACK/NACK are sent. */
    switch (type)
    {
        case MSG_HANDSHAKE:
        {
            SysState_t st = StateMachine_GetState();

            if (st != SYS_PAIRING)
            {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
                break;
            }

            if (len >= 5)
            {
                uint16_t hb = (uint16_t)payload[0] | ((uint16_t)payload[1] << 8);
                uint16_t tp = (uint16_t)payload[2] | ((uint16_t)payload[3] << 8);
                uint8_t send_ack = payload[4];

                heartbeat_period_ms = hb;
                telemetry_period_ms = tp;
                send_ack_and_nack_packets = send_ack ? 1 : 0;

                uint8_t ack_payload[6];
                write_u32_le(&ack_payload[0], SYSTEM_TICK);
                ack_payload[4] = (uint8_t)st;
                ack_payload[5] = 0;

                CommsProtocol_Send(MSG_HANDSHAKE_ACK, seq, ack_payload, sizeof(ack_payload));

                if (handshake_cb) handshake_cb(hb, send_ack);

                StateMachine_OnHandshakeAccepted();
            }
            else
            {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
            }
            break;
        }

        case MSG_CONFIG:
        {
            SysState_t st = StateMachine_GetState();

            if (st != SYS_PAIRING && st != SYS_RUNNING_PI)
            {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
                break;
            }

            bool applied = Comms_ApplyConfigTLV(payload, len);

            if (applied) {
                if (send_ack_and_nack_packets) Comms_SendAck(seq);
            } else {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
            }
        }
        break;

        case MSG_DESIRED_FLOW:
            if (len >= 4)
            {
                uint32_t flow = (uint32_t)payload[0] |
                                ((uint32_t)payload[1] << 8) |
                                ((uint32_t)payload[2] << 16) |
                                ((uint32_t)payload[3] << 24);

                uint8_t ok = FlowSchedule_Push(flow);

                if (send_ack_and_nack_packets)
                {
                    if (ok) Comms_SendAck(seq);
                    else Comms_SendNack(seq);
                }
            }
            else
            {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
            }
            break;

        case MSG_DESIRED_FLOW_IMMEDIATE:
            if (len >= 4)
            {
                uint32_t flow = (uint32_t)payload[0] |
                                ((uint32_t)payload[1] << 8) |
                                ((uint32_t)payload[2] << 16) |
                                ((uint32_t)payload[3] << 24);

                FlowSchedule_PushImmediate(flow);

                if (send_ack_and_nack_packets) Comms_SendAck(seq);
            }
            else
            {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
            }
            break;

        case MSG_SET_PUMP_PWM:
            /* payload: [duty:1byte] */
            if (len >= 1) {
                SysState_t st = StateMachine_GetState();
                if (st != SYS_RUNNING_PI) {
                    if (send_ack_and_nack_packets) Comms_SendNack(seq);
                    break;
                }

                uint8_t duty = payload[0];
                if (duty > PUMP_DUTY_MAX) duty = PUMP_DUTY_MAX;

                /* Apply immediate manual PWM duty and mark manual mode */
                manual_pwm_duty = duty;
                manual_pwm_enabled = 1;

                /* set timer compare immediately; injection_and_flow uses same timer */
                __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, manual_pwm_duty);

                /* Enter SYS_DEBUG (state machine enforces allowed transitions) */
                StateMachine_EnterDebug();

                if (send_ack_and_nack_packets) Comms_SendAck(seq);
            } else {
                if (send_ack_and_nack_packets) Comms_SendNack(seq);
            }
            break;

        case MSG_EXIT_SYS_DEBUG:
            /* no payload, only valid in SYS_DEBUG */
            {
                SysState_t st = StateMachine_GetState();
                if (st == SYS_DEBUG) {
                    StateMachine_ExitDebug();
                    if (send_ack_and_nack_packets) Comms_SendAck(seq);
                } else {
                    if (send_ack_and_nack_packets) Comms_SendNack(seq);
                }
            }
            break;

        default:
            /* Unknown message type -> NACK (legacy behavior) */
            if (send_ack_and_nack_packets) Comms_SendNack(seq);
            break;
    } /* switch */
}

/* ---------------- Init / Process / Tick ---------------- */

void Comms_Init(USART_TypeDef *uart_inst) {
    /* preserve legacy behavior: heartbeat_counter initially zero */
    heartbeat_counter = 0;

    /* initialize protocol and register packet handler */
    CommsProtocol_Init(uart_inst);
    CommsProtocol_RegisterPacketHandler(Comms_OnPacket);

    /* flush & send initial heartbeat as in legacy */
    Comms_SendHeartbeat();
    HAL_Delay(10);
}

void Comms_Process(void) {
    /* transport-layer parsing & dispatch */
    CommsProtocol_Process();
}

/* Comms tick: heartbeat and telemetry scheduling (parity with legacy) */
void Comms_Tick(void) {
    static uint32_t last_heartbeat_tick = 0;
    static uint32_t last_telemetry_tick = 0;

    uint32_t now = SYSTEM_TICK;

    /* Heartbeat must be sent even before handshake to indicate device alive and current state */
    uint32_t hb_period_ticks = MS_TO_TICKS(heartbeat_period_ms);
    if (hb_period_ticks == 0) hb_period_ticks = MS_TO_TICKS(DEFAULT_HEARTBEAT_PERIOD_MS);

    if ((now - last_heartbeat_tick) >= hb_period_ticks) {
        last_heartbeat_tick = now;
        Comms_SendHeartbeat();
    }

    /* Only send telemetry once we've left startup/pairing */
    SysState_t st = StateMachine_GetState();
    if (st != SYS_RUNNING_PI && st != SYS_STANDALONE_OPERATION) {
        return;   // no telemetry yet
    }

    uint32_t tel_period_ticks = MS_TO_TICKS(telemetry_period_ms);
    if (tel_period_ticks > 0 && (now - last_telemetry_tick) >= tel_period_ticks) {
        last_telemetry_tick = now;
        Comms_SendTelemetry();
    }
}

/* Non-blocking echo debug: called only when in SYS_DEBUG and echo_debug_enabled == 1 */
void EchoDebug_Process(void)
{
    if (!echo_debug_enabled) return;

    #define ECHO_RECV_USART USART1
    #define ECHO_SEND_USART ECHO_RECV_USART

    uint8_t available = UartHAL_RxAvailable(ECHO_RECV_USART);
    if (available == 0) return;

    uint8_t buf[64];
    if (available > sizeof(buf)) available = sizeof(buf);

    for (uint8_t i = 0; i < available; ++i) {
        buf[i] = UartHAL_Read(ECHO_RECV_USART);
    }

    /* send back what we got */
    UartHAL_Send(ECHO_SEND_USART, buf, available);
}
