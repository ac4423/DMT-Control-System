#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>
#include <stdbool.h>

/* ================= Debug / Config Features ================= */

#define SKIP_STARTUP_SEQUENCE 1
#define ENABLE_USB_SERIAL_DEBUG      0
#define SERIAL_SEND_MS  200    // time period of how often to send serial USB debug data
#define PWM_DEBUG 0
#define ENABLE_ECHO_DEBUG 0

/* ================= Serial Comms ================= */

/* default values (can be overwritten by Pi primary/secondary handshake) */
#define DEFAULT_TELEMETRY_PERIOD_MS 10
#define DEFAULT_HEARTBEAT_PERIOD_MS 500
#define DEFAULT_SEND_ACK_AND_NACK 1
#define DEFAULT_SELF_OP_ENABLED 0

/* ================= Timing ================= */

#define DEFAULT_HANDSHAKE_TIMEOUT 30000 // ms
/*
 * TIM6 tick period in microseconds: the ISR will increment tim6_tick every TIM6_TICK_uS.
 * (Note: your code starts TIM2 in main but the conceptual "system tick" is here.)
 */
#define TIM6_TICK_uS  100   // microseconds

/* Helper to convert ms -> ticks (TIM6 ticks) */
#define MS_TO_TICKS(ms)   ((uint32_t)(((ms) * 1000U) / TIM6_TICK_uS))

/* ================= Flowmeter / pump / etc ================= */

#define RECORD_PULSE_TIMESTAMPS 1

#define SHORT_TERM_PULSE_BUFFER_SIZE 50

#define FLOW_WINDOW_MS   100     // averaging window for instantaneous flow rate

/* ================= Flowmeter ================= */
#define FLOW_PULSES_PER_LITRE   5880

/* ================= Pump Control ================= */
#define ENABLE_LOOKUP_TABLE 0
#define DEFAULT_ENABLE_PI_CONTROL 1

/* ================= Pump Control ================= */

#define PUMP_SAMPLE_TIME_MS 10 // time period for updating the state of the pump input voltage.

/* How many future pump ticks to store desired flow for */
#define FLOW_SCHEDULE_LEN        128

/* --- Duty limits --- */
#define PUMP_DUTY_MIN     0U
#define PUMP_DUTY_MAX     99U

/* --- PI-control: defaults (can be overwritten by Pi) --- */
#define DEFAULT_PI_Kp 0.002f
#define DEFAULT_PI_Ki 0.001f

#define FLOW_SCHEDULE_MIN_LOOKAHEAD  0 // keep this at zero for now.
#define FLOW_DIFF_LUT_THRESHOLD_MLMIN 500

#define CAL_STEP_DUTY     5U
#define CAL_STABILIZE_MS  500

/* ================= These are necessary: ================= */

#if RECORD_PULSE_TIMESTAMPS
#define LONG_TERM_PULSE_ARRAY_CAPACITY 6000 // number of pulses/ size of the timestamp array. 6000 = roughly one litre. 12kB ish of data.
#define PULSE_DELTA_SOFT_MAX 65530u // max real delta value allowed. If a pulse happens at tick = 65530 ? real delta is recorded
#define PULSE_OVERFLOW_MARKER 65531u // indicates overflow chunk. If pulse happens too late ? overflow marker is recorded.
#define UNPOPULATED_ELEMENT_MARKER 65532u // indicates unpopulated -- this is added upon initialisation.
#endif

/* ---------------- PWM Saw Debug ---------------- */
#define SAW_PWM_MIN 0 // minimum duty (timer counts)
#define SAW_PWM_MAX 99 // maximum duty (timer counts)
#define SAW_PWM_STEP 1 // change per tick

static uint32_t saw_pwm_duty = SAW_PWM_MIN;
static int8_t saw_direction = 1; // +1 rising, -1 falling
//static uint8_t saw_debug_enable = 1; // set to 0 to disable debug

/* ================= Exported globals (storage + externs) ================= */

/* system tick: increments in timer ISR - this is the single source-of-truth for timestamps */
// extern volatile uint32_t tim6_tick;

/* converted tick thresholds (derived from ms) */
extern uint32_t flowmeter_window_ticks;
extern uint32_t serial_send_ticks_threshold;
extern uint32_t pump_ticks_threshold;

/* runtime-configurable communication parameters (overwritten via handshake/config packet) */
extern volatile uint16_t telemetry_period_ms; /* ms */
extern volatile uint16_t heartbeat_period_ms; /* ms */
extern volatile uint8_t send_ack_and_nack_packets;
extern volatile uint8_t self_op_enabled;

/* telemetry and stream flags */
extern volatile uint8_t request_dump_long_term;
extern volatile uint8_t stream_enabled;

/* PI control runtime-configurable params */
extern volatile float PI_Kp;
extern volatile float PI_Ki;
extern volatile uint8_t ENABLE_PI_CONTROL;

/* ================= Functions ================= */

void FlowMeter_TickHook(void);
void flags_init(void);

#endif // CONFIG_H
