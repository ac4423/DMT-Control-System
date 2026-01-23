######################################
# Project configuration
######################################

TARGET = firmware
BUILD_DIR = build

MCU = cortex-m3

######################################
# Toolchain
######################################

CC = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
SIZE = arm-none-eabi-size

######################################
# Source files (auto-discovered)
######################################

SRC = $(wildcard Core/Src/*.c)
SRC += $(wildcard Drivers/STM32F1xx_HAL_Driver/Src/*.c)
SRC += Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/system_stm32f1xx.c
SRC += Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.s

# USB middleware (from Keil)
SRC += $(wildcard Middlewares/ST/STM32_USB_Device_Library/Core/Src/*.c)
SRC += $(wildcard Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/*.c)
SRC += $(wildcard USB_DEVICE/App/*.c)
SRC += $(wildcard USB_DEVICE/Target/*.c)

######################################
# Include paths (from Keil)
######################################

INC = \
-ICore/Inc \
-IDrivers/STM32F1xx_HAL_Driver/Inc \
-IDrivers/STM32F1xx_HAL_Driver/Inc/Legacy \
-IDrivers/CMSIS/Include \
-IDrivers/CMSIS/Device/ST/STM32F1xx/Include \
-IMiddlewares/ST/STM32_USB_Device_Library/Core/Inc \
-IMiddlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc \
-IUSB_DEVICE/App \
-IUSB_DEVICE/Target

######################################
# Flags
######################################

CFLAGS = -mcpu=$(MCU) -mthumb -Wall -O2 -g
CFLAGS += $(INC)
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -DSTM32F103xE -DUSE_HAL_DRIVER

LDFLAGS = -TSTM32F103ZE.ld
LDFLAGS += -Wl,--gc-sections
LDFLAGS += -lc -lm -lnosys

######################################
# Build rules
######################################

ELF = $(BUILD_DIR)/$(TARGET).elf
BIN = $(BUILD_DIR)/$(TARGET).bin

all: $(BIN)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(ELF): $(SRC) | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(SRC) $(LDFLAGS) -o $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@
	$(SIZE) $<

flash: $(BIN)
	st-flash write $(BIN) 0x08000000

clean:
	rm -rf $(BUILD_DIR)
