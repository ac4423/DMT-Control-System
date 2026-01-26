################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.c 

OBJS += \
./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.o 

C_DEPS += \
./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/%.o Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/%.su Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/%.cyclo: ../Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/%.c Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m3 -std=gnu11 -DUSE_HAL_DRIVER -DSTM32F103xE -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Drivers/CMSIS/Device/ST/STM32F1xx/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Drivers/STM32F1xx_HAL_Driver/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Middlewares/ST/STM32_USB_Device_Library/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/USB_DEVICE/Target" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/Drivers/CMSIS/Core/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control_from_CubeIDE/USB_DEVICE/App" -I../Core/Inc -I../USB_DEVICE/App -I../USB_DEVICE/Target -I../Drivers/STM32F1xx_HAL_Driver/Inc -I../Drivers/STM32F1xx_HAL_Driver/Inc/Legacy -I../Middlewares/ST/STM32_USB_Device_Library/Core/Inc -I../Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc -I../Drivers/CMSIS/Device/ST/STM32F1xx/Include -I../Drivers/CMSIS/Include -Os -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@"

clean: clean-Drivers-2f-CMSIS-2f-DSP-2f-Examples-2f-ARM-2f-arm_class_marks_example

clean-Drivers-2f-CMSIS-2f-DSP-2f-Examples-2f-ARM-2f-arm_class_marks_example:
	-$(RM) ./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.cyclo ./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.d ./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.o ./Drivers/CMSIS/DSP/Examples/ARM/arm_class_marks_example/arm_class_marks_example_f32.su

.PHONY: clean-Drivers-2f-CMSIS-2f-DSP-2f-Examples-2f-ARM-2f-arm_class_marks_example

