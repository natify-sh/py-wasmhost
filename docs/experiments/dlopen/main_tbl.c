#include <stdio.h>
#include <dlfcn.h>
typedef struct { const char *name; int (*fn)(int); } Meth;
void *dlopen(const char*, int) __attribute__((import_module("env"),import_name("dlopen")));
void *dlsym(void*, const char*) __attribute__((import_module("env"),import_name("dlsym")));
char *dlerror(void) __attribute__((import_module("env"),import_name("dlerror")));
int main(void){ void *h = dlopen("side_tbl.so", RTLD_NOW); const Meth *(*init)(void) = dlsym(h, "PyInit_demo");
  for (const Meth *m = init(); m->name; m++) printf("%s(7)=%d\n", m->name, m->fn(7)); return 0; }
