#include <stdbool.h>
typedef void (*code_func_t)();
typedef void code;
void test(void) {
    int addr = 0x1234;
    ((code_func_t)(addr))(1, 2, 3);
}
