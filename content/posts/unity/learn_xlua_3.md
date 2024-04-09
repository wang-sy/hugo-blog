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



- `tolua`：https://github.com/topameng/tolua
- `tolua_runtime`：https://github.com/topameng/tolua_runtime



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
    print(print_person:GetName()..""'s age is ""..print_person:GetAge())
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

