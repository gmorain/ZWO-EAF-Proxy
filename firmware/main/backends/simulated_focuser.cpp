#include "backends/simulated_focuser.h"

void SimulatedFocuser::advance(int32_t elapsed_ms) {
  const int64_t target_milli = static_cast<int64_t>(target_) * 1000;
  const int64_t remaining = target_milli - position_;
  if (remaining == 0) return;

  const int64_t step = static_cast<int64_t>(rate_) * elapsed_ms;
  if (step >= (remaining < 0 ? -remaining : remaining)) {
    position_ = target_milli;
    return;
  }
  position_ += (remaining > 0) ? step : -step;
}
