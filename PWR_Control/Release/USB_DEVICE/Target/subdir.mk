################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../USB_DEVICE/Target/usbd_conf.c 

OBJS += \
./USB_DEVICE/Target/usbd_conf.o 

C_DEPS += \
./USB_DEVICE/Target/usbd_conf.d 


# Each subdirectory must supply rules for building sources it contributes
USB_DEVICE/Target/%.o USB_DEVICE/Target/%.su USB_DEVICE/Target/%.cyclo: ../USB_DEVICE/Target/%.c USB_DEVICE/Target/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m3 -std=gnu11 -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/Third_Party/FreeRTOS/Source/include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Device/ST/STM32F1xx/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/STM32F1xx_HAL_Driver/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/ST/STM32_USB_Device_Library/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/USB_DEVICE/Target" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM3" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Core/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/USB_DEVICE/App" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -Os -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@"

clean: clean-USB_DEVICE-2f-Target

clean-USB_DEVICE-2f-Target:
	-$(RM) ./USB_DEVICE/Target/usbd_conf.cyclo ./USB_DEVICE/Target/usbd_conf.d ./USB_DEVICE/Target/usbd_conf.o ./USB_DEVICE/Target/usbd_conf.su

.PHONY: clean-USB_DEVICE-2f-Target

