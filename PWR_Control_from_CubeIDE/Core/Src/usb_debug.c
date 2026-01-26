#include "usb_debug.h"
#include "usb_device.h"  // CubeMX USB CDC interface
#include "usbd_cdc_if.h"
#include <stdio.h>
#include <stdarg.h>
#include "injection_and_flow.h"
#include "config.h"
#include "flow_lut.h"

int8_t usb_serial_flag;

void USB_serial_send_debug() {
	if (stream_enabled) {
	// if (1) {
		if (usb_serial_flag) {
		// if (1) {
		
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
	
	if (request_dump_long_term)
    {
        request_dump_long_term = 0;
        Dump_LongTerm_Memory_USB();
        return;
    }
	
}

void Dump_LongTerm_Memory_USB(void)
{
#if !RECORD_PULSE_TIMESTAMPS
    const char *msg = "LONGTERM: disabled (RECORD_PULSE_TIMESTAMPS=0)\r\n";
    CDC_Transmit_FS((uint8_t*)msg, strlen(msg));
    return;
#endif

    uint32_t count;

    // Take atomic snapshot of count
    __disable_irq();
    count = FlowMeter_GetPulseDeltaCount();
    __enable_irq();

    char header[64];
    int len = snprintf(header, sizeof(header),
                       "\r\nLONGTERM_DUMP,count=%lu\r\n", count);
    CDC_Transmit_FS((uint8_t*)header, len);

    const volatile uint16_t* deltas = FlowMeter_GetPulseDeltas();

    char line[32];

    for (uint32_t i = 0; i < count; i++)
    {
        uint16_t v = deltas[i];

        if (v == PULSE_OVERFLOW_MARKER)
        {
            len = snprintf(line, sizeof(line), "%lu,OVERFLOW\r\n", i);
        }
        else
        {
            len = snprintf(line, sizeof(line), "%lu,%u\r\n", i, v);
        }

        // Wait if USB is busy (non-blocking safe version)
        while (CDC_Transmit_FS((uint8_t*)line, len) == USBD_BUSY)
        {
            HAL_Delay(1);
        }
    }

    const char *footer = "END_LONGTERM_DUMP\r\n";
    CDC_Transmit_FS((uint8_t*)footer, strlen(footer));
}

/* --- USB debug dump --- */
void FlowLUT_SendToUSB(void)
{
    char msg[64];
    for (size_t i = 0; i < FlowLUT.n_points; i++) {
        int len = snprintf(msg, sizeof(msg), "LUT[%lu]: %.3f L/min -> Duty %u\r\n",
                           i, FlowLUT.points[i].flow_lmin, FlowLUT.points[i].duty);
        while (CDC_Transmit_FS((uint8_t*)msg, len) == USBD_BUSY)
            HAL_Delay(1);
    }
}
