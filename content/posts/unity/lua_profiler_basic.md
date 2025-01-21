---
title: 'Lua Profiler 基本原理'
date: 2024-09-06T10:54:21+08:00
draft: false
categories:
    - Unity
tags:
    - Unity
    - Lua
---
学习`ELuaProfiler`和`Miku-LuaProfiler`，讨论 lua profiler 的前置能力 希望通过学习主流的 lua profiler 的前置能力，来讨论 webgl 平台 lua profiler 的可行性
<!--more-->




学习了两款主流的`lua profiler`：

- [`Miku-LuaProfiler`](https://github.com/leinlin/Miku-LuaProfiler)：unity中常用的`lua profiler`，不支持`webgl`，只支持`windows`, `android`
- [`ELuaProfiler`](https://github.com/inkiu0/ELuaProfiler)：UE中常用的`lua profielr`


想要实现一个`lua profiler`，依赖的核心功能是：

- 内存监控：
  1. 感知内存分配行为；
  2. 统计当前内存总量；
  3. 分别对`Table`, `Function`, `UserData`, `Thread`, `Proto`, `String` 进行精细处理；
- 调用监控：
  1. 感知`lua`的调用行为；
  2. 感知函数退出；


依赖这些功能，就能实现一个最简单的`lua profiler`了。


# 调用感知


## ELuaProfiler


`ELuaProfiler`使用了`lua`原生提供的`hook`能力：

```c++
/*
** Event codes
*/
#define LUA_HOOKCALL  0
#define LUA_HOOKRET 1
#define LUA_HOOKLINE  2
#define LUA_HOOKCOUNT 3
#define LUA_HOOKTAILCALL 4

/*
** Event masks
*/
#define LUA_MASKCALL  (1 << LUA_HOOKCALL)
#define LUA_MASKRET (1 << LUA_HOOKRET)
#define LUA_MASKLINE  (1 << LUA_HOOKLINE)
#define LUA_MASKCOUNT (1 << LUA_HOOKCOUNT)

LUA_API void (lua_sethook) (lua_State *L, lua_Hook func, int mask, int count);
```


`lua`提供了`api`，能通过`lua_sethook`来获取`lua`中发生的一些事件（下表来自于《如何利用LuaHook开发一个健壮的Profiler》）：

|   Lua Hook类型   |                 触发时机                 |
| :--------------: | :--------------------------------------: |
|   LUA_HOOKCALL   |       进入新函数后，函数获取参数前       |
|   LUA_HOOKRET    |               函数返回之前               |
|   LUA_HOOKLINE   |     解释器准备开始执行新的一行代码时     |
|  LUA_HOOKCOUNT   |       解释器每执行完count条指令时        |
| LUA_HOOKTAILCALL | 执行尾调用时，具体时机与LUA_HOOKCALL相同 |


刚才提到的`lua_sethook`函数，可以预定义一个`lua_Hook`的函数，来接收事件，这个函数的声明如下：

```c++
struct lua_Debug {
  int event;
  const char *name; /* (n) */
  const char *namewhat; /* (n) 'global', 'local', 'field', 'method' */
  const char *what; /* (S) 'Lua', 'C', 'main', 'tail' */
  const char *source; /* (S) */
  int currentline;  /* (l) */
  int linedefined;  /* (S) */
  int lastlinedefined;  /* (S) */
  unsigned char nups; /* (u) number of upvalues */
  unsigned char nparams;/* (u) number of parameters */
  char isvararg;        /* (u) */
  char istailcall;  /* (t) */
  char short_src[LUA_IDSIZE]; /* (S) */
  /* private part */
  struct CallInfo *i_ci;  /* active function */
};

/* Functions to be called by the debugger in specific events */
typedef void (*lua_Hook) (lua_State *L, lua_Debug *ar);
```

传入的`lua_Debug`中的`event`字段被设置，用于感知当前发生的事件类型，`hook`函数可以根据`event`的类型来进一步获取信息。


接下来就可以调用`lua_getinfo`来获取当前正在运行中的函数信息：

```c++
lua_getinfo(L, "nS", ar);
```

这样就可以对`ar`中与`"n"`, `"S"`相关的字段进行填充，上层就可以获得正在进行调用的函数的名称、文件名、行号等信息。


如果每次都要重新获取`nS`的话，就会比较慢，`ELuaProfiler`的作者使用`"f"`方法获取函数指针：

```c++
lua_getinfo(L, "f", ar);
const void* luaPtr = lua_topointer(L, -1);
```

使用`Map`缓存`luaPtr`到已经缓存的`ar`信息，这样就不用每次都新开数据了。


## Miku-LuaProfiler

`Miku-LuaProfiler`并没有选择依赖`lua`本身提供的`hook`机制，而是选择使用了原生的`hook`能力

```c#
public interface NativeUtilInterface
{
  IntPtr GetProcAddress(string InPath, string InProcName);
  IntPtr GetProcAddressByHandle(IntPtr InModule, string InProcName);
  void HookLoadLibrary(Action<IntPtr> callBack);
  INativeHooker CreateHook();
}

public interface INativeHooker
{
  void Init(IntPtr targetPtr, IntPtr replacementPtr);
  Delegate GetProxyFun(Type t);
  bool isHooked { get; set; }
  void Install();
  void Uninstall();
}
```

针对不同平台，需要实现：

- `NativeUtilInterface.GetProcAddress`：根据方法名，拿到`targetPtr`，根据`targetPtr`能拿到`INativeHooker`；
- `INativeHooker`：使用将`c#`中的函数，替换原有的函数；


利用这套`hook`能力，`hook`住了：

- `luaL_loadbufferx`
- `luaL_loadbuffer`

`lua`在加载文件的时候，会使用该方法，将文件内容加载进来，`Miku-LuaProfiler`将这个过程劫持了，并且在文件内容被加载前，对其进行了修改。

它添加了如下内容：

```lua
local MikuSample = {
    rawget(_G, 'MikuLuaProfiler').LuaProfiler.BeginSample,
    rawget(_G, 'MikuLuaProfiler').LuaProfiler.EndSample,
    rawget(_G, 'miku_unpack_return_value')
}

MikuSample[1]("[lua]:require ${filename},${filename}&line:1")

return (function(...)

  -- 中间填充原来的函数.

end)(...)
```

与此同时，`Miku-LuaProfiler`实现了一个`Lua`的词法分析器 + 语法分析器，该分析器会遍历`lua`的代码，执行以下操作：

- **函数名分析：**在拿到`function`的`token`时，把函数名分析出来；

- **调用行为分析**：能够识别调用，并且识别是否是尾调用；

- **返回行为分析**：能够识别函数的`return`；


当我们的`lua`内容如下的时：

```lua
function Sum(l, r)
    if l < r then
        return l + r
    else
        return r + l
    end

    return 1
end

function GetOnePlusOneResult()
    return Sum(1, 1)
end
```

生成的结果如下：

```lua
local MikuSample = {rawget(_G, 'MikuLuaProfiler').LuaProfiler.BeginSample, rawget(_G, 'MikuLuaProfiler').LuaProfiler.EndSample, rawget(_G, 'miku_unpack_return_value')} return (function(...) MikuSample[1]("[lua]:require asd,asd&line:1")function Sum(l, r) MikuSample[1]("[lua]:Sum,asd&line:1")
    if l < r then
         return MikuSample[3]( l + r)
    else
         return MikuSample[3]( r + l)
    end

     return MikuSample[3]( 1)
end

function GetOnePlusOneResult()
    return Sum(1, 1)
end
 MikuSample[2]()
 end)(...)
```

而这里，`miku_unpack_return_value`就是单纯的调用了一下：

```c#
[MonoPInvokeCallbackAttribute(typeof(LuaCSFunction))]
static int UnpackReturnValue(IntPtr L)
{
  LuaProfiler.EndSample(L);
  return LuaDLL.lua_gettop(L);
}
```


到此为止，`LuaProfiler`在进入函数的时候，被告知`BeginSample`，在


## 总结

`ELuaProfiler`和`Miku-LuaProfiler`本质上都是通过`hook` `lua`函数入口、出口来实现的

不同点在于：

- `ELuaProfiler`通过`lua`原生机制实现，能够感知到`tostring`等`lua`原生提供的接口的调用，这是优势，但与此同时，也需要定制维护一个函数黑名单，来过滤掉不过多的、不必要的系统函数的调用；
- `Miku-LuaProfiler`是通过平台原生的`hook`机制，劫持了`lua_loadbufferx`方法，修改了读入的`lua`代码，这样就可以只`hook`到用户编写的`lua`文件，而不`hook`系统调用，会更灵活一些；


`ELuaProfiler`的方式可以直接拿过来用，但是`Miku-LuaProfiler`的方式就需要针对`webgl`重新开发，来实现它的`hook`接口。但是方法是不难的，可以引入头文件，将`lua`中对`lua_api`的调用修改为可`hook`的调用，如：

```c++
typedef int (*luaL_loadbufferx_func)(lua_State *L, const char *buff, size_t size, const char *name, const char *mode);

static luaL_loadbufferx_func luaL_loadbufferx_ptr = &luaL_loadbufferx;

LUALIB_API int wrap_luaL_loadbufferx(lua_State *L, const char *buff, size_t size,
                                 const char *name, const char *mode) {
  *luaL_loadbufferx_ptr(L, buff, size, name, mode);
}

int install_luaL_loadbufferx_hook(void* hook_func) {
  luaL_loadbufferx_ptr = (luaL_loadbufferx_func)hook_func;
}

int uinstall_luaL_loadbufferx_hook(void* hook_func) {
  luaL_loadbufferx_ptr = &luaL_loadbufferx;
}
```

动态获取`luaL_loadbufferx_ptr`进行调用；

```c++
#define luaL_loadbufferx wrap_luaL_loadbufferx
```

对所有调用`luaL_loadbufferx`的地方，改为`wrap_luaL_loadbufferx`即可。


# 内存监控

内存监控的目标有两点：

1. 实时的内存使用量感知
2. 感知不同类型的对象数量、占用空间


## 内存使用量统计


### ELuaProfiler

`lua`允许用户自定义内存分配器，可以通过调用`lua_setallocf`来指明自己的内存分配器，其声明如下：

```c++
typedef void * (*lua_Alloc) (void *ud, void *ptr, size_t osize, size_t nsize);

void lua_setallocf (lua_State *L, lua_Alloc f, void *ud);
```

用户需要自己实现`lua_Alloc`，这个函数根据参数传入不同需要做出不同行为：

| 参数状态（前提）            | 需要做出的行为                                    |
| --------------------------- | ------------------------------------------------- |
| `nsize  == 0`               | 根据`osize`释放内存                               |
| `ptr == NULL && nsize != 0` | 根据`nsize`分配对应大小的内存                     |
| `ptr != NULL && nsize != 0` | 执行`realloc`逻辑，同时释放`osize`并且分配`nsize` |

通过监听`lua_setallocf`能够实时感知到`lua`的内存分配情况，`ELuaProfiler`中实现如下：

```c++
void* FELuaMonitor::LuaAllocator(void* ud, void* ptr, size_t osize, size_t nsize)
{
    if (nsize == 0)
    {
        ELuaProfiler::GCSize += osize;
        FMemory::Free(ptr);
        return nullptr;
    }

  if (!ptr)
    {
        ELuaProfiler::AllocSize += nsize;
        return FMemory::Malloc(nsize);
    }
    else
    {
        ELuaProfiler::GCSize += osize;
        ELuaProfiler::AllocSize += nsize;
        return FMemory::Realloc(ptr, nsize);
    }
}
```

这上面的表中的内容一模一样，不做过多讲解。


### Miku-LuaProfiler

`Miku-LuaProfiler`的思路相当暴力：**直接禁用掉所有lua的gc操作，统计lua的内存增量即可**

我们之前提到`Miku-LuaProfiler`使用了平台的`hook`能力，基于这个能力，`Miku-LuaProfiler`也`hook`了`lua_gc`这个函数：

```c++
[MonoPInvokeCallbackAttribute(typeof(lua_gc_fun))]
public static int lua_gc_replace(IntPtr luaState, LuaGCOptions what, int data)
{
  lock (m_Lock)
  {
    if (!isHook)
    {
      return lua_gc(luaState, what, data);
    }
    else if (what == LuaGCOptions.LUA_GCCOUNT)
    {
      return lua_gc(luaState, what, data);
    }
    else if (what == LuaGCOptions.LUA_GCCOUNTB)
    {
      return lua_gc(luaState, what, data);
    }
    return 0;
  }
}
```

`hook`之后，只会处理`LUA_GCCOUNT`, `LUA_GCCOUNTB`这两轮`gc`，其他的部分一概不处理。

这样`lua`的内存就不会缩减了，只需要每次`sample`结束后，`count`一遍`lua`的内存，算一下`diff`就可以知道不同函数使用了多少内存：

```c#
public static long GetLuaMemory(IntPtr luaState)
{
  long result = 0;
  if (LuaProfiler.m_hasL)
  {
    result = LuaDLL.lua_gc(luaState, LuaGCOptions.LUA_GCCOUNT, 0);
    result = result * 1024 + LuaDLL.lua_gc(luaState, LuaGCOptions.LUA_GCCOUNTB, 0);
  }
  return result;
}
```


## 分类型统计（内存快照）


### Miku-LuaProfiler

`miku-luaprofiler`中的内存快照功能在`lua`中实现：

```lua
function miku_do_record(val, prefix, key, record, history, null_list)
```

在实际使用的过程中，会从`_G`全局表，以及`_R`注册表（`debug.getregistry()`）出发，递归的进行遍历。

- `null_list`会返回所有在`c#`中已经`destory`的`userdata`，其原理是通过调用`c#`的`System.Object.Equals`判断是否为`nil`；

- `record`会记录所有对象 到其 所在位置的集合的映射，如下面的函数，在以下路径出现：

  ```lua
  function: 001FA820      
  {
      "function:=[C]&line:-1",
      "[_G].[package].[loaded].[os].[exit]",
      "function:@.\temp.lua&line:23.[infoTb].[table:]",
      "function:@.\temp.lua&line:10.[funAddrTb].[table:]"
  }
  ```

- `history`是一张特殊的表，在执行`miku_diff`时生效，为了生成`diff`，会在`lua`中保存一张之前的历史记录，这张表中的内容是不希望被遍历到的；


在递归遍历的过程中，除了对于节点本身外：

- `function`：会遍历`upvalue`进行记录
- `table`：遍历`table`中的内容，进行记录
- 对于所有的对象：取`metatable`，进行记录


代码详情，[可以点击此处](https://github.com/leinlin/Miku-LuaProfiler/blob/9f2440819ac26654e42a09488ca201e61e7c6909/LuaProfiler/Runtime/Core/LuaHookSetup.cs#L998)


### ELuaProfiler

`ELuaProfiler`的内存快照功能在`c++`中实现，核心在于：

```c++
void FELuaMemAnalyzer::traverse_object(lua_State* L, const char* desc, int level, const void* parent)
{
    int t = lua_type(L, -1);                      // [object]
    switch (t)
    {
    case LUA_TLIGHTUSERDATA:
        traverse_lightuserdata(L, desc, level, parent);         // [] pop object
        break;
    case LUA_TSTRING:
        traverse_string(L, desc, level, parent);              // [] pop object
        break;
    case LUA_TTABLE:
        traverse_table(L, desc, level, parent);             // [] pop object
        break;
    case LUA_TUSERDATA:
        traverse_userdata(L, desc, level, parent);            // [] pop object
        break;
    case LUA_TFUNCTION:
        traverse_function(L, desc, level, parent);            // [] pop object
        break;
    case LUA_TTHREAD:
        traverse_thread(L, desc, level, parent);              // [] pop object
        break;
    //case LUA_TNUMBER:
    //    traverse_number(L, desc, level, parent);              // [] pop object
    //    break;
    default:
        lua_pop(L, 1);                          // [] pop object
        break;
    }
}
```


实现的思路与`miku`相同，但是看起来，对`LUA_TTHREAD`进行了更多的处理，在`traverse_thread`中：

- 对`thread`的栈上所有元素，执行`traverse_object`，进行遍历；
- 随后会不停的使用`lua_getstack`取调用栈，进行记录；


# 总结

- 调用感知：
  - 需要`hook` lua函数调用的行为
    - 可以学习`EluaProfiler`，利用`Lua`原生的`hook`来实现，但是在`unity`中需要从头开始自己实现；
    - 更好的方法是改写`Miku-LuaProfielr`，编写`Webgl Hook`，对于编写`hook`：
      - 可以使用工具，改变`lua`源码，添加工具函数；
      - 可以用`binaryen`，注入一个`hook`方法，直接修改`wasm`，适配会好适配一些；
- 内存监控：
  - 内存量的变动：
    - 学习`EluaProfiler`看起来更好一些，不会限制用户的`gc`，可以实时感知到真实的内存使用；
    - 保持`Miku-LuaProfiler`的话，可以看到每个函数的增量，但是会导致`lua gc`不生效；
  - 内存快照：
    - 实现原理基本一致，都是遍历`_G`，`Miku-LuaProfiler`还多遍历了`debug.getregistry`


# 风险


## 1. hook本身会耗时，影响精度

《Lua Profiler性能分析工具的实现》作者进行了实验，每次`hook`耗时为`14us`，在层次较深，但是函数逻辑简单的调用过程中，`hook`的耗时会随着函数调用深度的增加而累加，可能会导致耗时统计不准。

他们另外开了一条线程来处理`hook`，但是显然`wasm`环境中不具备这样的条件。


# 参考

1. [《Lua性能优化（一）：Lua内存优化 》](https://zhuanlan.zhihu.com/p/29315286)
2. 《如何利用LuaHook开发一个健壮的Profiler》 —— 未公开
3. 《Lua Profiler性能分析工具的实现》 —— 未公开
4. [Miku-LuaProfiler](https://github.com/leinlin/Miku-LuaProfiler)
5. [ELuaProfiler](https://github.com/inkiu0/ELuaProfiler)