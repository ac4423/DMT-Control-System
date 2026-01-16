#ifndef MKS42D_H
#define MKS42D_H

#include <stdint.h>

// Function prototypes - KEEP IT SIMPLE BUT KEEP MULTI-READ/WRITE
uint8_t getCheckSum(uint8_t *buffer, uint8_t size);
void goHome(uint8_t slaveAddr);
uint8_t readGoHomeFinishAck(void);

void speedModeRun(uint8_t slaveAddr, uint8_t dir, uint16_t speed, uint8_t acc);
void speedModeStop(uint8_t slaveAddr, uint8_t acc);
void positionMode1Run(uint8_t slaveAddr, uint8_t dir, uint16_t speed, uint8_t acc, uint32_t pulses);
void positionMode2Run(uint8_t slaveAddr, uint16_t speed, uint8_t acc, int32_t absPulses);


void readStepperPosTx(uint8_t slaveAddr);
void readStepperSpeedTx(uint8_t slaveAddr);
uint8_t readStepperPos(int64_t *outPos);

#endif