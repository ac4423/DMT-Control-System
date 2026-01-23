#include "usb_debug.h"
#include "usb_device.h"  // CubeMX USB CDC interface
#include "usbd_cdc_if.h"
#include <stdio.h>
#include <stdarg.h>
#include "injection_and_flow.h"
#include "config.h"

int8_t usb_serial_flag;

void USB_serial_send_debug() {
	if (usb_serial_flag) {
		
		usb_serial_flag = 0;
		
		FlowMeter_UpdateInstantaneous();
		FlowMeter_UpdateTotal();
		
		float flow = FlowMeter_GetFlow_Lmin();
		float volume = FlowMeter_GetTotalLitres();

		char msg[96];
		int len = snprintf(msg, sizeof(msg),
				"Flow: %.3f L/min | Volume: %.4f L\r\n",
				flow, volume);

		CDC_Transmit_FS((uint8_t*)msg, len);
	}
}