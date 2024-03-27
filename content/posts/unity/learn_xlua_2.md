---
title: '【xlua】引入 & 实现第三方库'
date: 2024-03-26T20:15:49+08:00
draft: false
categories:
    - Unity
tags:
    - Unity
    - XLua
---
使用Lua开发过程中经常需要使用第三方库扩展lua的能力, 这篇文章介绍如何引入 & 实现第三方库
<!--more-->





写这篇文章的目标主要是想要探索一下，lua的第三方库是如何实现的，lua和c++之间的交互是如何实现的。在此基础上，会简单介绍相关的使用方法。



# 一、在纯lua项目中引入第三方库

我们首先抛开XLua，看看纯lua项目中如何使用第三方库。



## 1. 理解lua的编译

首先把lua的仓库clone下来观察：https://github.com/lua/lua

观察其makefile文件，可以看到：

```makefile
CORE_T=	liblua.a
LUA_T=	lua
LUA_O=	lua.o

ALL_T= $(CORE_T) $(LUA_T)
ALL_O= $(CORE_O) $(LUA_O) $(AUX_O) $(LIB_O)
ALL_A= $(CORE_T)

all:	$(ALL_T)
	touch all

o:	$(ALL_O)

a:	$(ALL_A)

$(CORE_T): $(CORE_O) $(AUX_O) $(LIB_O)
	$(AR) $@ $?
	$(RANLIB) $@

$(LUA_T): $(LUA_O) $(CORE_T)
	$(CC) -o $@ $(MYLDFLAGS) $(LUA_O) $(CORE_T) $(LIBS) $(MYLIBS) $(DL)
```

其中包含两个编译目标：

1. `CORE_T`：`liblua.a`，静态链接库，可以在代码中调用；
2. `LUA_T`：`lua`二进制，可以直接运行，进行交互；



## 2. 使用c++调用lua

在理解上面的内容后，我们就知道接下来要做什么了：需要将`liblua.a`的目标整合进我们的项目中，这样就可以依赖到lua，然后在使用c++调用相关接口即可。

### a. 编写cmake文件:

```cmake
cmake_minimum_required(VERSION 3.27)
project(luavm)

set(CMAKE_CXX_STANDARD 17)

set (CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

set(LIB_LUA_PATH ${CMAKE_SOURCE_DIR}/third_party/lua)
include_directories(${LIB_LUA_PATH})

# 将lua编译为静态链接库.
aux_source_directory(${LIB_LUA_PATH} LIB_LUA_SRC_FILES)
set(LUA_EXEC_FILE_PATH ${LIB_LUA_PATH}/lua.c)
list(REMOVE_ITEM LIB_LUA_SRC_FILES ${LUA_EXEC_FILE_PATH})
add_library(liblua STATIC ${LIB_LUA_SRC_FILES})

add_executable(luavm main.cpp)

# 编译可执行文件时, 链接编译好的静态链接库.
find_library(liblua ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY})
target_link_libraries(luavm liblua)

```



### b. 编写c++代码调用lua

这个过程和`xlua`中使用基本一致，不同点在于`xlua`将栈的操作封装好了，`c++`访问原生lua接口时，需要我们自己操控栈：

```c++
#include <iostream>

extern "C" {
#include "lauxlib.h"
}

static const std::string kLuaCode = R"(
function add(a, b)
    return a + b
end
)";

int main() {
    lua_State *L = luaL_newstate();
    luaL_dostring(L, kLuaCode.c_str());

    lua_getglobal(L, "add");
    lua_pushnumber(L, 10);
    lua_pushnumber(L, 20);

    if (int ret = lua_pcall(L, 2, 1, 0); ret != 0) {
        std::cout << "error, " << lua_tostring(L, -1) << std::endl;
        return -1;
    }

    std::cout << "lua a + b result = " << lua_tonumber(L, -1) << std::endl;

    lua_pop(L, -1);

    return 0;
}
```



### c. 编译运行

直接使用`cmake`编译运行即可得到结果：

<center>
	<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240326165628159.png" alt="image-20240326165628159" style="zoom:50%;" />
    <p>
        <b>图1： 运行lua a+b</b>
    </p>
</center>



## 3. 引入第三方库

我们尝试将`lua-rapidjson`引入到项目中：https://github.com/xpol/lua-rapidjson



### a. 观察lua-rapidjson的cmake文件

```cmake
include_directories(${LUA_INCLUDE_DIR} ${RAPIDJSON_INCLUDE_DIRS})

set(SOURCES
    src/Document.cpp
    src/Schema.cpp
    src/Userdata.hpp
    src/file.hpp
    src/luax.hpp
    src/rapidjson.cpp
    src/values.cpp
    src/values.hpp
)

add_library(lua-rapidjson MODULE ${SOURCES})
```

可以看到，其核心部分如上文所示，就是找到`LUA_INCLUDE_DIR`与`RAPIDJSON_INCLUDE_DIRS`，将其作为`include dir`进行设置，然后直接编译几个`cpp`与`hpp`文件，编译为`lib`。



### b. 将 lua-rapidjson 迁移进原有的项目中

了解原理后就非常简单了，直接添加一个动态链接库即可：

```cmake
cmake_minimum_required(VERSION 3.27)
project(luavm)

set(CMAKE_CXX_STANDARD 17)

set (CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

set(LIB_LUA_PATH ${CMAKE_SOURCE_DIR}/third_party/lua)
set(LIB_RAPID_JSON_PATH ${CMAKE_SOURCE_DIR}/third_party/lua-rapidjson/rapidjson/include)
set(LIB_LUA_RAPID_JSON_PATH ${CMAKE_SOURCE_DIR}/third_party/lua-rapidjson/src)
include_directories(${LIB_LUA_PATH})
include_directories(${LIB_RAPID_JSON_PATH})
include_directories(${LIB_LUA_RAPID_JSON_PATH})

# 将lua编译为静态链接库.
aux_source_directory(${LIB_LUA_PATH} LIB_LUA_SRC_FILES)
set(LUA_EXEC_FILE_PATH ${LIB_LUA_PATH}/lua.c)
list(REMOVE_ITEM LIB_LUA_SRC_FILES ${LUA_EXEC_FILE_PATH})
add_library(liblua STATIC ${LIB_LUA_SRC_FILES})

# 将lua-rapidjson编译为静态链接库
aux_source_directory(${LIB_LUA_RAPID_JSON_PATH} LIB_LUA_RAPID_JSON_SRC_FILES)
add_library(lib_lua_rapidjson STATIC ${LIB_LUA_RAPID_JSON_SRC_FILES})

add_executable(luavm main.cpp)

# 编译可执行文件时, 链接编译好的静态链接库.
find_library(liblua ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY})
find_library(lib_lua_rapidjson ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY})
target_link_libraries(luavm liblua lib_lua_rapidjson)
```

同时，需要添加一个`lua.hpp`到`lua-rapidjson`项目中：

```c++
#ifndef lua_hpp
#define lua_hpp

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
};

#endif
```



### c. 修改c++代码 & lua代码进行验证

查看`rapidjson`可以看到其注册的函数：

```c++

LUALIB_API int luaopen_rapidjson(lua_State* L)
{
	lua_newtable(L); // [rapidjson]

	luax::setfuncs(L, methods); // [rapidjson]

	lua_pushliteral(L, "rapidjson"); // [rapidjson, name]
	lua_setfield(L, -2, "_NAME"); // [rapidjson]

	lua_pushliteral(L, LUA_RAPIDJSON_VERSION); // [rapidjson, version]
	lua_setfield(L, -2, "_VERSION"); // [rapidjson]

    values::push_null(L); // [rapidjson, json.null]
    lua_setfield(L, -2, "null"); // [rapidjson]

	createSharedMeta(L, "json.object", "object");
	createSharedMeta(L, "json.array", "array");

	Userdata<Document>::luaopen(L);
	Userdata<SchemaDocument>::luaopen(L);
	Userdata<SchemaValidator>::luaopen(L);

	return 1;
}
```

我们可以模仿`luaL_openlibs`中注册标准库的操作：

```c++
/*
** require and preload selected standard libraries
*/
LUALIB_API void luaL_openselectedlibs (lua_State *L, int load, int preload) {
  int mask;
  const luaL_Reg *lib;
  luaL_getsubtable(L, LUA_REGISTRYINDEX, LUA_PRELOAD_TABLE);
  for (lib = stdlibs, mask = 1; lib->name != NULL; lib++, mask <<= 1) {
    if (load & mask) {  /* selected? */
      luaL_requiref(L, lib->name, lib->func, 1);  /* require library */
      lua_pop(L, 1);  /* remove result from the stack */
    }
    else if (preload & mask) {  /* selected? */
      lua_pushcfunction(L, lib->func);
      lua_setfield(L, -2, lib->name);  /* add library to PRELOAD table */
    }
  }
  lua_assert((mask >> 1) == LUA_UTF8LIBK);
  lua_pop(L, 1);  /* remove PRELOAD table */
}
```

直接对每一个想要引用的库调用`luaL_requiref`即可。

我们需要在c++代码中调用`luaopen_rapidjson`函数，来对`rapidjson`库进行注册，然后再在lua中对其进行调用：

```c++
#include <iostream>

extern "C" {
#include "lauxlib.h"
#include "lualib.h"
}

extern "C" {
LUALIB_API int luaopen_rapidjson(lua_State *L);
}


static const std::string kLuaCode = R"(
function get_raw_json()
    local rapidjson = require('rapidjson')
    print(rapidjson)
    return rapidjson.encode({a=1, b=2.1, c='', d=false}, {sort_keys=true})
end
)";


int main() {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    luaL_requiref(L, "rapidjson", luaopen_rapidjson, 0);

    luaL_dostring(L, kLuaCode.c_str());

    lua_getglobal(L, "get_raw_json");

    if (int ret = lua_pcall(L, 0, 1, 0); ret != 0) {
        std::cout << "error, " << lua_tostring(L, -1) << std::endl;
        return -1;
    }

    std::cout << "get raw json result = " << lua_tostring(L, -1) << std::endl;

    lua_pop(L, -1);

    return 0;
}
```

可以观察到输出：

```shell
get raw json result = {"a":1,"b":2.1,"c":"","d":false}
```





# 二、实现一个自己的第三方库

## 1. 从一个最简单的case开始



### a. 新建文件，加入工程

首先我们搭出来一个架子，我们模仿`rapidjson`的结构来一个：

**mylib.cpp**

```c++
#include <iostream>

extern "C" {
#include "lauxlib.h"
#include "lualib.h"
}

// ... 待实现库的逻辑.
```



**cmakelists.txt**

```cmake
# 将自己写的 mylib 编译为静态链接库.
add_library(mylib STATIC ${CMAKE_SOURCE_DIR}/mylib.cpp)

# 编译可执行文件时, 链接编译好的静态链接库.
find_library(mylib ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY})
target_link_libraries(luavm liblua rapidjson mylib)
```

在原有项目的基础上，添加自己写的库。



### b. 认识lua库

我们想要实现一个非常简单的库：

```lua
local mylib = require("mylib")

result = mylib.add(10, 20)
print(result)
```

希望能够实现一个`mylib`，这个`mylib`有一个`add`方法，可以对数字进行求和操作。



为了完成这个目标，我们这里需要讨论两个问题：

1. 我们在进行`require`的时候，到底`require`到了一个什么东西。
2. c++怎么写lua的函数？



**c++怎么写lua函数？**

首先需要完成函数的定义：

```c++
static int xxx (lua_State *L) {
}
```

这里就涉及到两个问题：

- 接受参数
- 返回内容



对于参数的接收，lua在进行函数调用时，与汇编类似，会将参数一个一个压入栈中，我们可以用`lua_tonumber`这样的方法，配合上基于栈的偏移来获取到指定的元素。

对于内容的返回，通过`lua_pushxxx`的方法就可以将返回值压入栈中，随后根据c++`return`的数字，来确认返回参数的个数，就可以完成函数的返回。





**require的机制**

正如上一节中讨论的一样，在`lua`中`require`一个库的时候，实际上是在调用这个库的`luaopen_xxx`方法，以`math`库为例：

```C++
static const luaL_Reg mathlib[] = {
  {"abs",   math_abs},
  {"acos",  math_acos},
  {"asin",  math_asin},
  //.. 中间忽略
};

/*
** Open math library
*/
LUAMOD_API int luaopen_math (lua_State *L) {
  luaL_newlib(L, mathlib);
  lua_pushnumber(L, PI);
  lua_setfield(L, -2, "pi");
  lua_pushnumber(L, (lua_Number)HUGE_VAL);
  lua_setfield(L, -2, "huge");
  lua_pushinteger(L, LUA_MAXINTEGER);
  lua_setfield(L, -2, "maxinteger");
  lua_pushinteger(L, LUA_MININTEGER);
  lua_setfield(L, -2, "mininteger");
  setrandfunc(L);
  return 1;
}
```



这是一个`c++`实现的`lua`函数，函数的返回值表示函数返回参数的个数。这里`luaL_newlib`时，会入栈一个`table`，并且将`mathlib`这个数组中的所有方法设入`table`中。接下来，不断地使用`setfield`方法，向`table`设置参数，最后调用`setrandfunc`继续设置`rand`相关的部分。



返回的table应该类似于：

```lua
{
    "abs": function() end,
    "acos": function() end,
    "asin": function() end,
    "pi": PI,
    "huge": HUGE_VAL,
    "maxinteger": LUA_MAXINTEGER,
    "mininteger": LUA_MININTEGER
}
```

这样用户使用`local math = require('math')`进行接收时，就接收到了一个`table`，在此基础上，就可以通过`math.abs`, `math.pi`对里面的内容进行指定。





### c. 实现一个最简单的lua库

有了上面的积累，我们可以实现出一个非常简单的lua库：

```c++
#include <iostream>

extern "C" {
#include "lauxlib.h"
#include "lualib.h"
}

static int mylib_add(lua_State* L) {
    lua_pushnumber(L, luaL_checknumber(L, -1) +luaL_checknumber(L, -2));
    return 1;
}


static const luaL_Reg my_lib[] = {
        {"add", mylib_add},
        {nullptr, nullptr}
};

int luaopen_mylib(lua_State* L)
{
    luaL_newlib(L, my_lib);
    return 1;
}
```





随后在刚才的主程序中，添加代码：

```c++
#include <iostream>

extern "C" {
#include "lauxlib.h"
#include "lualib.h"
}

extern "C" {
LUALIB_API int luaopen_rapidjson(lua_State *L);
}


static const std::string kLuaCode = R"(
function get_raw_json()
    local rapidjson = require('rapidjson')
    return rapidjson.encode({a=1, b=2.1, c='', d=false}, {sort_keys=true})
end

local mylib = require('mylib')
mylib_test_result = mylib.add(20, 40)
)";


LUALIB_API int luaopen_mylib(lua_State* L);

int main() {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);

    luaL_requiref(L, "rapidjson", luaopen_rapidjson, 0);
    lua_pop(L, 1);

    luaL_requiref(L, "mylib", luaopen_mylib, 0);
    lua_pop(L, 1);

    luaL_dostring(L, kLuaCode.c_str());

    lua_getglobal(L, "get_raw_json");

    if (int ret = lua_pcall(L, 0, 1, 0); ret != 0) {
        std::cout << "error, " << lua_tostring(L, -1) << std::endl;
        return -1;
    }

    std::cout << "get raw json result = " << lua_tostring(L, -1) << std::endl;
    lua_pop(L, -1);


    lua_getglobal(L, "mylib_test_result");
    std::cout << "mylib_test_result = " << luaL_checknumber(L, -1) << std::endl;
    lua_pop(L, -1);

    return 0;
}
```



运行后，即可观察到结果：

> ```shell
> get raw json result = {"a":1,"b":2.1,"c":"","d":false}
> mylib_test_result = 60
> ```



