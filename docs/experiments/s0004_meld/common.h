#include <string.h>
#include <stdlib.h>
static void say(const char *prefix) {
    /* get-arguments (list<string>: needs cabi_realloc + memory), then write prefix + argc + args to stdout */
    P(list_string_t) args; wasi_cli_environment_get_arguments(&args);
    char buf[256]; size_t n = 0;
    size_t pl = strlen(prefix); memcpy(buf, prefix, pl); n = pl;
    buf[n++] = ' '; buf[n++] = '0' + (char)args.len;
    for (size_t i = 0; i < args.len && n < 200; i++) { buf[n++] = ' '; memcpy(buf+n, args.ptr[i].ptr, args.ptr[i].len); n += args.ptr[i].len; }
    buf[n++] = '\n';
    P(list_u8_t) c = {(uint8_t*)buf, n};
    wasi_io_streams_borrow_output_stream_t o = {wasi_cli_stdout_get_stdout().__handle};
    wasi_io_streams_stream_error_t e;
    wasi_io_streams_method_output_stream_blocking_write_and_flush(o, &c, &e);
    P(list_string_free)(&args);
}
