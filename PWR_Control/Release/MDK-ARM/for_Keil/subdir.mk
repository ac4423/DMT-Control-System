################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
S_SRCS += \
../MDK-ARM/for_Keil/startup_stm32f103xe_for_Keil.s 

OBJS += \
./MDK-ARM/for_Keil/startup_stm32f103xe_for_Keil.o 

S_DEPS += \
./MDK-ARM/for_Keil/startup_stm32f103xe_for_Keil.d 


# Each subdirectory must supply rules for building sources it contributes
MDK-ARM/for_Keil/%.o: ../MDK-ARM/for_Keil/%.s MDK-ARM/for_Keil/subdir.mk
	arm-none-eabi-gcc -mcpu=cortex-m3 -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc" -x assembler-with-cpp -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@" "$<"

clean: clean-MDK-2d-ARM-2f-for_Keil

clean-MDK-2d-ARM-2f-for_Keil:
	-$(RM) ./MDK-ARM/for_Keil/startup_stm32f103xe_for_Keil.d ./MDK-ARM/for_Keil/startup_stm32f103xe_for_Keil.o

.PHONY: clean-MDK-2d-ARM-2f-for_Keil

