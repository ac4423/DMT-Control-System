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
#include "usb_device.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "hall_sensor.h"
#include "lasers.h"
#include "mks42d.h"
#include "motor_control.h"
#include "computer_bridge.h"
#include "uart_hal.h"
#include "CONFIG.h"
#include "injection_and_flow.h"
#include "usb_debug.h"
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
bool motor_flag = false;
bool motor_read_flag = false;
bool stepper_rx_check_flag = false;
bool check_start_flag = false;
bool transmit_data_flag = false;

// flowmeter + injection pump:
// volatile int flowmeter_pulse_flag = 0;
volatile bool injection_system_flag = 0;

uint32_t tim6_tick = 0;
uint32_t timer_cnt_1s = 0;
uint8_t timer_cnt_2ms = 0;
uint32_t timer_sync_count = 0;
uint32_t usb_serial_timer = 0;



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
  MX_USART2_UART_Init();
  MX_USART3_UART_Init();
  MX_USB_DEVICE_Init();
  /* USER CODE BEGIN 2 */
	
  HAL_TIM_Base_Start_IT(&htim6); // start TIM6 system clock
	HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1); // start TIM2 for PWM for injection pump
	HAL_TIM_IC_Start_IT(&htim3, TIM_CHANNEL_1); // start TIM3 for flowmeter input capture.
	
	// Custom Init functions:
	InjectionAndFlow_Init();
	flags_init();
	
	#if !SKIP_STARTUP_SEQUENCE
	
		goHome(0x03);
	
		while (1) {
			uint8_t result = readGoHomeFinishAck();
			if (result == 1) { // 1 = Success
					break; 
			}
			HAL_Delay(10);
		}
		
		HAL_Delay(5000);
		setZero(0x03);
		
		while (1) {
			uint8_t result = readSetZeroAck();
			if (result == 1) { // 1 = Success
					break; 
			}
			HAL_Delay(10);
		}
		
		HAL_Delay(1000);
		positionMode2Run(0x03, 500, 50, 1600);
		HAL_Delay(5000);
		
	#endif
  
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
		
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
//    hall_status_check();
//    lasers_shutdown();
		
      check_start();
      motor_test();
      motor_read();
      transmit_data();
		
			#if ENABLE_USB_SERIAL_DEBUG
					USB_serial_send_debug();
			#endif
  }
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
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL6;
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

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_USB;
  PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim) {
    if (htim->Instance == TIM3 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1) {
        FlowMeter_PulseCallback(); // call the function directly from the ISR for better real-time timestamping.
    }
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM6) {
				#if RECORD_PULSE_TIMESTAMPS
						FlowMeter_TickHook(); // for recording flowmeter pulse timestamps.
						// GPT says that this is light for the ISR. Roughly 200 nanoseconds of time. Reevaluate and confirm if critical.
				#endif
			
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_14, 1);
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_14, 0);
			
				tim6_tick++;   // new extern counter variable (CONFIG.h)
				
        hall_check_flag = true;
        lasers_flag = true;
        stepper_rx_check_flag = true;
        check_start_flag = true;
			
        if (++timer_cnt_1s >= 10000) {
						timer_cnt_1s = 0;
						motor_flag = true;
        }
				
        if (++timer_cnt_2ms >= 20) {
						timer_cnt_2ms = 0;
						motor_read_flag = true;
						transmit_data_flag = true;
        }
				
				if (++usb_serial_timer >= serial_send_ticks_threshold) {
						usb_serial_timer = 0;
						usb_serial_flag = true;
        }
				
        if (run_state) {
						timer_sync_count++;
        }
				
        else {
						timer_sync_count = 0;
        }
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

#ifdef  USE_FULL_ASSERT
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

/************************ (C) COPYRIGHT STMicroelectronics *****END OF FILE****/
