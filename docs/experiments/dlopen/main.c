#include <stdio.h>
#include <stdlib.h>
__attribute__((import_module("env"),import_name("dl_open"))) void *dl_open(const char*);
__attribute__((import_module("env"),import_name("dl_sym"))) void *dl_sym(void*, const char*);
int main_counter = 5;
__attribute__((visibility("default"),used)) int main_add(int a,int b){ main_counter++; return a+b; }
int main(void){
  void *h = dl_open("side.so");
  printf("handle=%p\n", h);
  #define F(name) int (*name)() = dl_sym(h, #name); printf(#name "=%p\n", (void*)name);
  F(side_add) F(side_call_main) F(side_direct) F(side_read_main_counter) F(side_stack)
  printf("side_add(1,2)=%d (expect 103)\n", side_add(1,2));
  printf("side_call_main(3,4)=%d (expect 14)\n", side_call_main(3,4));
  printf("side_direct(5)=%d (expect 1005)\n", side_direct(5));
  printf("main_counter via side=%d (main sees %d)\n", side_read_main_counter(), main_counter);
  printf("side_stack(1)=%d\n", side_stack(1));
  return 0;
}
