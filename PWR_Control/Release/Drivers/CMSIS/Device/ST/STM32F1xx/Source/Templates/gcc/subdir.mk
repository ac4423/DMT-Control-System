################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
S_SRCS += \
../Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.s 

OBJS += \
./Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.o 

S_DEPS += \
./Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/%.o: ../Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/%.s Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/subdir.mk
	arm-none-eabi-gcc -mcpu=cortex-m3 -c -I"C:/Users/andre/Documents/ME3/DMT/DMT-Control-System/PWR_Control/Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc" -x assembler-with-cpp -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfloat-abi=soft -mthumb -o "$@" "$<"

clean: clean-Drivers-2f-CMSIS-2f-Device-2f-ST-2f-STM32F1xx-2f-Source-2f-Templates-2f-gcc

clean-Drivers-2f-CMSIS-2f-Device-2f-ST-2f-STM32F1xx-2f-Source-2f-Templates-2f-gcc:
	-$(RM) ./Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.d ./Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.o

.PHONY: clean-Drivers-2f-CMSIS-2f-Device-2f-ST-2f-STM32F1xx-2f-Source-2f-Templates-2f-gcc

