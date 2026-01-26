#include "led_strip.h"

// ========================
// === INTERNAL BUFFER  ===
// ========================
static uint8_t led_buffer[NUM_LEDS * 3]; // GRB order

// ========================
// === TIMING CONSTANTS ===
// ========================
// These counts depend on CPU clock speed (assuming ~72 MHz STM32F103)
#define DELAY_0H  1   // ~0.35–0.4 µs
#define DELAY_0L  3   // ~0.85 µs
#define DELAY_1H  2   // ~0.8 µs
#define DELAY_1L  1   // ~0.45 µs

// ========================
// === LOCAL DELAY LOOP ===
// ========================
static inline void delay_cycles(volatile int cycles) {
    while(cycles--);
}

// ========================
// === IMPLEMENTATION   ===
// ========================
void LED_Strip_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitStruct.Pin   = LED_GPIO_PIN;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(LED_GPIO_PORT, &GPIO_InitStruct);

    HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_RESET);
}

void LED_Strip_SetColorAll(uint8_t r, uint8_t g, uint8_t b)
{
    for (int i = 0; i < NUM_LEDS; i++) {
        led_buffer[i*3 + 0] = g;  // WS2812 expects GRB
        led_buffer[i*3 + 1] = r;
        led_buffer[i*3 + 2] = b;
    }
}

void LED_Strip_SendBuffer(void)
{
    __disable_irq();  // stop SysTick & others during WS2812 timing

    for (int i = 0; i < NUM_LEDS * 3; i++) {
        uint8_t mask = 0x80;
        for (int bit = 0; bit < 8; bit++) {
            if (led_buffer[i] & mask) {
                HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_SET);
                delay_cycles(DELAY_1H);
                HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_RESET);
                delay_cycles(DELAY_1L);
            } else {
                HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_SET);
                delay_cycles(DELAY_0H);
                HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_RESET);
                delay_cycles(DELAY_0L);
            }
            mask >>= 1;
        }
//       delay_cycles(10);
    }

    __enable_irq();   // re-enable interrupts

    HAL_Delay(1);     // reset pulse >50 µs
}


void LED_Strip_Update(void)
{
    LED_Strip_SendBuffer();
}
