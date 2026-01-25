################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Core/Src/CONFIG.c \
../Core/Src/computer_bridge.c \
../Core/Src/gpio.c \
../Core/Src/hall_sensor.c \
../Core/Src/injection_and_flow.c \
../Core/Src/lasers.c \
../Core/Src/led_strip.c \
../Core/Src/main.c \
../Core/Src/mks42d.c \
../Core/Src/motor_control.c \
../Core/Src/stm32f1xx_hal_msp.c \
../Core/Src/stm32f1xx_it.c \
../Core/Src/system_stm32f1xx.c \
../Core/Src/tim.c \
../Core/Src/uart_hal.c \
../Core/Src/usart.c \
../Core/Src/usb_debug.c 

OBJS += \
./Core/Src/CONFIG.o \
./Core/Src/computer_bridge.o \
./Core/Src/gpio.o \
./Core/Src/hall_sensor.o \
./Core/Src/injection_and_flow.o \
./Core/Src/lasers.o \
./Core/Src/led_strip.o \
./Core/Src/main.o \
./Core/Src/mks42d.o \
./Core/Src/motor_control.o \
./Core/Src/stm32f1xx_hal_msp.o \
./Core/Src/stm32f1xx_it.o \
./Core/Src/system_stm32f1xx.o \
./Core/Src/tim.o \
./Core/Src/uart_hal.o \
./Core/Src/usart.o \
./Core/Src/usb_debug.o 

C_DEPS += \
./Core/Src/CONFIG.d \
./Core/Src/computer_bridge.d \
./Core/Src/gpio.d \
./Core/Src/hall_sensor.d \
./Core/Src/injection_and_flow.d \
./Core/Src/lasers.d \
./Core/Src/led_strip.d \
./Core/Src/main.d \
./Core/Src/mks42d.d \
./Core/Src/motor_control.d \
./Core/Src/stm32f1xx_hal_msp.d \
./Core/Src/stm32f1xx_it.d \
./Core/Src/system_stm32f1xx.d \
./Core/Src/tim.d \
./Core/Src/uart_hal.d \
./Core/Src/usart.d \
./Core/Src/usb_debug.d 


# Each subdirectory must supply rules for building sources it contributes
Core/Src/%.o Core/Src/%.su Core/Src/%.cyclo: ../Core/Src/%.c Core/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m3 -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32F103xE -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Middlewares/ST/STM32_USB_Device_Library/Core/Inc" -I../Core/Inc -I../USB_DEVICE/App -I../USB_DEVICE/Target -I../Drivers/STM32F1xx_HAL_Driver/Inc -I../Drivers/STM32F1xx_HAL_Driver/Inc/Legacy -I../Middlewares/ST/STM32_USB_Device_Library/Core/Inc -I../Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc -I../Drivers/CMSIS/Device/ST/STM32F1xx/Include -I../Drivers/CMSIS/Include -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Drivers/CMSIS/RTOS2/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Drivers/CMSIS/Core_A/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/startup" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@"

clean: clean-Core-2f-Src

clean-Core-2f-Src:
	-$(RM) ./Core/Src/CONFIG.cyclo ./Core/Src/CONFIG.d ./Core/Src/CONFIG.o ./Core/Src/CONFIG.su ./Core/Src/computer_bridge.cyclo ./Core/Src/computer_bridge.d ./Core/Src/computer_bridge.o ./Core/Src/computer_bridge.su ./Core/Src/gpio.cyclo ./Core/Src/gpio.d ./Core/Src/gpio.o ./Core/Src/gpio.su ./Core/Src/hall_sensor.cyclo ./Core/Src/hall_sensor.d ./Core/Src/hall_sensor.o ./Core/Src/hall_sensor.su ./Core/Src/injection_and_flow.cyclo ./Core/Src/injection_and_flow.d ./Core/Src/injection_and_flow.o ./Core/Src/injection_and_flow.su ./Core/Src/lasers.cyclo ./Core/Src/lasers.d ./Core/Src/lasers.o ./Core/Src/lasers.su ./Core/Src/led_strip.cyclo ./Core/Src/led_strip.d ./Core/Src/led_strip.o ./Core/Src/led_strip.su ./Core/Src/main.cyclo ./Core/Src/main.d ./Core/Src/main.o ./Core/Src/main.su ./Core/Src/mks42d.cyclo ./Core/Src/mks42d.d ./Core/Src/mks42d.o ./Core/Src/mks42d.su ./Core/Src/motor_control.cyclo ./Core/Src/motor_control.d ./Core/Src/motor_control.o ./Core/Src/motor_control.su ./Core/Src/stm32f1xx_hal_msp.cyclo ./Core/Src/stm32f1xx_hal_msp.d ./Core/Src/stm32f1xx_hal_msp.o ./Core/Src/stm32f1xx_hal_msp.su ./Core/Src/stm32f1xx_it.cyclo ./Core/Src/stm32f1xx_it.d ./Core/Src/stm32f1xx_it.o ./Core/Src/stm32f1xx_it.su ./Core/Src/system_stm32f1xx.cyclo ./Core/Src/system_stm32f1xx.d ./Core/Src/system_stm32f1xx.o ./Core/Src/system_stm32f1xx.su ./Core/Src/tim.cyclo ./Core/Src/tim.d ./Core/Src/tim.o ./Core/Src/tim.su ./Core/Src/uart_hal.cyclo ./Core/Src/uart_hal.d ./Core/Src/uart_hal.o ./Core/Src/uart_hal.su ./Core/Src/usart.cyclo ./Core/Src/usart.d ./Core/Src/usart.o ./Core/Src/usart.su ./Core/Src/usb_debug.cyclo ./Core/Src/usb_debug.d ./Core/Src/usb_debug.o ./Core/Src/usb_debug.su

.PHONY: clean-Core-2f-Src

