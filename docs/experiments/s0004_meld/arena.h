/* grow-free allocator: a static bump arena, so no memory.grow is linked */
#include <stddef.h>
#include <stdint.h>
static unsigned char arena[16384]; static size_t arena_used;
__attribute__((__export_name__("cabi_realloc")))
void *cabi_realloc(void *ptr, size_t old_size, size_t align, size_t new_size) {
  if (new_size == 0) return (void*)align;
  size_t at = (arena_used + align - 1) & ~(align - 1);
  if (at + new_size > sizeof arena) __builtin_trap();
  arena_used = at + new_size;
  if (ptr && old_size) __builtin_memcpy(arena + at, ptr, old_size < new_size ? old_size : new_size);
  return arena + at;
}
void free(void *p) { (void)p; }
