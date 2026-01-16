#ifndef UART_HAL_H
#define UART_HAL_H

#include <stdint.h>
#include <stddef.h>
#include "stm32f1xx.h"

// -------- Public API (instance-based) --------
// Attach a UART/USART instance AFTER CubeMX calls MX_USARTx_Init().
void UartHAL_Attach(USART_TypeDef *inst);

// Optional: enable/disable RX IRQ (defaults enabled on attach)
void UartHAL_EnableRxIRQ(USART_TypeDef *inst, uint8_t enable);

// Flush RX ring buffer (drop unread data)
void UartHAL_FlushRx(USART_TypeDef *inst);

// Non-blocking read: returns [-1] if no data; otherwise [0..255]
int16_t UartHAL_Read(USART_TypeDef *inst);

// Non-blocking send: enqueues up to 'len' bytes, returns bytes accepted
uint16_t UartHAL_Send(USART_TypeDef *inst, const uint8_t *buf, uint16_t len);

// IRQ handler to be called from the peripheral ISR
void UartHAL_IRQHandler(USART_TypeDef *inst);

uint16_t UartHAL_RxAvailable(USART_TypeDef *inst);

#endif // UART_HAL_H
