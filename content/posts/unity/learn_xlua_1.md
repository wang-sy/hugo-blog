---
title: 'unity + xlua 学习'
date: 2024-03-19T19:16:11+08:00
draft: true
categories:
    - Unity
tags:
    - Unity
    - XLua
---
XLua 实现了 unity 中 c# 脚本与 lua 脚本之间的互调功能，并且提供了热更的能力，这篇文章学习 XLua 的使用
<!--more-->

# 一、 hello world



## 1. 创建工程并导入 XLua



下载`Xlua`: [xlua链接](https://github.com/Tencent/xLua)



**创建一个全新的unity工程**，这里我使用的unity版本是`2021.3.33f1c1`。

- 创建结束后，将`XLua`中的`Assets/Plugins`, `Assets/XLua`, `Tools`, `WebGLPlugins`目录依次拷贝到我们新建的项目中。

- 随后将`Assets/XLua/Examples`, `Assets/XLua/Tutorial`下的代码删除（不然会有一些莫名其妙的bug）。



<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319165203026.png" alt="image-20240319165203026" style="zoom:50%;" />
    <p>
        <b>图1：将XLua导入到已有工程</b>
    </p>
</center>



**使用XLua生成代码**

点击`XLua > Generate Code`， 能够观察到`Assets/XLua/Gen`下生成了一些代码：

<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319172843406.png" alt="image-20240319172843406" style="zoom:50%;" />
    <p>
        <b>图2：使用 XLua Generate Code</b>
    </p>
</center>





## 2. 通过XLua运行简单脚本

创建`TestMain`脚本，写入如下内容：

```c#
using UnityEngine;
using XLua;

public class TestMain : MonoBehaviour
{
        void Start()
        {
            LuaEnv luaenv = new LuaEnv();
            luaenv.DoString("CS.UnityEngine.Debug.Log('hello world')");
            luaenv.Dispose();

            Debug.Log("Unity C#: hello world");
        }
}

```





## 3. 编译并运行项目

直接`File > Build And Run`，编译出来`webgl`项目，项目运行后，能够在控制台中分别看到来自`luaenv.DoString`和`Debug.Log`的输出：

<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319173011730.png" alt="image-20240319173011730" style="zoom:50%;" />
    <p>
        <b>图3：运行 hello world</b>
    </p>
</center>





## 可能踩到的坑

在这个过程里面还是有一些坑的，我遇到了两个坑：

### a) 提示 'Light' does not contain a definition for 'shadowAngle'

<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319173732514.png" alt="image-20240319173732514" style="zoom:50%;" />
    <p>
        <b>图4：未删除 Examples 导致的错误</b>
    </p>
</center>



如上图所示，可能是因为没有删除`Examples`导致的问题，直接将`Assets/XLua/Examples`删除并重新`Generate Code`后再编译即可解决。



### b) 提示 xlua_webgl.cpp错误

<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319183644258.png" alt="image-20240319183644258" style="zoom:50%;" />
    <p>
        <b>图5：xlua_webgl.cpp错误</b>
    </p>
</center>

点开后查看详情，看到：

> In file included from Assets/Plugins/WebGL/xlua_webgl.cpp:35:
> WebGLPlugins\i64lib.c:409:34: error: invalid suffix on literal; C++11 requires a space between literal and identifier [-Wreserved-user-defined-literal]
>         snprintf(temp, sizeof(temp), "%"PRIu64, n);

其中：

```c
# if __WORDSIZE == 64  
#  define PRIu64    "lu"   
# else  
#  define PRIu64    "llu"  
```

`c++11`里面，两个字符串拼在一起的时候，中间要插入空格，我们在`"%"PRIu64`中间插入空格，变为`"%" PRIu64`就可以了。



# 二、





**然后, 修改Define Symbols**:  打开`Edit > Project Settings > Player > OtherSettings > Script Complication > Scriptiong Define Symbols`，添加`HOTFIX_ENABLE`，点击`apply`：

<center>
    <img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240319171529548.png" alt="image-20240319171529548" style="zoom:50%;" />
    <p>
        <b>图2：为XLua添加 Define Symbols </b>
    </p>
</center>

