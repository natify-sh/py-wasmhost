#![no_std]
#[repr(C)] #[derive(Clone, Copy)] pub enum Color { Red, Green = 5, Blue }
pub type U32 = u32;
#[repr(C)] pub struct Node { pub value: i32, pub c: Color, pub next: *const Node }
#[no_mangle] pub extern "C" fn add(a: i32, b: i32) -> i32 { a.wrapping_add(b) }
#[no_mangle] pub extern "C" fn apply(f: extern "C" fn(i32) -> i32, x: i32) -> i32 { f(x) }
#[no_mangle] pub unsafe extern "C" fn sum_list(mut n: *const Node) -> U32 {
    let mut s: U32 = 0; while !n.is_null() { s = s.wrapping_add((*n).value as u32); n = (*n).next; } s }
#[no_mangle] pub extern "C" fn len_of(s: &str) -> usize { s.len() }
#[no_mangle] pub extern "C" fn first(s: &[u8]) -> u8 { if s.is_empty() { 0 } else { s[0] } }
#[panic_handler] fn panic(_: &core::panic::PanicInfo) -> ! { loop {} }
