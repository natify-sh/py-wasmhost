#include <Python.h>
static PyObject *foo_add(PyObject *self, PyObject *args) {
    long a, b;
    if (!PyArg_ParseTuple(args, "ll", &a, &b)) return NULL;
    return PyLong_FromLong(a + b);
}
static PyObject *foo_greet(PyObject *self, PyObject *args) {
    const char *name;
    if (!PyArg_ParseTuple(args, "s", &name)) return NULL;
    return PyUnicode_FromFormat("hello, %s, from a side module", name);
}
static PyMethodDef methods[] = {
    {"add", foo_add, METH_VARARGS, "add two ints"},
    {"greet", foo_greet, METH_VARARGS, "greet"},
    {NULL, NULL, 0, NULL}};
static struct PyModuleDef moddef = {PyModuleDef_HEAD_INIT, "foo", "a side module", -1, methods};
PyMODINIT_FUNC PyInit_foo(void) { return PyModule_Create(&moddef); }
