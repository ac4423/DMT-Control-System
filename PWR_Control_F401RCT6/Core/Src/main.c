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
#include "motor_control.h"
#include "computer_bridge.h"
#include "uart_hal.h"
#include "config.h"
#include "injection_and_flow.h"
#include "state_machine.h"
#if ENABLE_USB_SERIAL_DEBUG
#include "usb_debug.h"
#endif
#include "comms.h"
#include "state_machine.h"
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
volatile bool hall_check_flag = false;
volatile bool lasers_flag = false;
volatile bool motor_flag = false;
volatile bool motor_read_flag = false;
volatile bool stepper_rx_check_flag = false;
volatile bool check_start_flag = false;
volatile bool transmit_data_flag = false;

// flowmeter + injection pump:
// volatile int flowmeter_pulse_flag = 0;
volatile bool injection_system_flag = 0;

uint32_t timer_cnt_1s = 0;
uint32_t usart_count_ms = 0;
uint32_t stepper_motor_read_count_ms = 0;
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
  MX_TIM5_Init();
  MX_USART2_UART_Init();
  MX_USART6_UART_Init();
  /* USER CODE BEGIN 2 */

	HAL_TIM_Base_Start_IT(&htim2); // start SYSTEM_TICK system clock
//	HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1); // start TIM3 for PWM for injection pump
//	HAL_TIM_IC_Start_IT(&htim5, TIM_CHANNEL_1); // start TIM5 for flowmeter input capture.
//	
//	// Custom Init functions:
//	InjectionAndFlow_Init();
//	flags_init();
//	
//	// in main() after HAL and peripheral init:
//	
//	// ComputerBridge_Init();    // sets up comms
//	StateMachine_Init();      // sets state to SYS_STARTUP
//	
//	Comms_Init(USART6); // set up comms
//	UartHAL_FlushRx(USART6);
//	// UartHAL_EnableRxIRQ(USART6, 1);  // re-enable RX interrupt

//	/*
//	while (1) {
//		if (USART6->CR1 & USART_CR1_RXNEIE) {
//		    char c = 'A';
//		    // UartHAL_Send(USART6, (uint8_t*)&c, 1);  // should send
//		    Comms_SendHeartbeat();
//		    HAL_Delay(10);
//		} else {
//		    char c = 'X';
//		    // UartHAL_Send(USART6, (uint8_t*)&c, 1);  // debug
//		}
//	}
//	*/


//	#if ENABLE_ECHO_DEBUG
//	while (1) {
//		int16_t byte = UartHAL_Read(USART6);  // read one byte from RX
//		if (byte >= 0) {
//			uint8_t b = (uint8_t)byte;
//			UartHAL_Send(USART6, &b, 1);     // immediately send it back
//		}
//		// optionally, small delay if CPU load is an issue:
//		// HAL_Delay(1);
//	}
//	#endif

//	//*/

//  
//	while (1) {
//		// keep Comms parsing running
//		Comms_Process();

//		// state machine handling for startup/handshake/timeouts
//		StateMachine_ProcessTick();

//		// send telemetry and heartbeat packets)
//		Comms_Tick();

//		// Small delay / let other interrupts do work; do not block.
//	}

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, 0);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2, 0);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, 0);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
	while (1)
	{
    /* USER CODE END WHILE */
        RunStartupSequence();
    /* USER CODE BEGIN 3 */
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

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim) {
    if (htim->Instance == TIM5 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1) {
        FlowMeter_PulseCallback(); // call the function directly from the ISR for better real-time timestamping.
    }
}

/* inside HAL_TIM_PeriodElapsedCallback */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        /* increment the system tick (single timebase used for timestamps) */
    	SYSTEM_TICK++;  // <-- IMPORTANT: TIM2/TIM6 comment mismatch — this is your system tick increment

        #if RECORD_PULSE_TIMESTAMPS
            FlowMeter_TickHook();
        #endif

        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_14, 1);
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_14, 0);

        hall_check_flag = true;
        lasers_flag = true;
        stepper_rx_check_flag = true;
        check_start_flag = true;

        /* Convert ms counters to ticks where appropriate in other modules.
           Keep these counters for backward compatibility but they are driven by the ISR tick increments. */

        // simple counters retained but can be refactored to use tim6_tick comparisons
        if (++timer_cnt_1s >= 10000) {
            timer_cnt_1s = 0;
            motor_flag = true;
        }

        /*
        if (++usart_count_ms >= PI_STM_TRANSMIT_DATA_PERIOD_MS) {
            usart_count_ms = 0;
            transmit_data_flag = true;
        }
        */

        /*
        if (++stepper_motor_read_count_ms >= STEPPER_MOTOR_READ_PERIOD_MS) {
            stepper_motor_read_count_ms = 0;
            motor_read_flag = true;
        }
        */

#if ENABLE_USB_SERIAL_DEBUG
        if (++usb_serial_timer >= serial_send_ticks_threshold) {
            usb_serial_timer = 0;
            usb_serial_flag = 1;
        }
#endif

        if (++Pump_Control.pump_counter >= pump_ticks_threshold) {
            Pump_Control.pump_counter = 0;
            Pump_Control.pump_flag = 1;
        }

        if (++debug_ticker_1 >= 1000) {
            debug_ticker_1 = 0;
            debug_flag_1 = 1;
        }

        if (run_state) {
            timer_sync_count++;
        } else {
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
  while (1) {};
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
