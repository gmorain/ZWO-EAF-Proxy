// Shared base for the ASCII-over-serial focusers. All three backends speak a
// terminated ASCII dialect over a UART; only the framing and verbs differ.
#pragma once

#include <Arduino.h>

#include "focuser.h"

class SerialFocuser : public Focuser {
 public:
  SerialFocuser(HardwareSerial& port, uint32_t baud) : port_(port), baud_(baud) {}

 protected:
  HardwareSerial& port_;
  uint32_t baud_;
};
