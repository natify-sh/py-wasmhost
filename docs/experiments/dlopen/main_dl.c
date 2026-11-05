#include <stdio.h>
#include <dlfcn.h>
/* the real libc names, bound to host imports instead of the weak stubs of libdl.a */
void *dlopen(const char*, int) __attribute__((import_module("env"),import_name("dlopen")));
void *dlsym(void*, const char*) __attribute__((import_module("env"),import_name("dlsym")));
char *dlerror(void) __attribute__((import_module("env"),import_name("dlerror")));
int main(void){
  void *h = dlopen("side_libc.so", RTLD_NOW);
  if(!h){ printf("dlopen failed: %s\n", dlerror()); return 2; }
  int (*f)(const char*) = dlsym(h,"side_libc");
  return f("hello via real dlopen") == 42 ? 0 : 1; }
