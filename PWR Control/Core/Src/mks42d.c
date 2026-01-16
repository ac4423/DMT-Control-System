#include <string.h>
#include <stdio.h>
#include "mks42d.h"
#include "uart_hal.h"
#include "tim.h"

// Static variables
static uint8_t txBuffer[64];
static uint8_t rxBuffer[64];

// Private helper
static inline USART_TypeDef* MKS_BUS(void) { return USART1; }

uint8_t getCheckSum(uint8_t *buffer, uint8_t size) {
    uint16_t sum = 0;
    for (uint8_t i = 0; i < size; i++) sum += buffer[i];
    return (uint8_t)(sum & 0xFF);
}

void goHome(uint8_t slaveAddr) {
    UartHAL_FlushRx(MKS_BUS());
    
    txBuffer[0] = 0xFA;          // Frame header
    txBuffer[1] = slaveAddr;     // Slave address
    txBuffer[2] = 0x91;          // GoHome Function Code
    txBuffer[3] = getCheckSum(txBuffer, 3); // Checksum
    
    UartHAL_Send(MKS_BUS(), txBuffer, 4);
}

uint8_t readGoHomeFinishAck(void)
{
    uint8_t Rx_total = UartHAL_RxAvailable(MKS_BUS());
    if (Rx_total < 5) return 0; // Frame is 5 bytes

    uint8_t success_cnt = 0;
    uint8_t buffer[5];
    uint16_t checksum = 0;

    for (uint8_t i = 0; i < Rx_total; i++) {
        uint8_t temp = UartHAL_Read(MKS_BUS());

        // State 0: Frame Header (FB)
        if (success_cnt == 0 && temp == 0xFB) {
            buffer[0] = temp;
            checksum = temp;
            success_cnt = 1;
            continue;
        }
        // State 1: Slave Address (03)
        if (success_cnt == 1) {
            buffer[1] = temp;
            checksum += temp;
            if (temp != 0x03) { success_cnt = 0; continue; }
            success_cnt = 2;
            continue;
        }
        // State 2: Function Code (91 - GoHome)
        if (success_cnt == 2) {
            buffer[2] = temp;
            checksum += temp;
            if (temp != 0x91) { success_cnt = 0; continue; }
            success_cnt = 3;
            continue;
        }
        // State 3: Status Byte
        if (success_cnt == 3) {
            buffer[3] = temp;
            checksum += temp;
            success_cnt = 4;
            continue;
        }
        // State 4: Checksum Verification
        if (success_cnt == 4) {
            uint8_t receivedChecksum = temp;
            if ((checksum & 0xFF) == receivedChecksum) {
                uint8_t status = buffer[3];
                
                // Status 2: Go home success 
                if (status == 2) return 1; 
                
                // Status 0: Go home fail 
                if (status == 0) return 2;

                // Status 1: Go home start (Busy) - We ignore this if waiting for finish
                // and simply reset to look for the next packet.
            }
            success_cnt = 0;
        }
    }
    return 0; // Not finished yet
}

void speedModeRun(uint8_t slaveAddr, uint8_t dir, uint16_t speed, uint8_t acc) {
    if (speed > 3000) speed = 3000;

    txBuffer[0] = 0xFA;
    txBuffer[1] = slaveAddr;
    txBuffer[2] = 0xF6;
    
    // Byte 4: High bit is direction, lower 4 bits are speed high nibble
    txBuffer[3] = (uint8_t)((dir << 7) | ((speed >> 8) & 0x0F)); 
    // Byte 5: Speed low byte
    txBuffer[4] = (uint8_t)(speed & 0xFF);
    txBuffer[5] = acc;
    txBuffer[6] = getCheckSum(txBuffer, 6);

    UartHAL_Send(MKS_BUS(), txBuffer, 7);
}

void speedModeStop(uint8_t slaveAddr, uint8_t acc) {
    txBuffer[0] = 0xFA;
    txBuffer[1] = slaveAddr;
    txBuffer[2] = 0xF6;
    txBuffer[3] = 0x00; // Dir/Speed high 0
    txBuffer[4] = 0x00; // Speed low 0
    txBuffer[5] = acc;  // Acceleration (Deceleration rate)
    txBuffer[6] = getCheckSum(txBuffer, 6);

    UartHAL_Send(MKS_BUS(), txBuffer, 7);
}

void positionMode1Run(uint8_t slaveAddr, uint8_t dir, uint16_t speed, uint8_t acc, uint32_t pulses) {
    if (speed > 3000) speed = 3000;

    txBuffer[0] = 0xFA;
    txBuffer[1] = slaveAddr;
    txBuffer[2] = 0xFD;
    // Byte 4: Dir + Speed High Nibble
    txBuffer[3] = (uint8_t)((dir << 7) | ((speed >> 8) & 0x0F));
    // Byte 5: Speed Low Byte
    txBuffer[4] = (uint8_t)(speed & 0xFF);
    txBuffer[5] = acc;
    
    // Bytes 7-10: Pulses (uint32_t Big Endian)
    txBuffer[6] = (uint8_t)((pulses >> 24) & 0xFF);
    txBuffer[7] = (uint8_t)((pulses >> 16) & 0xFF);
    txBuffer[8] = (uint8_t)((pulses >> 8)  & 0xFF);
    txBuffer[9] = (uint8_t)( pulses        & 0xFF);
    
    txBuffer[10] = getCheckSum(txBuffer, 10);

    UartHAL_Send(MKS_BUS(), txBuffer, 11);
}

void positionMode2Run(uint8_t slaveAddr, uint16_t speed, uint8_t acc, int32_t absPulses) {
    if (speed > 3000) speed = 3000;

    txBuffer[0] = 0xFA;
    txBuffer[1] = slaveAddr;
    txBuffer[2] = 0xFE;
    
    // Byte 4-5: Speed (16-bit, no direction bit mixing here per Manual Page 38)
    txBuffer[3] = (uint8_t)((speed >> 8) & 0xFF);
    txBuffer[4] = (uint8_t)(speed & 0xFF);
    
    txBuffer[5] = acc;
    
    // Bytes 7-10: Absolute Pulses (int32_t Big Endian)
    txBuffer[6] = (uint8_t)((absPulses >> 24) & 0xFF);
    txBuffer[7] = (uint8_t)((absPulses >> 16) & 0xFF);
    txBuffer[8] = (uint8_t)((absPulses >> 8)  & 0xFF);
    txBuffer[9] = (uint8_t)( absPulses        & 0xFF);
    
    txBuffer[10] = getCheckSum(txBuffer, 10);

    UartHAL_Send(MKS_BUS(), txBuffer, 11);
}

void readStepperPosTx(uint8_t slaveAddr) {
    UartHAL_FlushRx(MKS_BUS());
    txBuffer[0] = 0xFA;          // Frame header
    txBuffer[1] = slaveAddr;      // Slave address
    txBuffer[2] = 0x31;           // Position read command
    txBuffer[3] = getCheckSum(txBuffer, 3); // Checksum (FA + Addr + 30)
    
    UartHAL_Send(MKS_BUS(), txBuffer, 4);
}

void readStepperSpeedTx(uint8_t slaveAddr) {
    UartHAL_FlushRx(MKS_BUS());
    txBuffer[0] = 0xFA;          // Frame header
    txBuffer[1] = slaveAddr;      // Slave address
    txBuffer[2] = 0x32;           // Speed read command
    txBuffer[3] = getCheckSum(txBuffer, 3); // Checksum (FA + Addr + 32)
    
    UartHAL_Send(MKS_BUS(), txBuffer, 4);
}

uint8_t readStepperPos(int64_t *outPos)
{
    // We need at least 10 bytes for a full response frame
    // Frame format: FB 01 31 [6 bytes data] [CRC]
    uint8_t rxCount = UartHAL_RxAvailable(MKS_BUS());
    if (rxCount < 10) return 0;

    // State machine variables
    static uint8_t state = 0;
    static uint8_t checksum = 0;
    static uint8_t dataBytes[6];
    
    // Process all available bytes
    for (uint8_t i = 0; i < rxCount; i++) {
        uint8_t byte = UartHAL_Read(MKS_BUS());

        switch (state) {
            case 0: // Header check
                if (byte == 0xFB) {
                    state = 1;
                    checksum = byte;
                }
                break;

            case 1: // ID check (Hardcoded to 0x01)
                if (byte == 0x03) {
                    state = 2;
                    checksum += byte;
                } else {
                    state = 0; // Reset if ID doesn't match
                }
                break;

            case 2: // Function Code check (0x31 = Read Position)
                if (byte == 0x31) {
                    state = 3;
                    checksum += byte;
                } else {
                    state = 0; // Reset if not the expected function
                }
                break;

            // Capture 6 bytes of Position Data (int48_t)
            case 3:
            case 4:
            case 5:
            case 6:
            case 7:
            case 8:
                dataBytes[state - 3] = byte;
                checksum += byte;
                state++;
                break;

            case 9: // Checksum Verification
                if (byte == (checksum & 0xFF)) {
                    // Packet Valid - Parse Data
                    int64_t tempPos = 0;

                    // Combine 6 bytes (Big Endian)
                    for (int j = 0; j < 6; j++) {
                        tempPos = (tempPos << 8) | dataBytes[j];
                    }

                    // Handle 48-bit Sign Extension to 64-bit
                    // If the 48th bit (0x800000000000) is 1, it's negative.
                    if (tempPos & 0x800000000000) {
                        tempPos |= 0xFFFF000000000000;
                    }

                    // Update output variable
                    if (outPos != NULL) {
                        *outPos = tempPos;
                    }
                    
                    // Optional: Toggle debug LED like original code
                    // HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_5);
                    
                    state = 0; // Reset for next packet
                    return 1;  // Success
                }
                
                state = 0; // Checksum failed, reset
                break;
                
            default:
                state = 0;
                break;
        }
    }

    return 0; // No complete packet found in this batch
}