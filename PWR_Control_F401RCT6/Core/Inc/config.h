#ifndef CONFIG_H
#define CONFIG_H

/* Standard includes */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
/*
 * ----------------------------------------------------------------------
 * Debug / Config Features
 * ----------------------------------------------------------------------
 *
 * These control compile-time debug toggles and test behavior.
 * (Content preserved from original.)
 */

#define SKIP_STARTUP_SEQUENCE 0
#define DEFAULT_USB_SERIAL_DEBUG      0
#define DEFAULT_SERIAL_SEND_MS  200    // default period (ms)
#define DEFAULT_PWM_DEBUG 0
#define DEFAULT_ENABLE_ECHO_DEBUG 0
#define DEFAULT_SOLENOID_TEST 0

/*
 * ----------------------------------------------------------------------
 * Serial / Communications: defaults (runtime-overwritable)
 * ----------------------------------------------------------------------
 *
 * These defaults can be overwritten by Pi during handshake or via
 * MSG_CONFIG TLV packets.
 */

#define DEFAULT_TELEMETRY_PERIOD_MS 200
#define DEFAULT_HEARTBEAT_PERIOD_MS 500
#define DEFAULT_SEND_ACK_AND_NACK 1
#define DEFAULT_SELF_OP_ENABLED 0

/*
 * ----------------------------------------------------------------------
 * Timing helpers & conversion
 * ----------------------------------------------------------------------
 *
 * TIM6 tick period in microseconds: the ISR will increment tim6_tick
 * every TIM6_TICK_uS.
 */

#define DEFAULT_HANDSHAKE_TIMEOUT 30000 // ms

#define TIM6_TICK_uS  100   // microseconds

/* Helper to convert ms -> ticks (TIM6 ticks) */
#define MS_TO_TICKS(ms)   ((uint32_t)(((ms) * 1000U) / TIM6_TICK_uS))

/*
 * ----------------------------------------------------------------------
 * Flowmeter / pump / schedule parameters
 * ----------------------------------------------------------------------
 */
/* COntrol methods: */
#define DEFAULT_ENABLE_PI_CONTROL 1
#define DEFAULT_ENABLE_LOOKUP_TABLE 0


/* parameters: */
#define DEFAULT_FLOW_WINDOW_MS   250
#define DEFAULT_FLOW_PULSES_PER_LITRE   5880U // 5880U
#define DEFAULT_PUMP_SAMPLE_TIME_MS 10

#define RECORD_PULSE_TIMESTAMPS 1

#define SHORT_TERM_PULSE_BUFFER_SIZE 50

// #define FLOW_WINDOW_MS   100     // averaging window for instantaneous flow rate

#define SOLENOID_UPDATE_PERIOD_MS  10

/* Flowmeter specifics */

#define PUMP_SAMPLE_TIME_MS 10 // time period for updating the state of the pump input voltage.

/* How many future pump ticks to store desired flow for */
#define FLOW_SCHEDULE_LEN        128

/* --- Duty limits --- */
#define PUMP_DUTY_MIN     0U
#define PUMP_DUTY_MAX     99U

/* --- PI-control: defaults (can be overwritten by Pi) --- */
#define DEFAULT_PI_Kp 0.05f
#define DEFAULT_PI_Ki 0.05f

#define FLOW_SCHEDULE_MIN_LOOKAHEAD  0 // keep this at zero for now.
#define FLOW_DIFF_LUT_THRESHOLD_MLMIN 500

#define CAL_STEP_DUTY     5U
#define CAL_STABILIZE_MS  500

/*
 * ---------------- These are necessary for timestamped pulse recording:
 */

#if RECORD_PULSE_TIMESTAMPS
#define LONG_TERM_PULSE_ARRAY_CAPACITY 6000 // number of pulses/ size of the timestamp array. 6000 = roughly one litre. 12kB ish of data.
#define PULSE_DELTA_SOFT_MAX 65530u // max real delta value allowed. If a pulse happens at tick = 65530 ? real delta is recorded
#define PULSE_OVERFLOW_MARKER 65531u // indicates overflow chunk. If pulse happens too late ? overflow marker is recorded.
#define UNPOPULATED_ELEMENT_MARKER 65532u // indicates unpopulated -- this is added upon initialisation.
#endif

/*
 * ---------------- PWM Saw Debug (static values; preserved verbatim)
 *
 * NOTE: these static variables were originally in the header. Keeping them
 * here to preserve content exactly; consider moving to config.c in a future refactor.
 */
#define SAW_PWM_MIN 0 // minimum duty (timer counts)
#define SAW_PWM_MAX 99 // maximum duty (timer counts)
#define SAW_PWM_STEP 1 // change per tick

static uint32_t saw_pwm_duty = SAW_PWM_MIN;
static int8_t saw_direction = 1; // +1 rising, -1 falling

/* converted tick thresholds (derived from ms) */
extern uint32_t flowmeter_window_ticks;
extern uint32_t serial_send_ticks_threshold;
extern uint32_t pump_ticks_threshold;

/* runtime-configurable parameters (overwritten via handshake/config packet) */
extern volatile uint16_t telemetry_period_ms; /* ms */
extern volatile uint16_t heartbeat_period_ms; /* ms */
extern volatile uint8_t send_ack_and_nack_packets;
extern volatile uint8_t self_op_enabled;

/* new runtime-configurable debug flags */
extern volatile uint8_t usb_serial_debug_enabled; /* previously ENABLE_USB_SERIAL_DEBUG */
extern volatile uint16_t serial_send_ms;         /* previously SERIAL_SEND_MS */
extern volatile uint8_t pwm_debug_enabled;       /* previously PWM_DEBUG */
extern volatile uint8_t echo_debug_enabled;      /* previously ENABLE_ECHO_DEBUG */

/* --- NEW: flowmeter pulse send debug flag --- */
extern volatile uint8_t flowmeter_pulse_send_debug_enabled; /* 0/1: send packet on each flow pulse while in SYS_DEBUG */

/* -- new runtime flags referenced by ISR / main -- */
extern volatile uint8_t usb_serial_flag;      /* ISR sets when it's time to send serial packet */
extern volatile uint8_t solenoid_test_enabled;/* runtime-controlled solenoid test */

/* runtime-configurable flow/pump params */
extern volatile uint16_t flow_window_ms;         /* averaging window for instantaneous flow rate */
extern volatile uint32_t flow_pulses_per_litre; /* pulses per litre */
extern volatile uint16_t pump_sample_time_ms;    /* previously PUMP_SAMPLE_TIME_MS */

/* runtime pump control*/
extern volatile uint8_t pi_control_enabled;
extern volatile uint8_t lookup_table_enabled;     /* previously ENABLE_LOOKUP_TABLE */

/* manual PWM control (debug): when set by MSG_SET_PUMP_PWM */
extern volatile uint8_t manual_pwm_enabled;
extern volatile uint32_t manual_pwm_duty; /* 0..PUMP_DUTY_MAX */

/* PI control runtime-configurable params */
extern volatile uint8_t pi_control_enabled;

/*
 * ----------------------------------------------------------------------
 * TLV configuration tags table (extend with new tags)
 * ----------------------------------------------------------------------
 */
typedef enum {
    CONFIG_TAG_TELEMETRY_PERIOD_MS = 0x01, /* uint16_t, 2 bytes LE */
    CONFIG_TAG_HEARTBEAT_PERIOD_MS = 0x02, /* uint16_t, 2 bytes LE */
    CONFIG_TAG_PI_KP               = 0x03, /* float, 4 bytes LE (IEEE 754) */
    CONFIG_TAG_PI_KI               = 0x04, /* float, 4 bytes LE (IEEE 754) */
    CONFIG_TAG_ENABLE_PI_CONTROL   = 0x05, /* uint8_t, 1 byte (0/1) */

    /* Debug / runtime flags */
    CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG = 0x06, /* uint8_t, 1 byte (0/1) */
    CONFIG_TAG_SERIAL_SEND_MS          = 0x07, /* uint16_t, 2 bytes LE */
    CONFIG_TAG_PWM_DEBUG               = 0x08, /* uint8_t, 1 byte */
    CONFIG_TAG_ENABLE_ECHO_DEBUG       = 0x09, /* uint8_t, 1 byte */

    /* Flow/Pump runtime params */
    CONFIG_TAG_FLOW_WINDOW_MS          = 0x0A, /* uint16_t, 2 bytes LE */
    CONFIG_TAG_FLOW_PULSES_PER_LITRE   = 0x0B, /* uint32_t, 4 bytes LE */
    CONFIG_TAG_ENABLE_LOOKUP_TABLE     = 0x0C, /* uint8_t, 1 byte */
    CONFIG_TAG_PUMP_SAMPLE_TIME_MS     = 0x0D,  /* uint16_t, 2 bytes LE */
	CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG = 0x0E  /* uint8_t, 1 byte (0/1) */  /* <-- new */
} ConfigTag_t;

/*
 * ----------------------------------------------------------------------
 * Functions
 * ----------------------------------------------------------------------
 */

void flags_init(void);

/* Hook called every flowmeter tick (implementation elsewhere) */
void FlowMeter_TickHook(void);

/* helper to recompute derived tick thresholds when ms values change */
void Config_RecomputeDerivedTicks(void);

/* helper to apply a config TLV tag payload into runtime config */
int Config_ApplyTag(uint8_t tag, const void *payload, size_t len);

/* ----------------- flowmeter 2 --------------- */

#define DEFAULT_FLOW2_WINDOW_MS 200   /* ms; tune as needed */
#define DEFAULT_FLOW2_PULSES_PER_LITRE 450  /* example; set to real sensor spec */

#endif // CONFIG_H

