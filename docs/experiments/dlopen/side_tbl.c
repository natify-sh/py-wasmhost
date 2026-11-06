typedef struct { const char *name; int (*fn)(int); } Meth;   /* like PyMethodDef: strings and fn pointers in data */
static int dbl(int x){ return 2*x; }
static int sq(int x){ return x*x; }
static const Meth methods[] = { {"dbl", dbl}, {"sq", sq}, {0,0} };
__attribute__((visibility("default"))) const Meth *PyInit_demo(void){ return methods; }
