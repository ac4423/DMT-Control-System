################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.c \
../Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.c 

OBJS += \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.o \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.o 

C_DEPS += \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.d \
./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/CMSIS/DSP/Source/FastMathFunctions/%.o Drivers/CMSIS/DSP/Source/FastMathFunctions/%.su Drivers/CMSIS/DSP/Source/FastMathFunctions/%.cyclo: ../Drivers/CMSIS/DSP/Source/FastMathFunctions/%.c Drivers/CMSIS/DSP/Source/FastMathFunctions/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m3 -std=gnu11 -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/Third_Party/FreeRTOS/Source/include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Device/ST/STM32F1xx/Include" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/STM32F1xx_HAL_Driver/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/ST/STM32_USB_Device_Library/Core/Inc" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/USB_DEVICE/Target" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM3" -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Core/Include" -Os -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@"

clean: clean-Drivers-2f-CMSIS-2f-DSP-2f-Source-2f-FastMathFunctions

clean-Drivers-2f-CMSIS-2f-DSP-2f-Source-2f-FastMathFunctions:
	-$(RM) ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_f32.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q15.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_cos_q31.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_f32.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q15.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sin_q31.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q15.su ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.cyclo ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.d ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.o ./Drivers/CMSIS/DSP/Source/FastMathFunctions/arm_sqrt_q31.su

.PHONY: clean-Drivers-2f-CMSIS-2f-DSP-2f-Source-2f-FastMathFunctions

