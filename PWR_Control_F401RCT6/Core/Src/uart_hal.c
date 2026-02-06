#include "uart_hal.h"

// ===== Configuration =====
#ifndef UART_HAL_RX_SZ
#define UART_HAL_RX_SZ 1024
#endif
#ifndef UART_HAL_TX_SZ
#define UART_HAL_TX_SZ 1024
#endif

typedef struct {
    USART_TypeDef *inst;
    volatile uint8_t rx[UART_HAL_RX_SZ];
    volatile uint16_t rx_head, rx_tail;

    volatile uint8_t tx[UART_HAL_TX_SZ];
    volatile uint16_t tx_head, tx_tail;

    uint8_t attached;
} UartHAL_Port;

static UartHAL_Port _ports[6];

static inline UartHAL_Port* _get_port(USART_TypeDef *inst) {
    if (inst == USART1) return &_ports[0];
    if (inst == USART2) return &_ports[1];
    if (inst == USART6) return &_ports[2];
    return NULL;
}

static inline uint16_t _nxt(uint16_t i, uint16_t mod) { return (uint16_t)((i + 1u) % mod); }

void UartHAL_Attach(USART_TypeDef *inst) {
    UartHAL_Port *p = _get_port(inst);
    if (!p) return;
    p->inst = inst;
    p->rx_head = p->rx_tail = 0;
    p->tx_head = p->tx_tail = 0;
    p->attached = 1u;

    // Enable RXNE interrupt so RX is always captured
    // (CubeMX already enabled clocks/GPIO/IRQ; MX_USARTx_Init called before.)
    p->inst->CR1 |= USART_CR1_RXNEIE;
}

void UartHAL_EnableRxIRQ(USART_TypeDef *inst, uint8_t enable) {
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached) return;
    if (enable) p->inst->CR1 |= USART_CR1_RXNEIE;
    else        p->inst->CR1 &= ~USART_CR1_RXNEIE;
}

void UartHAL_FlushRx(USART_TypeDef *inst) {
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached) return;
    __disable_irq();
    p->rx_head = p->rx_tail = 0;
    __enable_irq();
}

int16_t UartHAL_Read(USART_TypeDef *inst) {
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached) return -1;
    int16_t out = -1;
    __disable_irq();
    if (p->rx_head != p->rx_tail) {
        out = p->rx[p->rx_tail];
        p->rx_tail = _nxt(p->rx_tail, UART_HAL_RX_SZ);
    }
    __enable_irq();
    return out;
}

uint16_t UartHAL_Send(USART_TypeDef *inst, const uint8_t *buf, uint16_t len) {
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached || !buf || !len) return 0;

    uint16_t accepted = 0;
    __disable_irq();
    for (; accepted < len; ++accepted) {
        uint16_t n = _nxt(p->tx_head, UART_HAL_TX_SZ);
        if (n == p->tx_tail) break; // full
        p->tx[p->tx_head] = buf[accepted];
        p->tx_head = n;
    }
    // Kick TXE interrupt to start draining
    if (p->tx_head != p->tx_tail) {
        p->inst->CR1 |= USART_CR1_TXEIE;
    }
    __enable_irq();
    return accepted;
}

void UartHAL_IRQHandler(USART_TypeDef *inst) {
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached) return;

    uint32_t sr = p->inst->SR;

    // RXNE: data available
    if (sr & USART_SR_RXNE) {
        uint8_t b = (uint8_t)p->inst->DR; // read DR clears RXNE
        uint16_t n = _nxt(p->rx_head, UART_HAL_RX_SZ);
        if (n != p->rx_tail) {
            p->rx[p->rx_head] = b;
            p->rx_head = n;
        } else {
            // overflow -> drop byte
        }
    }

    // TXE: data register empty -> send next if any
    if ((p->inst->CR1 & USART_CR1_TXEIE) && (sr & USART_SR_TXE)) {
        if (p->tx_tail != p->tx_head) {
            p->inst->DR = p->tx[p->tx_tail];
            p->tx_tail = _nxt(p->tx_tail, UART_HAL_TX_SZ);
        } else {
            // nothing to send -> disable TXE interrupt
            p->inst->CR1 &= ~USART_CR1_TXEIE;
            // We do NOT use TCIE; simpler and fine for full-duplex UART buses.
        }
    }

    // Optional: handle ORE by reading DR if needed; RXNE path already reads DR.
    if (sr & USART_SR_ORE) { volatile uint8_t dummy = p->inst->DR; (void)dummy; }
}

// Add to uart_hal.c
uint16_t UartHAL_RxAvailable(USART_TypeDef *inst)
{
    UartHAL_Port *p = _get_port(inst);
    if (!p || !p->attached) return 0;
    
    __disable_irq();
    uint16_t available = (p->rx_head >= p->rx_tail) ? 
                       (p->rx_head - p->rx_tail) : 
                       (UART_HAL_RX_SZ - p->rx_tail + p->rx_head);
    __enable_irq();
    
    return available;
}
