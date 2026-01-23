#include "config.h"
#include "usb_debug.h"

/*
 * Convert milliseconds to timer ticks:
 * ticks = (ms * 1000) / tick_us
 */

#define MS_TO_TICKS(ms)   ((uint32_t)(((ms) * 1000U) / TIM6_TICK_uS))

uint32_t flowmeter_window_ticks = MS_TO_TICKS(FLOW_WINDOW_MS);
uint32_t serial_send_ticks_threshold      = MS_TO_TICKS(SERIAL_SEND_MS);

void flags_init(void) {
	usb_serial_flag = 0;
}