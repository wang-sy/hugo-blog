---
title: '【Wasm】Emcc & Binaryen 初步学习'
date: 2024-04-02T10:28:12+08:00
draft: true
categories:
    - Wasm
tags:
    - Wasm
    - Binaryen
    - Emcc

---

Binaryen 可用于编辑已经生成好的 Wasm 文件，这篇文章探索一下这个工具的使用

<!--more-->



发现Binaryen的中文资料非常少，都不知道怎么用，因此探索一下，简单记录下。



# 1. 下载 & 安装 相关工具

## Emsdk(包含emcc)

仓库地址：https://github.com/emscripten-core/emsdk

```zsh
git clone https://github.com/emscripten-core/emsdk.git
```

按照仓库中的方法安装即可，进入仓库后：

```zsh
./emsdk install latest
./emsdk activate latest
```

如果你想每次打开控制台都能用的话，就直接：

**mac or linux (zsh console)**

```zsh
echo "source ./emsdk_env.sh" >> ~/.zshrc
```

**windows**用户自己学习下怎么在启动`powershell`的时候运行`ps1`脚本就好了。



## Binaryen

先`clone`下来：

```zsh
git clone --recursive https://github.com/WebAssembly/binaryen.git
```

进入`clone`下来的目录，创建文件夹，并且使用`Cmake & Makefile`进行编译 & 安装：

```zsh 
mkdir build && cd build

cmake ..
make -j 16
sudo make install
```

安装结束后可以看到安装的内容：

```zsh
Install the project...
-- Install configuration: "Release"
-- Installing: /usr/local/lib/libbinaryen.dylib
-- Installing: /usr/local/include/binaryen-c.h
-- Installing: /usr/local/include/wasm-delegations.def
-- Installing: /usr/local/bin/wasm-opt
-- Installing: /usr/local/bin/wasm-metadce
-- Installing: /usr/local/bin/wasm2js
-- Installing: /usr/local/bin/wasm-emscripten-finalize
-- Installing: /usr/local/bin/wasm-as
-- Installing: /usr/local/bin/wasm-dis
-- Installing: /usr/local/bin/wasm-ctor-eval
-- Installing: /usr/local/bin/wasm-shell
-- Installing: /usr/local/bin/wasm-reduce
-- Installing: /usr/local/bin/wasm-merge
-- Installing: /usr/local/bin/wasm-fuzz-types
-- Installing: /usr/local/bin/wasm-fuzz-lattices
-- Installing: /usr/local/bin/wasm-split
-- Installing: /usr/local/bin/binaryen-unittests
```

不仅安装了我们最想要的`libbinaryen.dylib`，还安装了一些其他工具，这里不做介绍，想大概了解就直接去[仓库](https://github.com/WebAssembly/binaryen#Tools)里面看。





# 2. c++转wasm

这个被各种博客快讲烂了，就一笔带过了：

```c++
// main.cc
#include <iostream>

int main () {
  std::cout << "Hello World Wasm" << std::endl
  return 0;
}
```

直接使用刚才安装好的`emcc`进行编译:

```zsh
emcc main.cc -s WASM=1 -o main.html
```

可以观察到生成出来的文件：

```zsh
# XXX @ XXX-MB1 in ~/Desktop/codes/play_wasm [11:15:26] 
$ ls
main.cc   main.html main.js   main.wasm
```

使用`emsdk`自带的工具起一个`httpsvr`：

```zsh
# XXX @ XXX-MB1 in ~/Desktop/codes/play_wasm [11:19:12] C:130
$ emrun --no_browser --port 8080 .
Web server root directory: /Users/XXX/Desktop/codes/play_wasm
Now listening at http://0.0.0.0:8080/
```



打开对应的地址：http://localhost:8080/main.html就可以看到`wasm`的输出了

<img src="https://jaegerdocs-1301596189.cos.ap-guangzhou.myqcloud.com/image-20240402111947623.png" alt="image-20240402111947623" style="zoom:67%;" />



# 3. 学习使用Binaryen-c

首先新建一个`cmake`工程：

```cmake
cmake_minimum_required(VERSION 3.23)
project(binaryen_test)

set(CMAKE_CXX_STANDARD 17)
set(MY_LIBRARY_PATH "/usr/local/lib/")
set(MY_HEADER_PATH "/usr/local/include/")

include_directories(${MY_HEADER_PATH})
link_directories(${MY_LIBRARY_PATH})

add_executable(binaryen_test main.cpp)
target_link_libraries(binaryen_test libbinaryen.dylib)
```

这里引用了刚才编译出来的动态链接库，将他和我们项目中的`main.cpp`一起编，`main.cpp`直接抄`binaryen`的[demo中的内容](https://github.com/WebAssembly/binaryen/blob/main/test/example/c-api-hello-world.c)。

```c++
#include <binaryen-c.h>

int main() {
  BinaryenModuleRef module = BinaryenModuleCreate();

  // Create a function type for  i32 (i32, i32)
  BinaryenType ii[2] = {BinaryenTypeInt32(), BinaryenTypeInt32()};
  BinaryenType params = BinaryenTypeCreate(ii, 2);
  BinaryenType results = BinaryenTypeInt32();

  // Get the 0 and 1 arguments, and add them
  BinaryenExpressionRef x = BinaryenLocalGet(module, 0, BinaryenTypeInt32()),
          y = BinaryenLocalGet(module, 1, BinaryenTypeInt32());
  BinaryenExpressionRef add = BinaryenBinary(module, BinaryenAddInt32(), x, y);

  // Create the add function
  // Note: no additional local variables
  // Note: no basic blocks here, we are an AST. The function body is just an
  // expression node.
  BinaryenFunctionRef adder =
          BinaryenAddFunction(module, "adder", params, results, NULL, 0, add);

  // Print it out
  BinaryenModulePrint(module);
  
  // Clean up the module, which owns all the objects we created above
  BinaryenModuleDispose(module);


  return 0;
}
```

执行，可以看到如下输出：

```lisp
(module
 (type $0 (func (param i32 i32) (result i32)))
 (func $adder (param $0 i32) (param $1 i32) (result i32)
  (i32.add
   (local.get $0)
   (local.get $1)
  )
 )
)
```

从这个case中可以看出，`binaryen`能够用语法树表达一段`wasm`程序，并且提供了将这种语法树输出为`asm.js`的能力。



但是美中不足的是，我学习他的目标是希望能够

