---
title: '【Unity】toLua 中 c# object 与 luavm 之间的交互'
date: 2024-04-08T12:23:12+08:00
draft: false
categories:
    - Unity
tags:
    - Unity
    - toLua
    - Lua
---

ToLua 能够实现 C# 与 Lua 之间的互通，这篇文章分析这一机制的实现原理
<!--more-->



# 1. 如何将一个类型“注入”Lua脚本

在不考虑`ToLua`这个库的情况下，先来讨论一下，如何将一个自定义好的`class`作为一个第三方库，放到`lua`中使用：



## 将MyPerson类提供给lua调用



### MyPerson类的介绍

```c++
class MyPerson {
public:
    MyPerson(std::string  name, int age) :name_(std::move(name)), age_(age) {}

    void set_name(const std::string& name) {name_ = name;}
    [[nodiscard]] const std::string& get_name() const {return name_;}

    void set_age(int age) {age_ = age;}
    [[nodiscard]] int get_age() const {return age_;}
private:
    std::string name_;
    int age_;
};
```

有上面的这个`c++`类，接下来希望放到`lua`中使用。



### 构建mylib库的架子

```c++
#define LUA_MY_PERSON "MyPerson"

static const luaL_Reg my_lib[] = {
        {"create_my_person", create_my_person},
        {nullptr, nullptr}
};

static const luaL_Reg my_person_funcs[] = {
        {"get_age", my_person_get_age},
        {"set_age", my_person_set_age},
        {"get_name", my_person_get_name},
        {"set_name", my_person_set_name},
        {nullptr, nullptr}
};


int luaopen_mylib(lua_State* L)
{
    // 创建 MyPerson metatable.
    luaL_newmetatable(L, LUA_MY_PERSON);

    lua_newtable(L);
    luaL_setfuncs(L, my_person_funcs, 0);
    lua_setfield(L, -2, "__index");

    lua_pop(L, -1);
	
    // 清空栈，然后创建lib的table, 并且返回.
    luaL_newlib(L, my_lib);
    return 1;
}
```

这里从`luaopen_mylib`出发，做了两件事情：

1.  创建了一张叫做`MyPerson`的`metatable`，然后向该`metatable`的`__index`表中设置了一些函数，相当于构建了一个这样的`metatable`:

   ```lua
   MyPerson = {
       __index = {
           get_name = function(self) end,
           set_name = function(self, name) end,
           get_age = function(self) end,
           set_age = function(self, age) end,
       }
   }
   ```

2. 返回了一个`table`，作为`require`当前库时的返回结果，执行`require`时，拿到的结果实际上是：

   ```lua
   {
       create_my_person = function(name, age) end
   }
   ```

当调用`create_my_person`等方法时，`lua`会将请求转发到我们编写的库中的函数中执行，接下来我们就来实现这些方法。



### 实现 create_my_person 方法

用户在`lua`中会编写如下的代码对`create_my_person`进行调用：

```lua
local mylib = require('mylib')

local person = mylib.create_my_person('jack', 18)
```

在用户调用`mylib.create_my_person('jack', 18)`时，`luavm`会调用当前的`create_my_person((lua_State* L))`函数，调用时栈如下：

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/learn_tolua.drawio.svg" alt="learn_tolua.drawio" style="zoom:80%;" />
    <p>
        <b>图1：调用 create my person 的栈</b>
    </p>
</center>

可以使用`luaL_checkstring`, `luaL_checkinteger`根据栈上元素的`index`进行选取，因此可以写出下面的代码：

```c++
static int create_my_person(lua_State* L) {
    const std::string name = luaL_checkstring(L, 1);
    const int age = static_cast<int>(luaL_checkinteger(L, 2));

    new(lua_newuserdata(L, sizeof(MyPerson))) MyPerson(name, age);

    luaL_setmetatable(L, LUA_MY_PERSON);
    return 1;
}
```

其中`lua_newuserdata`与`C`中的`malloc`非常相似，开发者可以调用该方法向`lua`虚拟机请求一片固定大小的内存，`lua`会对这片内存进行管理。

该方法与`malloc`一样，只负责开内存，不负责调构造函数，这里这种写法是使用`lua_newuserdata`开出来内存之后又调用了`MyPerson`的构造函数。

创建好`userdata`后，调用`luaL_setmetatable`，将之前搭`mylib`时注册的`MyPerson`表给到了创建好的对象。



函数调用结束后，堆栈如下图所示：

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/learn_tolua-create_my_person_ret.drawio.svg" alt="learn_tolua-create_my_person_ret.drawio" style="zoom:65%;" />
    <p>
        <b>图2：create my person 调用结束时的栈</b>
    </p>
</center>


### 实现 MyPerson 的成员方法

接着上面的代码，用户在拿到`person`后，就会调用`person`相关的方法，进行读写操作：

```lua
function print_person_info(print_person)
    print(print_person:get_name().."'s age is "..print_person:get_age())
end

print_person_info(person)

print("ten years later")

person:set_name('old_'..person:get_name())
person:set_age(person:get_age() + 10)

print_person_info(person)
```



用户在调用`set_name`, `set_age`时，其实和python一样，对象本身会作为函数的第一个参数`self`进行传递。因此直接写出下面的方法就可以解决：

```c++
static int my_person_get_age(lua_State* L){
    auto* my_person = reinterpret_cast<MyPerson*>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    lua_pushinteger(L, my_person->get_age());
    return 1;
}


static int my_person_set_age(lua_State* L){
    auto* my_person = reinterpret_cast<MyPerson*>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    my_person->set_age(static_cast<int>(luaL_checkinteger(L, 2)));
    return 0;
}


static int my_person_get_name(lua_State* L){
    auto* my_person = reinterpret_cast<MyPerson*>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    lua_pushstring(L, my_person->get_name().c_str());
    return 1;
}


static int my_person_set_name(lua_State* L){
    auto* my_person = reinterpret_cast<MyPerson*>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    my_person->set_name(luaL_checkstring(L, 2));
    return 0;
}
```

在这些方法中，`person`作为`userdata`被推入栈中，我们可以通过`luaL_checkudata`获取到之前通过`lua_newuserdata`申请到的内存地址，拿到地址后，将其强转为`MyPerson`指针，在进行其他操作即可。

### 在c++中将这个case跑起来

```c++
static const std::string kLuaCode = R"(
local mylib = require('mylib')

local person = mylib.create_my_person('jack', 18)

function print_person_info(print_person)
    print(print_person:get_name().."'s age is "..print_person:get_age())
end

print_person_info(person)

print("ten years later")

person:set_name('old_'..person:get_name())
person:set_age(person:get_age() + 10)

print_person_info(person)
)";


LUALIB_API int luaopen_mylib(lua_State* L);

int main() {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);

    luaL_requiref(L, "mylib", luaopen_mylib, 0);
    lua_pop(L, 1);

    if (int ret =  luaL_dostring(L, kLuaCode.c_str()); ret != 0) {
        std::cout << "error, " << lua_tostring(L, -1) << std::endl;
    }

    return 0;
}
```

直接起一个`luavm`来跑这段代码即可，特殊的点在于，需要提前调用`luaL_requiref`来将`mylib`的`open`方法进行注册，这样在`lua`中调用`require('mylib')`时，就不会去本地文件中寻找`mylib.so`，而是直接调用已经注册的`luaopen_mylib`方法。



将`mylib`代码与上面的代码一起编译，运行就可以得到：

```powershell
~/luavm/cmake-build-debug/luavm.exe
jack's age is 18
ten years later
old_jack's age is 28
```



## 解决MyPerson的内存问题



### MyPerson没能正确释放内存

**发现问题**

上面就把一个简单的case跑通了，但是如果我们在`lua`中创建一个循环，不断地去跑这个case，就会发现一个问题：

```lua
local mylib = require('mylib')

for i = 0, 1000000000000, 1 do
    local person = mylib.create_my_person('jack', 18)
end
```

当我们运行上述`lua`代码时，会发现：

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240408204907054.png" alt="image-20240408204907054" style="zoom:67%;" />
    <p>
        <b>图3：循环创建person时，内存很高</b>
    </p>
</center>

这个进程占用的内存会越来越大，这说明某些地方发生了内存泄漏。



**问题的原因**

这里`MyPerson`类中，使用了`std::string`，`std::string`对象的内存分布如下：

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/v2-6e1dcdff16d980f82a79abb472e35fa9_1440w.webp" alt="img" style="zoom:50%;" />
    <p>
        <b>图4：std::string的内存分布（参考自<a href="https://zhuanlan.zhihu.com/p/157169295">《C++ string 源码实现对比》</a>）</b>
    </p>
</center>

当我们创建一个`std::string`，并且为他赋值时，他会分配一片新的内存，并且将字符串内容存储在新分配的内存中，而`luavm`管理内存时，只会将`_M_dataplus`的部分干掉，而不会触发`string`的析构，因此堆上分配的空间不会被释放。



**解决的思路：__gc函数**

`lua`中提供了一种机制，如果你的`metatable`中含有`__gc`方法，那么在`gc`要删除这个对象时，就会先调用你内置的`__gc`方法，可以通过这个`case`来体验：

```lua
function create_useless_data()
    local test_meta = {
        __gc = function()
            print('gc')
        end
    }

    return setmetatable({}, test_meta)
end

create_useless_data()

collectgarbage("collect")
```

使用`lua`运行，可以观察到：

```zsh
gc
```

这里创建了一个含有`__gc`方法的`metatable`，我们通过`create_useless_data`函数，创建出来了一个没有用的对象，然后使用`collectgarbage("collect")`触发了`gc`的全流程，进行了标记清除，清除`useless`对象时，由于`metatable.__gc`方法存在，因此调用该方法，执行结束后，才对对象进行释放。

> 说明：
>
> - 在lua 5.1版本中，只有userdata上绑定的\_\_gc方法会被调用
>
> - 在lua 5.2及其往后的版本中，table上绑定的\_\_gc方法也能被正常调用



基于此，我们可以得到两种方法，来解决内存没法正常释放的问题：

1. 触发`__gc`时，显式调用析构函数；
2. 在`mylib`中通过`new, delete`管理所有内存，`luavm`中只持有指针；



### 方案1：显式调用析构函数

为`MyPerson`添加`__gc`成员方法`on_lua_gc`，然后创建一个`luaCFunction`进行调用：

```c++
static int my_person_on_lua_gc(lua_State* L){
    auto* my_person = reinterpret_cast<MyPerson*>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    my_person->~MyPerson();
    return 0;
}
```

将新的`my_person_on_lua_gc`方法，注册到`MyPerson`的`Metatable`中:

```c++
int luaopen_mylib(lua_State* L)
{
    luaL_newmetatable(L, LUA_MY_PERSON);

    // 新增这两行，将my_person_on_lua_gc这个函数，作为__gc设置给LUA_MY_PERSON
    lua_pushcfunction(L, my_person_on_lua_gc);
    lua_setfield(L, -2, "__gc");
    
    // .. 下面的部分都一样，省略
    lua_pop(L, -1);

    luaL_newlib(L, my_lib);
    return 1;
}
```

这个方案很好理解，就是在`free`掉内存之前，先调用默认析构函数，将`MyPerson`下面的内容进行析构。



### 方案2: mylib中管理内存, lua中只管理指针

**改造create_my_person 方法**:

```c++
static int create_my_person(lua_State* L) {
    std::string name = luaL_checkstring(L, 1);
    int age = static_cast<int>(luaL_checkinteger(L, 2));

    *reinterpret_cast<MyPerson**>(lua_newuserdata(L, sizeof(MyPerson*))) = new MyPerson(name, age);

    luaL_setmetatable(L, LUA_MY_PERSON);
    return 1;
}
```

这里有点绕，我们通过`lua_newuserdata`申请对象时，申请的不再是一整个对象的空间，而是一个指针的空间。

这里的`lua_newuserdata`返回的是`my_person`指针的指针，拿到这个指针的指针之后，我们使用`new`方法创建一个`MyPerson`，赋值给这个指针的指针。



**改造 \_\_gc 方法**

```c++
static int my_person_on_lua_gc(lua_State* L){
    auto* my_person = *reinterpret_cast<MyPerson**>(luaL_checkudata(L, 1, LUA_MY_PERSON));
    delete my_person;
    return 0;
}
```

这里获取`my_person`的方式也要进行修改，因为`luavm`中记录的`userdata`不是`MyPerson`的完整数据了，而是`MyPerson`的地址。

这里拿到`MyPerson`地址的地址，反取一下，就可以拿到`my_person`指针了，对这个地址调用`delete`方法即可。



**改造其他成员方法**

这里的改造思路与`__gc`方法完全一致，就不放重复的代码了。



### 验证与对比

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240409104316238.png" alt="image-20240408230233531" style="zoom:50%;" />
    <p>
        <b>图5：方案1效果，调用析构函数</b>
    </p>
</center>


<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240408231349307.png" alt="image-20240408231349307" style="zoom:50%;" />
    <p>
        <b>图6：方案2效果，lua只持有指针</b>
    </p>
</center>

运行发现实际运行的效果与我们的预期有所不同，他们的内存竟然都在缓慢的增长？

从原理来看，都能够正常的调用到`__gc`方法，但是给`MyPerson`的构造函数与析构函数添加计数后发现，方案2中未被释放的对象数量竟然在逐渐上涨。



猜测是因为`lua`中`gc`的速度跟不上分配对象的速度，导致内存一直释放不掉。如果我们在`lua`代码中加入定期主动`gc`，可以暂时解决问题：

```lua
local mylib = require('mylib')

for i = 0, 1000000000000, 1 do
    local person = mylib.create_my_person('jack', 18)
    
    if (i % 1000000 == 0) then
       collectgarbage("collect") 
    end
end
```



修改后再重新运行，能够观察到内存稳定在一定区间内。



# 2. ToLua如何将 C# 对象“注入”Lua脚本



- `tolua`：[https://github.com/topameng/tolua](https://github.com/topameng/tolua)
- `tolua_runtime`：[https://github.com/topameng/tolua_runtime](https://github.com/topameng/tolua_runtime)



## 基本用法

### 在 C# 中执行 lua代码

`ToLua`包装了`Lua`，在`C#`中提供了`C#`与`lua`互通的能力，用户可以通过`C#`的接口来创建`luastate`，然后在里面运行`Lua`代码：

```c#
using UnityEngine;
using LuaInterface;
using System;

public class HelloWorld : MonoBehaviour
{
    void Awake()
    {
        LuaState lua = new LuaState();
        lua.Start();
        string hello =
            @"                
                print('hello tolua#')                                  
            ";
        
        lua.DoString(hello, "HelloWorld.cs");
        lua.CheckTop();
        lua.Dispose();
        lua = null;
    }
}
```



### 将 C# 的类型开放给 lua 使用

同样的，通过`toLua`，我们也能够将`C#`中已经编写好的代码交给`Lua`来使用：

**创建c#类**

```c#
public class MyPerson {
    public static MyPerson Create(string name, int age) { return new MyPerson(name, age); }
    public void SetName(string name) { this.name = name; }
    public string GetName() {  return this.name; }
    public void SetAge(int age) { this.age = age; }
    public int GetAge() { return this.age; }

    private MyPerson(string name, int age)
    {
        this.name = name;
        this.age = age;
    }   

    private string name;
    private int age;
}
```



**通过 tolua 生成 wrap 文件**

首先需要修改`ToLua`的`	CustomerSettings.cs`文件，修改其中的`customTypeList`添加刚才编写的`MyPerson`类型：

```c#

public static class CustomSettings
{
	//在这里添加你要导出注册到lua的类型列表
   public static BindType[] customTypeList =
   {
       _GT(typeof(MyPerson)),

                       
       _GT(typeof(LuaInjectionStation)),
       _GT(typeof(InjectType)),
       _GT(typeof(Debugger)).SetNameSpace(null),       
       
       // ... 剩余的忽略.
   }
}
```



配置好之后，点击`unity`中的`Lua > Generate All`可以看到在项目的`Source/Generate`目录下已经生成了`MyPersonWrap`文件，这说明可以在`lua`中使用这个类型了。



**c#中使用luabinder绑定库**

```c#
using UnityEngine;
using LuaInterface;
using System;

public class HelloWorld : MonoBehaviour
{
    void Awake()
    {
        LuaState lua = new LuaState();
        lua.Start();

        LuaBinder.Bind(lua); // 新增这一行，用于绑定所有库.

        string hello =
@"
print_person_info(person) 
";
        
        lua.DoString(hello, "HelloWorld.cs");
        lua.CheckTop();
        lua.Dispose();
        lua = null;
    }
}
```



**编写lua代码**

```lua
local person = MyPerson.Create('jack', 18)

function print_person_info(print_person)
    print(print_person:GetName().."'s age is "..print_person:GetAge())
end

print_person_info(person)

print('ten years later')

person:SetName('old_'..person:GetName())
person:SetAge(person:GetAge() + 10)

print_person_info(person) 
```

把之前的case小改一下拿来用即可。



**运行**

直接在`Editor`中运行就可以看到结果

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240409125541043.png" alt="image-20240409125541043" style="zoom:80%;" />
    <p>
        <b>图6：lua 调用 c# 方法</b>
    </p>
</center>



## C# 对象 bind 原理

### LuaBinder.cs

`LuaBinder`是由`toLua`自动生成的， 他根据`CustomSettings`中

```c#
public static class LuaBinder
{
	public static void Bind(LuaState L)
	{
		float t = Time.realtimeSinceStartup;
		L.BeginModule(null);
		MyPersonWrap.Register(L);
		LuaInterface_DebuggerWrap.Register(L);
		LuaProfilerWrap.Register(L);
		L.BeginModule("LuaInterface");
		LuaInterface_LuaInjectionStationWrap.Register(L);
		LuaInterface_InjectTypeWrap.Register(L);
		L.EndModule();
		L.BeginModule("UnityEngine");
		UnityEngine_ComponentWrap.Register(L);
        // ...
    }
    
    // ...
}
```



刚才的`C#`代码中，我们调用`LuaBinder.Bind(lua)`将对一些`unity`内置的类型，以及我们编写的`C#`类型绑定到了`lua`环境中。

通过代码可以看到，这里分了多个模块：空模块、`LuaInterface`、`UnityEngine`

我们的`MyPersonWrap`注册在默认模块下，而`Compoment`等常用的`UnityEngine`类型封装在`UnityEngine`模块下。



接下来就顺着这个注册的流程来观察，`tolua`是怎么操作的。



### 注册模块到lua



#### BeginModule

```c#
public bool BeginModule(string name)
{
#if UNITY_EDITOR
    if (name != null)
    {                
        LuaTypes type = LuaType(-1);

        if (type != LuaTypes.LUA_TTABLE)
        {                    
            throw new LuaException("open global module first");
        }
    }
#endif
    if (LuaDLL.tolua_beginmodule(L, name))
    {
        ++beginCount;
        return true;
    }

    LuaSetTop(0);
    throw new LuaException(string.Format("create table {0} fail", name));            
}
```

这里调用了预编译好的`LuaDLL`中的`tolua_beginmodule`方法，可以进入`tolua_runtime`中查看：

```c++
void pushmodule(lua_State *L, const char *str)
{    
    luaL_Buffer b;
    luaL_buffinit(L, &b);

    if (sb.len > 0)
    {
        luaL_addlstring(&b, sb.buffer, sb.len);
        luaL_addchar(&b, '.');
    }

    luaL_addstring(&b, str);
    luaL_pushresult(&b);    
    sb.buffer = lua_tolstring(L, -1, &sb.len);    
}

LUALIB_API bool tolua_beginmodule(lua_State *L, const char *name)
{
    if (name != NULL)
    {                
        lua_pushstring(L, name);			//stack key
        lua_rawget(L, -2);					//stack value

        if (lua_isnil(L, -1))  
        {
            lua_pop(L, 1);
            lua_newtable(L);				//stack table

            lua_pushstring(L, "__index");
            lua_pushcfunction(L, module_index_event);
            lua_rawset(L, -3);

            lua_pushstring(L, name);        //stack table name         
            lua_pushstring(L, ".name");     //stack table name ".name"            
            pushmodule(L, name);            //stack table name ".name" module            
            lua_rawset(L, -4);              //stack table name            
            lua_pushvalue(L, -2);			//stack table name table
            lua_rawset(L, -4);   			//stack table

            lua_pushvalue(L, -1);
            lua_setmetatable(L, -2);
            return true;
        }
        else if (lua_istable(L, -1))
        {
            if (lua_getmetatable(L, -1) == 0)
            {
                lua_pushstring(L, "__index");
                lua_pushcfunction(L, module_index_event);
                lua_rawset(L, -3);

                lua_pushstring(L, name);        //stack table name         
                lua_pushstring(L, ".name");     //stack table name ".name"            
                pushmodule(L, name);            //stack table name ".name" module            
                lua_rawset(L, -4);              //stack table name            
                lua_pushvalue(L, -2);           //stack table name table
                lua_rawset(L, -4);              //stack table

                lua_pushvalue(L, -1);
                lua_setmetatable(L, -2);                    
            }
            else
            {
                lua_pushstring(L, ".name");
                lua_gettable(L, -3);      
                sb.buffer = lua_tolstring(L, -1, &sb.len);                    
                lua_pop(L, 2);
            }

            return true;
        }

        return false;
    }
    else
    {                
        lua_pushvalue(L, LUA_GLOBALSINDEX);
        return true;
    }                
}
```



首次执行时，传入的`name`为`nil`，会将`_G`全局`Table`放在栈顶

再次执行`L.BeginModule("LuaInterface")`时，其堆栈变化如下：

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/learn_tolua-tolua_tolua_beginmodule.drawio.svg" alt="learn_tolua-tolua_tolua_beginmodule.drawio" style="zoom:80%;" />
    <p>
        <b>图7：执行 tolua_beginmodule 时的栈变化</b>
    </p>
</center>

可以看出，其主要作用就是创建了一张新的`table`，分别为其设置`__index`, `.name`, `metatable`，并且将其加入了`_G`全局表中。



#### EndModule

```c#
public void EndModule()
{
    --beginCount;            
    LuaDLL.tolua_endmodule(L);
}
```

```c++
LUALIB_API void tolua_endmodule(lua_State *L)
{
    lua_pop(L, 1);
    int len = (int)sb.len;

    while(len-- >= 0)
    {
        if (sb.buffer[len] == '.')
        {
            sb.len = len;
            return;
        }
    }

    sb.len = 0;
}
```

`EndModule`就是将刚才编辑好的`_G["ModuleName"]`给`pop`掉，然后再将`sb`中记录的`namespace`退回一层。



### 注册Class到Lua

从上面可以看出，`Module`的结构和`C#`中`namespace`的结构完全相同，有了`namespace`后，就要向里面注册各种`class`了，`class`的注册就是对各个`Wrap`调用`Register`方法：

```c#
public class MyPersonWrap
{
	public static void Register(LuaState L)
	{
		L.BeginClass(typeof(MyPerson), typeof(System.Object));
		L.RegFunction("Create", Create);
		L.RegFunction("SetName", SetName);
		L.RegFunction("GetName", GetName);
		L.RegFunction("SetAge", SetAge);
		L.RegFunction("GetAge", GetAge);
		L.RegFunction("__tostring", ToLua.op_ToString);
		L.EndClass();
	}
    
    
	[MonoPInvokeCallbackAttribute(typeof(LuaCSFunction))]
	static int Create(IntPtr L)
	{
		try
		{
			ToLua.CheckArgsCount(L, 2);
			string arg0 = ToLua.CheckString(L, 1);
			int arg1 = (int)LuaDLL.luaL_checknumber(L, 2);
			MyPerson o = MyPerson.Create(arg0, arg1);
			ToLua.PushObject(L, o);
			return 1;
		}
		catch (Exception e)
		{
			return LuaDLL.toluaL_exception(L, e);
		}
	}
    
    // .. 其他方法省略.
}
```

可以看到`MyPersonWrap`中根据每个方法的类型、参数数量对原有的`C#`函数进行了包装，使用`luaL_checknumber`获取参数，转发到`C#`中执行。

而`Register`方法，将这些包装好的方法注册到`lua`环境中，接下来主要看`Register`方法的实现。



#### Begin Class

```c#
public int BeginClass(Type t, Type baseType, string name = null)
{
  if (beginCount == 0)
  {
      throw new LuaException("must call BeginModule first");
  }

  int baseMetaRef = 0;
  int reference = 0;            

  if (name == null)
  {
      name = GetToLuaTypeName(t);
  }

  if (baseType != null && !metaMap.TryGetValue(baseType, out baseMetaRef))
  {
      LuaCreateTable();
      // public static int LUA_REGISTRYINDEX = -10000;
      baseMetaRef = LuaRef(LuaIndexes.LUA_REGISTRYINDEX);                
      BindTypeRef(baseMetaRef, baseType);
  }

  if (metaMap.TryGetValue(t, out reference))
  {
      LuaDLL.tolua_beginclass(L, name, baseMetaRef, reference);
      RegFunction("__gc", Collect);
  }
  else
  {
      reference = LuaDLL.tolua_beginclass(L, name, baseMetaRef);
      RegFunction("__gc", Collect);                
      BindTypeRef(reference, t);
  }

  return reference;
}
```

这个函数会确认`t`, `baseType`已经有`ref`的`id`，并且确认他们的`__gc`都已经被注册为`Collect`函数。

这里`LUA_REGISTRYINDEX`是一个特殊的`index`，调用`luaL_ref`时，传入`LUA_REGISTRYINDEX`时，会存入lua的注册表中。

通过观察`LuaBinder`的代码可以看出，这里维护了两个成员，：`metaMap`，`typeMap`，他们在`c#`中记录了`t`和`ref_id`的映射关系。



继续观察**tolua_beginclass**

```c#
[DllImport(LUADLL, CallingConvention = CallingConvention.Cdecl)]
public static extern int tolua_beginclass(IntPtr L, string name, int baseMetaRef, int reference = -1);
```

可以看出来，当`metaMap`中能够找到`t`时，说明`t`作为其他类的`baseType `已经进行过注册，`reference`会传递其注册过的值，而找不到时，会传`-1`。



```c++
static void _addtoloaded(lua_State *L)
{
    lua_getref(L, LUA_RIDX_LOADED);
    _pushfullname(L, -3); // 相当于 lua_pushstring("UnityEngine.Compoment")
    lua_pushvalue(L, -3);
    lua_rawset(L, -3);
    lua_pop(L, 1);
}

LUALIB_API int tolua_beginclass(lua_State *L, const char *name, int baseType, int ref)
{
    int reference = ref;
    lua_pushstring(L, name);                
    lua_newtable(L);      
    _addtoloaded(L);

    if (ref == LUA_REFNIL)        
    {
        lua_newtable(L);
        lua_pushvalue(L, -1);
        reference = luaL_ref(L, LUA_REGISTRYINDEX); 
    }
    else
    {
        lua_getref(L, reference);    
    }

    if (baseType != 0)
    {
        lua_getref(L, baseType);        
        lua_setmetatable(L, -2);
    }
           
    lua_pushlightuserdata(L, &tag);
    lua_pushnumber(L, 1);
    lua_rawset(L, -3);

    lua_pushstring(L, ".name");
    _pushfullname(L, -4);
    lua_rawset(L, -3);

    lua_pushstring(L, ".ref");
    lua_pushinteger(L, reference);
    lua_rawset(L, -3);

    lua_pushstring(L, "__call");
    lua_pushcfunction(L, class_new_event);
    lua_rawset(L, -3);

    tolua_setindex(L);
    tolua_setnewindex(L); 
    return reference;
}
```

- 首先会对当前类建立一个`table`，并且将其加到一张`LUA_RIDX_LOADED`的表中，

- 如果这个类型不存在，就创建这个类型，并且`ref`到`LUA_REGISTRYINDEX`中；

- 如果存在`baseType`，就将`baseType`的`table`取出，作为`metatable`塞给当前类型的`table`；

- 接下来对当前类型的table进行一系列操作：

  ```lua
  meta_table[magic_number] = 1
  meta_table[".name"] = "MyPerson"
  meta_table[".ref"] = ref_id
  meta_table["__call"] = c_func_class_new_event
  
  -- tolua_setindex
  meta_table["__index"] = c_func_class_index_event
  
  -- tolua_setnewindex
  meta_table["__newindex"] = c_func_class_newindex_event
  ```



在`tolua_beginclass`结束后，`C#`中还会调用`RegFunction("__gc", Collect);`将`c#`中的`Collect`方法注册进来。

接下来就可以继续向这张`table`中注册其他的方法和成员了。



#### EndClass

在类型注册结束后，会调用`L.EndClass();`，简单看一下发生了什么：

```c#
public void EndClass()
{
  LuaDLL.tolua_endclass(L);
}
```



```c++
LUALIB_API void tolua_endclass(lua_State *L)
{
	lua_setmetatable(L, -2);
    lua_rawset(L, -3);            
}
```



这里将编辑完的`meta_table`设置给了`MyPerson`的`Table`，并且将其设置到了正在编辑的`Module Table`中。

<center>
<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/learn_tolua-new%20class.drawio.svg" alt="learn_tolua-new class.drawio" style="zoom:80%;" />
    <p>
        <b>图9：创建 Class 时的Table关联</b>
    </p>
</center>



#### RegFunction

`Wrap`会调用`RegFunction`来注册函数：

```c#
public void RegFunction(string name, LuaCSFunction func)
{
    IntPtr fn = Marshal.GetFunctionPointerForDelegate(func);
    LuaDLL.tolua_function(L, name, fn);            
}
```



```c++
LUALIB_API void tolua_function(lua_State *L, const char *name, lua_CFunction fn)
{
  	lua_pushstring(L, name);
    tolua_pushcfunction(L, fn);
  	lua_rawset(L, -3);
}
```

`tolua_function`的实现就与我们之前写的完全一样了，唯一不同的点就在于，这里使用`Marshal.GetFunctionPointerForDelegate(func);`将`MyPersonWrap::SetName`这样的委托转为一个函数指针，将转换后的地址放到了`lua`里。



#### RegVar

一些`c#`类中，含有一些成员变量，供外部访问，这里也支持使用`RegVar`方法来对这种变量进行注册：

```c#
public void RegVar(string name, LuaCSFunction get, LuaCSFunction set)
{            
    IntPtr fget = IntPtr.Zero;
    IntPtr fset = IntPtr.Zero;

    if (get != null)
    {
        fget = Marshal.GetFunctionPointerForDelegate(get);
    }

    if (set != null)
    {
        fset = Marshal.GetFunctionPointerForDelegate(set);
    }

    LuaDLL.tolua_variable(L, name, fget, fset);
}
```



```c++
LUALIB_API void tolua_variable(lua_State *L, const char *name, lua_CFunction get, lua_CFunction set)
{                
    lua_pushlightuserdata(L, &gettag);
    lua_rawget(L, -2);

    if (!lua_istable(L, -1))
    {
        /* create .get table, leaving it at the top */
        lua_pop(L, 1);
        lua_newtable(L);        
        lua_pushlightuserdata(L, &gettag);
        lua_pushvalue(L, -2);
        lua_rawset(L, -4);
    }

    lua_pushstring(L, name);
    //lua_pushcfunction(L, get);
    tolua_pushcfunction(L, get);
    lua_rawset(L, -3);                  /* store variable */
    lua_pop(L, 1);                      /* pop .get table */

    /* set func */
    if (set != NULL)
    {        
        lua_pushlightuserdata(L, &settag);
        lua_rawget(L, -2);

        if (!lua_istable(L, -1))
        {
            /* create .set table, leaving it at the top */
            lua_pop(L, 1);
            lua_newtable(L);            
            lua_pushlightuserdata(L, &settag);
            lua_pushvalue(L, -2);
            lua_rawset(L, -4);
        }

        lua_pushstring(L, name);
        //lua_pushcfunction(L, set);
        tolua_pushcfunction(L, set);
        lua_rawset(L, -3);                  /* store variable */
        lua_pop(L, 1);                      /* pop .set table */
    }
}

```



这里就不做太多的讲解了，简单来说，就是在`Class MetaTable`中维护了两张表，`gettag`为索引的`get_table`, `settag`为索引的`settable`。

通过`ClassMetaTable[gettag]["var_name"]`就可以找到对应的`getter`



### Lua中对c#对象的创建 & 使用



#### 创建 c# 对象

当用户在`lua`中调用`Vector3(0,0,360)`、`MyPerson.Create()`时，之前编写的`class_new_event`、`MypersonWrap.Create`会被触发。我们来看看`tolua`是如何创建`c#`对象并返回的。



##### class_new_event 调用构造函数

```c++
static int class_new_event(lua_State *L)
{         
    if (!lua_istable(L, 1))
    {
        return luaL_typerror(L, 1, "table");        
    }

    int count = lua_gettop(L); 
    lua_pushvalue(L,1);  

    if (lua_getmetatable(L,-1))
    {   
        lua_remove(L,-2);                      
        lua_pushstring(L, "New");               
        lua_rawget(L,-2);    

        if (lua_isfunction(L,-1))
        {            
            for (int i = 2; i <= count; i++)
            {
                lua_pushvalue(L, i);                    
            }

            lua_call(L, count - 1, 1);
            return 1;
        }

        lua_settop(L,3);
    }    

    return luaL_error(L,"attempt to perform ctor operation failed");    
}
```

如果我们的类没有仅用默认构造函数，或是编写了`public`的构造函数，那么`tolua`会根据我们编写的构造函数创建`New`方法：

加入我们实现了四种不同的构造函数：

```c#
public class MyPerson {
    public MyPerson(string name, int age)
    {
        this.name = name;
        this.age = age;
    }

    public MyPerson(string name)
    {
        this.name = name;
    }

    public MyPerson(int age)
    {
        this.age = age;
    }

    public MyPerson() {}

    private string name;
    private int age;
}
```

那么在`MyPersonWrap`中，会有：

```c#
[MonoPInvokeCallbackAttribute(typeof(LuaCSFunction))]
static int _CreateMyPerson(IntPtr L)
{
	try
	{
		int count = LuaDLL.lua_gettop(L);

		if (count == 0)
		{
			MyPerson obj = new MyPerson();
			ToLua.PushObject(L, obj);
			return 1;
		}
		else if (count == 1 && TypeChecker.CheckTypes<int>(L, 1))
		{
			int arg0 = (int)LuaDLL.lua_tonumber(L, 1);
			MyPerson obj = new MyPerson(arg0);
			ToLua.PushObject(L, obj);
			return 1;
		}
		else if (count == 1 && TypeChecker.CheckTypes<string>(L, 1))
		{
			string arg0 = ToLua.ToString(L, 1);
			MyPerson obj = new MyPerson(arg0);
			ToLua.PushObject(L, obj);
			return 1;
		}
		else if (count == 2)
		{
			string arg0 = ToLua.CheckString(L, 1);
			int arg1 = (int)LuaDLL.luaL_checknumber(L, 2);
			MyPerson obj = new MyPerson(arg0, arg1);
			ToLua.PushObject(L, obj);
			return 1;
		}
		else
		{
			return LuaDLL.luaL_throw(L, "invalid arguments to ctor method: MyPerson.New");
		}
	}
	catch (Exception e)
	{
		return LuaDLL.toluaL_exception(L, e);
	}
}
```

tolua会根据参数的数量和类型，调用不同的构造函数，最后调用`ToLua.PushObject`来将`c#`对象压栈，进行返回。



##### PushObject 将 c# 对象转为 userdata

继续来看`ToLua.PushObject`的实现：

```c#
public static void PushObject(IntPtr L, object o)
{
    if (o == null || o.Equals(null))
    {
        LuaDLL.lua_pushnil(L);
    }
    else
    {
        if (o is Enum)
        {
            ToLua.Push(L, (Enum)o);
        }
        else
        {
            PushUserObject(L, o);
        }
    }
}

//o 不为 null
static void PushUserObject(IntPtr L, object o)
{
    Type type = o.GetType();
    int reference = LuaStatic.GetMetaReference(L, type);

    if (reference <= 0)
    {
        reference = LoadPreType(L, type);
    }

    PushUserData(L, o, reference);
}

public static void PushUserData(IntPtr L, object o, int reference)
{
    int index;
    ObjectTranslator translator = ObjectTranslator.Get(L);

    if (translator.Getudata(o, out index))
    {
        if (LuaDLL.tolua_pushudata(L, index))
        {
            return;
        }

        translator.Destroyudata(index);
    }

    index = translator.AddObject(o);
    LuaDLL.tolua_pushnewudata(L, reference, index);
}


```

这里会在`PushUserObject`中准备好`Object`在`lua`中的`ref_id`，随后进入`PushUserData`。

在`PushUserData`中，对每一个`LuaState`都会维护一个`ObjectTranslator`，这个`ObjectTranslator`负责为每一个 `Object` 分配一个`id`。

```c#
// ObjectTranslator [objects 为 LuaObjectPool]
public int AddObject(object obj)
{
    int index = objects.Add(obj);

    if (!TypeChecker.IsValueType(obj.GetType()))
    {
        objectsBackMap[obj] = index;
    }

    return index;
}

// LuaObjectPool
public int Add(object obj)
{
    int pos = -1;

    if (head.index != 0)
    {
        pos = head.index;
        list[pos].obj = obj;
        head.index = list[pos].index;
    }
    else
    {
        pos = list.Count;
        list.Add(new PoolNode(pos, obj));
        count = pos + 1;
    }

    return pos;
}
```

`ObjectTranslator`下维护了一个`LuaObjectPool`，这个`Pool`维护了一个链表，所有正在使用中的`Object`都会注册在链表中。

`Add`操作实际上就是向链表中添加了一个节点，获取到的`index`就是`Object` 在`List`中的位置，然后再在`ObjectTranslator`对`object --> index`的映射关系做了缓存



拿到`Object`对应的`id`后，就可以调用`tolua_pushnewudata`将这个`id`作为`userdata`压入`lua`栈中：

**新对象**

```c++
LUALIB_API void tolua_newudata(lua_State *L, int val)
{
	int* pointer = (int*)lua_newuserdata(L, sizeof(int));    
    lua_pushvalue(L, TOLUA_NOPEER);            
    lua_setfenv(L, -2);                        
	*pointer = val;
}

LUALIB_API void tolua_pushnewudata(lua_State *L, int metaRef, int index)
{
	lua_getref(L, LUA_RIDX_UBOX);
	tolua_newudata(L, index);
	lua_getref(L, metaRef);
	lua_setmetatable(L, -2);
	lua_pushvalue(L, -1);
	lua_rawseti(L, -3, index);
	lua_remove(L, -2);	
}
```

`tolua`中的每一个`userdata`都只占用一个`int`的空间大小，在压入`id`作为`userdata`后，通过`lua_getref`通过类型的`ref_id`获取到`class Table`设为`userdata`的`metatable`。最后以`index`为`key`，将这个`userdata`设入`LUA_RIDX_UBOX`中。

**同一个对象再次push**

同一个对象再次push时，就会从刚才的`LUA_RIDX_UBOX`中直接拿出来：

```c++
LUALIB_API bool tolua_pushudata(lua_State *L, int index)
{
	lua_getref(L, LUA_RIDX_UBOX);			// stack: ubox
	lua_rawgeti(L, -1, index); 				// stack: ubox, obj

	if (!lua_isnil(L, -1))
	{
		lua_remove(L, -2); 					// stack: obj
		return true;
	}

	lua_pop(L, 2);
	return false;
}
```



这样就完成了对象的创建 & 压栈，创建好的对象能够正确的被赋予`metatable`。



#### 销毁  c# 对象

在注册类型时，就已经对`metatable`写入了`__gc`方法，这里的`gc`方法全部被倒到了`Collect`函数中处理：

```c#
[MonoPInvokeCallbackAttribute(typeof(LuaCSFunction))]
public static int Collect(IntPtr L)
{
    int udata = LuaDLL.tolua_rawnetobj(L, 1);

    if (udata != -1)
    {
        ObjectTranslator translator = GetTranslator(L);
        translator.RemoveObject(udata);
    }

    return 0;
}
```

这里会使用`LuaDLL.tolua_rawnetobj(L, 1)`获取`UserObject`，结合`tolua_rawnetobj`来看，拿到的就是刚才在`translator`中分配的`index`。

接下来`userObject`会调用`RemoveObject`来回收这个`c# Object`

```c++
//lua gc一个对象(lua 库不再引用，但不代表c#没使用)
public void RemoveObject(int udata)
{            
    //只有lua gc才能移除
    object o = objects.Remove(udata);

    if (o != null)
    {
        // 对于 enum 的特殊处理，暂时不考虑.
        if (!TypeChecker.IsValueType(o.GetType()))
        {
            RemoveObject(o, udata);
        }

        if (LogGC)
        {
            Debugger.Log("gc object {0}, id {1}", o, udata);
        }
    }
}

// objects.Remove ()
public object Remove(int pos)
{
    if (pos > 0 && pos < count)
    {
        object o = list[pos].obj;
        list[pos].obj = null;                
        list[pos].index = head.index;
        head.index = pos;

        return o;
    }

    return null;
}
```

这里的`remove`操作就非常简单了，在`List`中，将相应的节点删除，那么对应`Object`在`C#`的内存空间中，就会变成无用的一片内存，这样`c#`中对应的元素就会被`c#`的gc清除。



与此同时，`ObjectTranslator`中缓存的映射关系也会被清除，清楚后，下一次不同的`Object`被分配到`List`上相同`index`时，由于`ObjectTranslator` Miss，会重新触发`tolua_pushnewudata`，来覆盖`luavm`中的`LUA_RIDX_UBOX`。



#### 调用 c# 对象

