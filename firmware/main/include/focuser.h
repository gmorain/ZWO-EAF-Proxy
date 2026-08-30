// Device-type contract between personas and backends. See docs/ARCHITECTURE.md.
#pragma once

#include <stdint.h>

// Returned by backends that cannot answer a query. The persona decides what to
// report upstream rather than the backend inventing a value.
constexpr int32_t kUnsupported = INT32_MIN;

class Focuser {
 public:
  virtual ~Focuser() = default;

  virtual bool begin() = 0;
  virtual int32_t position() = 0;
  virtual bool moveTo(int32_t target) = 0;
  virtual bool halt() = 0;

  // Redefine the current position without moving. The host zeroes a focuser
  // this way; see docs/protocol/registers.md.
  virtual bool setPosition(int32_t position) = 0;
  virtual bool isMoving() = 0;
  virtual int32_t maxStep() = 0;

  // Hundredths of a degree Celsius, or kUnsupported.
  virtual int32_t temperature() { return kUnsupported; }

  // Called from loop(); backends drive their own state machine here.
  virtual void tick() {}
};
