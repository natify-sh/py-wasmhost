#include <stdio.h>
#include <stdlib.h>
#include <string.h>
__attribute__((visibility("default"))) int side_libc(const char *s){ char *p = malloc(strlen(s)+1); strcpy(p,s); printf("side printf: %s (%zu)\n", p, strlen(p)); free(p); return 42; }
