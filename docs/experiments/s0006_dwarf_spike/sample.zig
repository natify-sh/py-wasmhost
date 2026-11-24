pub const Color = enum(u8) { red, green = 5, blue };
pub const Node = extern struct { value: i32, c: Color, next: ?*Node };
pub const U32 = u32;
export fn add(a: i32, b: i32) i32 { return a + b; }
export fn apply(f: *const fn (i32) callconv(.c) i32, x: i32) i32 { return f(x); }
export fn sum_list(n: ?*const Node) U32 {
    var s: U32 = 0;
    var p = n;
    while (p) |q| { s += @intCast(q.value); p = q.next; }
    return s;
}
