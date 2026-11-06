(module
  (import "wasi:cli/exit@0.2.6" "exit" (func $a (param i32)))
  (import "wasi:cli/exit@0.2.6" "exit" (func $b (param i32)))
  (func (export "a") (call $a (i32.const 0)))
  (func (export "b") (call $b (i32.const 0))))
