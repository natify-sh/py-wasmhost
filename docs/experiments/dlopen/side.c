extern int main_add(int,int);
extern int main_counter;               /* GOT.mem import */
static int table_val = 7;
int side_counter = 100;
int *side_ptr = &side_counter;        /* data relocation */
int (*side_cb)(int,int) = main_add;   /* GOT.func data reloc */
int side_add(int a,int b){ return a+b+*side_ptr; }
int side_call_main(int a,int b){ return side_cb(a,b) + table_val; }
int side_direct(int a){ return main_add(a,1000); }   /* env.main_add func import */
int side_read_main_counter(void){ return main_counter; }
int side_stack(int n){ volatile char buf[64]; for(int i=0;i<64;i++) buf[i]=i+n; int s=0; for(int i=0;i<64;i++) s+=buf[i]; return s; }
__attribute__((constructor)) static void ctor(void){ side_counter += 1; }
