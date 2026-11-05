/* The few libc++ symbols that py-ballisticcalc_exts (C++, no exceptions) imports from the main module.
   Written in C with the Itanium-mangled names; single-threaded, so the recursive mutex is a no-op. */
#include <stdlib.h>
void *_Znwm(unsigned long n) { void *p = malloc(n ? n : 1); if (!p) abort(); return p; }
void *_ZnwmRKSt9nothrow_t(unsigned long n, const void *t) { (void)t; return malloc(n ? n : 1); }
void _ZdlPv(void *p) { free(p); }
void _ZdlPvm(void *p, unsigned long n) { (void)n; free(p); }
char _ZSt7nothrow;
void *_ZNSt3__215recursive_mutexC1Ev(void *m) { return m; } /* wasm C++ ABI: constructors and destructors return this */
void *_ZNSt3__215recursive_mutexD1Ev(void *m) { return m; }
void _ZNSt3__215recursive_mutex4lockEv(void *m) { (void)m; }
void _ZNSt3__215recursive_mutex6unlockEv(void *m) { (void)m; }
/* std::__sort<std::__less<double,double>&, double*>(first, last, comp) */
void _ZNSt3__26__sortIRNS_6__lessIddEEPdEEvT0_S5_T_(double *a, double *b, void *cmp) {
  (void)cmp;
  for (double *i = a + 1; i < b; i++) { double v = *i, *j = i; while (j > a && v < j[-1]) { *j = j[-1]; j--; } *j = v; }
}
void __cxa_pure_virtual(void) { abort(); }
