#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <stdint.h>

void motor_test(void);
void motor_read(void);
void StepperOscillate_Start(int32_t low_pulses, int32_t high_pulses, uint16_t speed_rpm);
void StepperOscillate_Stop(void);


extern int32_t stepper_pos;

#endif
