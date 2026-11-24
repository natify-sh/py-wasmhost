typedef unsigned int u32;
enum color { RED, GREEN = 5, BLUE };
typedef struct node { int value; enum color c; struct node *next; } node_t;
typedef int (*cb_t)(int);
int add(int a, int b) { return a + b; }
int apply(cb_t f, int x) { return f(x); }
u32 sum_list(const node_t *n) { u32 s = 0; while (n) { s += n->value; n = n->next; } return s; }
