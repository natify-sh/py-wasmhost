#include "ga/a.h"
#define P(x) a_##x
#include "common.h"
uint32_t exports_demo_m_app_run(void) { say("A-text-ALPHA"); uint32_t r = demo_m_math_add(40, 2); say("A-after-add"); return r; }
