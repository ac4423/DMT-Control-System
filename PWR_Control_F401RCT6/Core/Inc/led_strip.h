#ifndef __LED_STRIP_H
#define __LED_STRIP_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"   // Adjust family header if needed

// ========================
// === USER DEFINITIONS ===
// ========================

// LED data pin
#define LED_GPIO_PORT    GPIOA
#define LED_GPIO_PIN     GPIO_PIN_0

// Number of LEDs in your strip
#define NUM_LEDS         30   // adjust to your actual strip length

// ========================
// === PUBLIC FUNCTIONS ===
// ========================

/**
 * @brief Initialize LED data pin
 */
void LED_Strip_Init(void);

/**
 * @brief Set the same color for all LEDs
 * @param r Red   (0�255)
 * @param g Green (0�255)
 * @param b Blue  (0�255)
 */
void LED_Strip_SetColorAll(uint8_t r, uint8_t g, uint8_t b);

/**
 * @brief Send the data buffer to the LED strip
 */
void LED_Strip_SendBuffer(void);

/**
 * @brief Update LED colors (calls SendBuffer)
 */
void LED_Strip_Update(void);

#ifdef __cplusplus
}
#endif

#endif /* __LED_STRIP_H */
