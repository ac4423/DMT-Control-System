/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * <h2><center>&copy; Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.</center></h2>
  *
  * This software component is licensed by ST under BSD 3-Clause license,
  * the "License"; You may not use this file except in compliance with the
  * License. You may obtain a copy of the License at:
  *                        opensource.org/licenses/BSD-3-Clause
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "hall_sensor.h"
#include "lasers.h"
#include "mks42d.h"
#include "flowmeter.h"
#include "injection_pump.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
bool hall_check_flag = false;
bool lasers_flag = false;

uint32_t timer_cnt_test = 0;

volatile uint32_t tim6_tick = 0;
volatile bool flow_update_flag = false;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
   
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();
  MX_TIM6_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  MX_TIM4_Init();
  /* USER CODE BEGIN 2 */
  HAL_TIM_Base_Start_IT(&htim6); // start timer6-driven highest level/main function actions.
  HAL_Delay(100);
  goHome(0x03);
  
	HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1); // start timer2-driven PWM for (to 12V PWM module then to) injection pump.

	HAL_TIM_IC_Start_IT(&htim3, TIM_CHANNEL_1); // start flow meter input timer3-enabled channels
	
	HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_1); // timer for powering LED (debugging)
	FlowMeter_Init();
	InjectionPump_Init();

	
	// uint32_t last_update = HAL_GetTick();
	
	uint32_t duty_pump = 49; // maximum is 49
	uint32_t duty_LED = 0; // maximum is 49
	
	volatile int8_t dir = 1;

	while (1)
	{
			if (flow_update_flag)
			{
					flow_update_flag = false;

					FlowMeter_Update(100);  // 100 ms window

					float flow = FlowMeter_GetFlow_Lmin();

					if (flow < 0.3f) flow = 0.3f;
					if (flow > 6.0f) flow = 6.0f;

					duty_LED = (uint32_t)(((flow - 0.3f) / (6.0f - 0.3f)) * 49.0f);
					if (duty_LED > 49) duty_LED = 49;
					if (duty_LED < 0) duty_LED = 0;
			}

			__HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, duty_pump);
			__HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, duty_LED);
			
//			// example of functionality:
//			
//			__HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, duty_LED);

//			duty_LED += dir;
//			
//			if (duty_LED >= 49) {
//				dir = -1;
//			}
//			
//			else if (duty_LED <= 0) {
//				dir = 1;
//			}

//			HAL_Delay(20);
	}

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  
//	while (1)
//  {
//		HAL_Delay(1000);
//		// HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, 1);
//		HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_13);
//		
//		
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
//    // hall_status_check();
//    // lasers_shutdown();
//  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM3 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1)
    {
        FlowMeter_PulseCallback();
    }
}


void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM6)
    {
        tim6_tick++;

        // 100ms = 1000 ticks at 10kHz
        if (tim6_tick >= 1000)
        {
            tim6_tick = 0;
            flow_update_flag = true;
        }

        hall_check_flag = true;
        lasers_flag = true;
    }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
