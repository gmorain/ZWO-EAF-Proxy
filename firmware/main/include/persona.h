// A ZWO device emulation presented to the ASIAIR over USB.
#pragma once

class Persona {
 public:
  virtual ~Persona() = default;

  // Configure USB descriptors and start the device stack.
  virtual bool begin() = 0;

  // Service USB traffic. Called from loop().
  virtual void tick() = 0;
};
