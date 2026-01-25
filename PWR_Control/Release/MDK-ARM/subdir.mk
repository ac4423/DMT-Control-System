################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
S_SRCS += \
../MDK-ARM/startup_stm32f103xe.s 

OBJS += \
./MDK-ARM/startup_stm32f103xe.o 

S_DEPS += \
./MDK-ARM/startup_stm32f103xe.d 


# Each subdirectory must supply rules for building sources it contributes
MDK-ARM/%.o: ../MDK-ARM/%.s MDK-ARM/subdir.mk
	arm-none-eabi-gcc -mcpu=cortex-m3 -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc" -x assembler-with-cpp -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@" "$<"

clean: clean-MDK-2d-ARM

clean-MDK-2d-ARM:
	-$(RM) ./MDK-ARM/startup_stm32f103xe.d ./MDK-ARM/startup_stm32f103xe.o

.PHONY: clean-MDK-2d-ARM

