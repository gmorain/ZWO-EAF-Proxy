// A focuser that exists only in memory, so the persona can be exercised with
// nothing attached. Movement is integrated from a caller-supplied clock.
#pragma once

#include "focuser.h"

class SimulatedFocuser : public Focuser {
 public:
  SimulatedFocuser(int32_t position, int32_t steps_per_second, int32_t temperature_centi)
      : position_(position * 1000),
        target_(position),
        rate_(steps_per_second),
        temperature_centi_(temperature_centi) {}

  bool begin() override { return true; }

  int32_t position() override { return position_ / 1000; }

  bool moveTo(int32_t target) override {
    if (target < 0) return false;
    target_ = target;
    return true;
  }

  bool halt() override {
    target_ = position_ / 1000;
    return true;
  }

  bool setPosition(int32_t position) override {
    if (position < 0) return false;
    position_ = static_cast<int64_t>(position) * 1000;
    target_ = position;
    return true;
  }

  bool isMoving() override { return (position_ / 1000) != target_; }

  int32_t maxStep() override { return 0x7FFFFFFF; }

  int32_t temperature() override { return temperature_centi_; }

  // Advance by `elapsed_ms` of travel. Position is held in thousandths of a step
  // so slow rates still make progress between ticks.
  void advance(int32_t elapsed_ms);

  void tick() override {}

 private:
  int64_t position_;  // thousandths of a step
  int32_t target_;
  int32_t rate_;
  int32_t temperature_centi_;
};
