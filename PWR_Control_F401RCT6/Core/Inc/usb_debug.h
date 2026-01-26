#ifndef USB_DEBUG_H
#define USB_DEBUG_H

#if ENABLE_USB_SERIAL_DEBUG

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdint.h>
#include <stdbool.h>

extern int8_t usb_serial_flag;

void USB_serial_send_debug(void);
void Dump_LongTerm_Memory_USB(void);

#ifdef __cplusplus
}
#endif

#endif

#endif /* USB_DEBUG_H */
