/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    injection_pump.c
  * @brief   Injection pump control module
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "injection_pump.h"
#include "gpio.h"

/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  Initializes the injection pump control.
  *         Only sets PE12 high.
  * @retval None
  */
void InjectionPump_Init(void)
{
    /* Set PE12 high in the same way as HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, 1); */
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_12, GPIO_PIN_SET);
		HAL_GPIO_WritePin(GPIOC, GPIO_PIN_10, GPIO_PIN_SET);
}