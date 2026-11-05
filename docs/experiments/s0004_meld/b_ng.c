#include "arena.h"
#include "gb/b.h"
#define P(x) b_##x
#include "common.h"
uint32_t exports_demo_m_math_add(uint32_t a, uint32_t b) { say("B-text-BRAVO"); return a + b; }
