#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

/* ================= Debug / Config Features ================= */

#define SKIP_STARTUP_SEQUENCE 1
#define ENABLE_USB_SERIAL_DEBUG      1


// for recording the pulse timestamps.
#define RECORD_PULSE_TIMESTAMPS   0
#define LONG_TERM_PULSE_ARRAY_CAPACITY 6000 // size of the timestamp array. 6000 = roughly one litre. 12kB ish of data.

#define PULSE_DELTA_SOFT_MAX     65530u   // max real delta value allowed. If a pulse happens at tick = 65530 ? real delta is recorded
#define PULSE_OVERFLOW_MARKER   65531u   // indicates overflow chunk. If pulse happens too late ? overflow marker is recorded.

#define SHORT_TERM_PULSE_BUFFER_SIZE 100


/* ================= Timing ================= */

// Timer 6 tick period in microseconds:
#define TIM6_TICK_uS  100   // microseconds

#define FLOW_WINDOW_MS   100     // averaging window for instantaneous flow rate
#define SERIAL_SEND_MS  200    // time period of how often to send serial USB debug data

/* ================= Flowmeter ================= */

#define FLOW_PULSES_PER_LITRE   5880   // calibrate if needed

/* ================= extern declarations ================= */

extern uint32_t tim6_tick;
extern uint32_t last_pulse_tick;

extern uint32_t flowmeter_window_ticks;
extern uint32_t serial_send_ticks_threshold;
extern volatile int flowmeter_pulse_flag;

/* ================= functions ================= */

void FlowMeter_TickHook(void);
void flags_init(void);

#endif // CONFIG_H