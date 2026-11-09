/* The C++ runtime symbols that numpy's two C++ modules import from the main module: real operator new/delete and the
   helpers of libc++ that they use; the exception machinery is stubs (nothing throws on the paths that were run). */
#include <stdlib.h>
#include <stddef.h>
void *_Znwm(size_t n) { void *p = malloc(n ? n : 1); if (!p) abort(); return p; }
void _ZdlPvm(void *p, size_t n) { (void)n; free(p); }
size_t _ZNSt3__212__next_primeEm(size_t n) {
  if (n < 3) return 3;
  for (size_t c = n | 1;; c += 2) { int pr = 1; for (size_t d = 3; d * d <= c; d += 2) if (c % d == 0) { pr = 0; break; } if (pr) return c; }
}
size_t _ZNSt3__213__hash_memoryEPKvm(const void *p, size_t n) {
  const unsigned char *b = p; size_t h = 2166136261u; for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 16777619u; } return h;
}
void *__cxa_allocate_exception(size_t n) { return malloc(n); }
void __cxa_free_exception(void *p) { free(p); }
void __cxa_throw(void *a, void *b, void *c) { (void)a; (void)b; (void)c; abort(); }
void *__cxa_begin_catch(void *p) { return p; }
void __cxa_end_catch(void) {}
int _Unwind_CallPersonality(void *p) { (void)p; abort(); }
void _ZSt9terminatev(void) { abort(); }
void *_ZNSt11logic_errorC2EPKc(void *t, const char *s) { (void)s; return t; }
void *_ZNSt13runtime_errorC1EPKc(void *t, const char *s) { (void)s; return t; }
void *_ZNSt20bad_array_new_lengthC1Ev(void *t) { return t; }
void *_ZNSt9bad_allocC1Ev(void *t) { return t; }
void *_ZNSt12length_errorD1Ev(void *t) { return t; }
void *_ZNSt13runtime_errorD1Ev(void *t) { return t; }
void *_ZNSt20bad_array_new_lengthD1Ev(void *t) { return t; }
void *_ZNSt3__217bad_function_callD1Ev(void *t) { return t; }
void *_ZNSt9bad_allocD1Ev(void *t) { return t; }
void *_ZNSt3__219__shared_weak_countD2Ev(void *t) { return t; }
void _ZNSt3__219__shared_weak_count14__release_weakEv(void *t) { (void)t; }
void *_ZNKSt3__219__shared_weak_count13__get_deleterERKSt9type_info(void *t, const void *i) { (void)t; (void)i; return 0; }
char _ZTVN10__cxxabiv117__class_type_infoE[64], _ZTVN10__cxxabiv120__si_class_type_infoE[64], _ZTINSt3__219__shared_weak_countE[32],
     _ZTVNSt3__217bad_function_callE[64], _ZTVSt12length_error[64];
