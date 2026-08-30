"""Gemini EAF dialect.

Not the Optec Gemini. A ~65 EUR ZWO EAF knockoff: same bracket pattern, same
port layout (TEMP, USB-B, HBX), USB-powered 5V. Ships its own ASCOM driver,
works with NINA and KStars, does not work with the ASIAIR. That last part is
why this project exists, and it means the Gemini does not speak EAF.

USB serial, so it can be probed from the Mac directly. The dialect is unknown;
many clones in this price bracket use a Moonlite-compatible ASCII protocol,
which is worth testing before assuming a custom one.
"""
