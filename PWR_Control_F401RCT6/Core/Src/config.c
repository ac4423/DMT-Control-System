#include "config.h"
#include "usb_debug.h"
#include "injection_and_flow.h"

/* system tick variable (single source of timestamp throughout the code) */
volatile uint32_t tim6_tick = 0;

/* converted thresholds (in TIM6 ticks) */
uint32_t flowmeter_window_ticks = MS_TO_TICKS(FLOW_WINDOW_MS);
uint32_t serial_send_ticks_threshold = MS_TO_TICKS(SERIAL_SEND_MS);
uint32_t pump_ticks_threshold = MS_TO_TICKS(PUMP_SAMPLE_TIME_MS);

/* runtime-configurable comm params (defaults, overwritten by handshake) */
volatile uint16_t telemetry_period_ms = DEFAULT_TELEMETRY_PERIOD_MS;
volatile uint16_t heartbeat_period_ms = DEFAULT_HEARTBEAT_PERIOD_MS;
volatile uint8_t send_ack_and_nack_packets = DEFAULT_SEND_ACK_AND_NACK;
volatile uint8_t self_op_enabled = DEFAULT_SELF_OP_ENABLED;

/* runtime PI control params (overwritable by secondary config) */
volatile float PI_Kp = DEFAULT_PI_Kp;
volatile float PI_Ki = DEFAULT_PI_Ki;
volatile uint8_t ENABLE_PI_CONTROL = DEFAULT_ENABLE_PI_CONTROL;

/* telemetry/stream flags */
volatile uint8_t request_dump_long_term = 0;
volatile uint8_t stream_enabled = 0;

void flags_init(void) {
#if ENABLE_USB_SERIAL_DEBUG
    usb_serial_flag = 0;
#endif
    request_dump_long_term = 0;
    stream_enabled = 0;
    debug_flag_1 = 0;
    debug_ticker_1 = 0;
}
