#include "config.h"
#include "usb_debug.h"
#include "injection_and_flow.h"
#include <stddef.h> // for size_t
#include <string.h> // for memcpy if needed

/* ---------------- runtime-configurable storage ---------------- */
/* converted tick thresholds (in TIM6 ticks) */
uint32_t flowmeter_window_ticks = MS_TO_TICKS(DEFAULT_FLOW_WINDOW_MS);
uint32_t serial_send_ticks_threshold = MS_TO_TICKS(DEFAULT_SERIAL_SEND_MS);
uint32_t pump_ticks_threshold = MS_TO_TICKS(DEFAULT_PUMP_SAMPLE_TIME_MS);

/* runtime-configurable comm params (defaults) */
volatile uint16_t telemetry_period_ms = DEFAULT_TELEMETRY_PERIOD_MS;
volatile uint16_t heartbeat_period_ms = DEFAULT_HEARTBEAT_PERIOD_MS;
volatile uint8_t send_ack_and_nack_packets = DEFAULT_SEND_ACK_AND_NACK;
volatile uint8_t self_op_enabled = DEFAULT_SELF_OP_ENABLED;

/* runtime debug flags & periods */
volatile uint8_t usb_serial_debug_enabled = DEFAULT_USB_SERIAL_DEBUG;
volatile uint16_t serial_send_ms = DEFAULT_SERIAL_SEND_MS;
volatile uint8_t pwm_debug_enabled = DEFAULT_PWM_DEBUG;
volatile uint8_t echo_debug_enabled = DEFAULT_ENABLE_ECHO_DEBUG;

/* runtime flow/pump params */
volatile uint16_t flow_window_ms = DEFAULT_FLOW_WINDOW_MS;
volatile uint32_t flow_pulses_per_litre = DEFAULT_FLOW_PULSES_PER_LITRE;
volatile uint16_t pump_sample_time_ms = DEFAULT_PUMP_SAMPLE_TIME_MS;

/* pump control */
volatile uint8_t lookup_table_enabled = DEFAULT_ENABLE_LOOKUP_TABLE;
volatile uint8_t pi_control_enabled = DEFAULT_ENABLE_PI_CONTROL;

/* manual PWM debug variables */
volatile uint8_t manual_pwm_enabled = 0;
volatile uint32_t manual_pwm_duty = 0;

/* telemetry/stream flags */
volatile uint8_t request_dump_long_term = 0;
volatile uint8_t stream_enabled = 0;

/* debug tickers (kept from original) */
volatile uint8_t debug_flag_1 = 0;
volatile uint16_t debug_ticker_1 = 0;

/* add near other runtime vars in config.c */

volatile uint8_t usb_serial_flag = 0;
volatile uint8_t solenoid_test_enabled = DEFAULT_SOLENOID_TEST; // runtime control

/* ------------------------ Functions ----------------------------------- */

void flags_init(void) {
    /* ensure runtime variables use their defaults initially and derived ticks are valid */
    request_dump_long_term = 0;
    stream_enabled = 0;

    solenoid_test_enabled = DEFAULT_SOLENOID_TEST;
    usb_serial_flag = 0;

    usb_serial_debug_enabled = DEFAULT_USB_SERIAL_DEBUG;
    serial_send_ms = DEFAULT_SERIAL_SEND_MS;
    pwm_debug_enabled = DEFAULT_PWM_DEBUG;
    echo_debug_enabled = DEFAULT_ENABLE_ECHO_DEBUG;

    flow_window_ms = DEFAULT_FLOW_WINDOW_MS;
    flow_pulses_per_litre = DEFAULT_FLOW_PULSES_PER_LITRE;
    pump_sample_time_ms = DEFAULT_PUMP_SAMPLE_TIME_MS;

    manual_pwm_enabled = 0;
    manual_pwm_duty = 0;

    /* compute derived tick thresholds from ms */
    flowmeter_window_ticks = MS_TO_TICKS(flow_window_ms);
    serial_send_ticks_threshold = MS_TO_TICKS(serial_send_ms);
    pump_ticks_threshold = MS_TO_TICKS(pump_sample_time_ms);

    /* keep any debug tickers zeroed */
    debug_flag_1 = 0;
    debug_ticker_1 = 0;

    /* Pump control */
    pi_control_enabled = DEFAULT_ENABLE_PI_CONTROL;
	lookup_table_enabled = DEFAULT_ENABLE_LOOKUP_TABLE;
}

/*
 * TLV metadata table (read-only). This is descriptive and may be used by the
 * Pi-side tooling or by a future "describe-config" RPC. It does not change
 * runtime behavior by itself.
 *
 * Keep entries in the same order as ConfigTag_t.
 */
/* ---------------- TLV metadata table (read-only) ----------------------- */
typedef struct {
    uint8_t tag;
    const char *name;
    uint8_t length; /* expected payload length in bytes */
    const char *type; /* human readable type */
} ConfigTagInfo_t;

// these strings for each entry are just supposed to be human-readable apparently -- no other functionality...
static const ConfigTagInfo_t TLV_TagTable[] = {
    { CONFIG_TAG_TELEMETRY_PERIOD_MS, "telemetry_period_ms", 2, "uint16_t (ms)" },
    { CONFIG_TAG_HEARTBEAT_PERIOD_MS, "heartbeat_period_ms", 2, "uint16_t (ms)" },
    { CONFIG_TAG_PI_KP,               "Pump_Control.kp",     4, "float (IEEE754)" },
    { CONFIG_TAG_PI_KI,               "Pump_Control.ki",     4, "float (IEEE754)" },
    { CONFIG_TAG_ENABLE_PI_CONTROL,   "pi_control_enabled",  1, "uint8_t (0/1)" },

    { CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG, "enable_usb_serial_debug", 1, "uint8_t (0/1)" },
    { CONFIG_TAG_SERIAL_SEND_MS,          "serial_send_ms",         2, "uint16_t (ms)" },
    { CONFIG_TAG_PWM_DEBUG,               "pwm_debug",              1, "uint8_t (0/1)" },
    { CONFIG_TAG_ENABLE_ECHO_DEBUG,       "enable_echo_debug",      1, "uint8_t (0/1)" },

    { CONFIG_TAG_FLOW_WINDOW_MS,          "flow_window_ms",         2, "uint16_t (ms)" },
    { CONFIG_TAG_FLOW_PULSES_PER_LITRE,   "flow_pulses_per_litre",  4, "uint32_t" },
    { CONFIG_TAG_ENABLE_LOOKUP_TABLE,     "enable_lookup_table",    1, "uint8_t (0/1)" },
    { CONFIG_TAG_PUMP_SAMPLE_TIME_MS,     "pump_sample_time_ms",    2, "uint16_t (ms)" }
};

static const size_t TLV_TagTableCount = sizeof(TLV_TagTable) / sizeof(TLV_TagTable[0]);

const ConfigTagInfo_t *Config_GetTagTable(size_t *out_count) {
    if (out_count) *out_count = TLV_TagTableCount;
    return TLV_TagTable;
}
