#include "config.h"
#include "usb_debug.h"
#include "injection_and_flow.h"

/*
 * Convert milliseconds to timer ticks:
 * ticks = (ms * 1000) / tick_us
 */

volatile uint8_t request_dump_long_term;
volatile uint8_t stream_enabled;

#define MS_TO_TICKS(ms)   ((uint32_t)(((ms) * 1000U) / TIM6_TICK_uS))

uint32_t flowmeter_window_ticks = MS_TO_TICKS(FLOW_WINDOW_MS);
uint32_t serial_send_ticks_threshold      = MS_TO_TICKS(SERIAL_SEND_MS);
uint32_t pump_ticks_threshold = MS_TO_TICKS(PUMP_SAMPLE_TIME_MS);

void flags_init(void) {
#if ENABLE_USB_SERIAL_DEBUG
	usb_serial_flag = 0;
#endif
	volatile uint8_t request_dump_long_term = 0;
	volatile uint8_t stream_enabled = 0;
	debug_flag_1=0;
	debug_ticker_1=0;
}
