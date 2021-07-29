---
title: "Cache 的一致性问题"
date: 2021-07-29T10:35:06+08:00
draft: false
tags: ["CPU", "面试"]
categories: ["hardware"]
author: "jaegerwang"
description: "Cache是CPUCore与Memory之间的桥梁，这篇文章讲解Cache如何保证CPU对其进行访问时的数据一致性问题。"
---
<!--more-->

## 从五级流水 MIPS32 入手

### 什么是五级流水

CPU会不断地从内存中取出指令并执行，一条指令的执行过程可以被概括为：

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/cache_sync_flow_mod.svg" title="1. 阻塞式运行" >}}

如果在一个时钟周期内顺序执行所有内容，那么**同一时间内只有一个模块在运行，其他模块都处于等待状态**，这将导致**时钟周期过长、指令执行效率低下**的问题。**五级流水**在各模块间**插入锁存器**，**各个模块在时钟周期内同时运算**，当监测到时钟上升沿时将**运算结果通过锁存器传入下一模块**。五级流水的实质是通过**拆分执行逻辑、存储中间状态**达到 **提高并行度、缩短时钟周期、提高IPS(Instr per Second)** 的目的。

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/五级流水线.svg" title="2. 五级流水并发执行" >}}

### 五级流水中的访存场景

我们讨论`CPU`何时需要访问内存。

- `访问内存`: `lw`, `sw` 等指令会对内存进行读写；
- `取出指令`：会根据`pc`寄存器(即`指令计数器`)，在内存中读取待执行的指令；

`访问内存`、`取出指令`两个阶段往往并发执行，为了降低设计成本、防止程序运行时修改代码段，`哈佛架构`应运而生。在哈佛架构中，指令存储器、数据存储器相互独立、互不影响。

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/hafo.svg" title="3. 哈佛结构" >}}

存储器的概念较为模糊，接下来会继续讲解。

### `Cache`在访存操作中的位置

将视线聚焦到`CPU`与内存之间的`IO`操作上。一次常规的操作可以分为三个阶段：
- 请求`IO`：`CPU`向内存发送读请求；
- 等待内存：`CPU`部分`Stall`，等待内存操作完成；
- `IO`完成：内存完成读写操作，`CPU`获取到数据并解除`Stall`状态继续运行；


{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/cacheInCPUView.svg" title="4. Cache与CPU、内存的关系" >}}

`Cache`实质上是内存的代理，`CPU`并不在意访问的是内存还是`Cache`，只要能取到数据就可以。与直接访问内存相比，`Cache`的引入能够尽量缩短`等待内存`阶段耗费的时间。

### `Cache`的内部实现

这一部分不会关注`Cache`内的组相连等设计，只会关注`Cache`与内存的同步性问题。

#### 通过读操作了解`Cache`整体结构

`Cache`是由一些顺序排列的行组成的，传入目标地址后，根据地址的`Index`段访问相应的`Cache`行，并判断该行内数据是否有效、存储的是否是目标地址的数据。总体结构如下图所示：

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/SimpleCacheStruct.svg" title="5. 简易Cache结构" >}}

- 初始状态下：`Valid`全部为`0`，表示`cache`中全部数据无效；
- 接收到读取`target`地址数据的请求后：
  - 将地址拆分为`Tag`、`Index`、`Offset`三个部分；
  - 使用`Index`找到`Cache`中对应的行；
  - 判断Cache行中的`Tag`与目标地址的`Tag`是否相等判断数据是否被`Cache`记录并通过`Valid`标志位判断记录是否有效；
- 上述条件全部满足被称为 **`HIT`**：`Cache`中存在相应数据，直接返回给`CPU`；
- 上述条件不满足则被称为 **`MISS`**：`Cache`中相应数据缺失，**将流水线`Stall`、从内存中读取数据、更新`Tag`并置`Valid`为`1`**；

#### `Cache`的写操作


##### 写直达(Write through)

`Cache`收到写请求时，向内存发起写请求，进入等待状态并`Stall`掉流水线，内存写入完成后更新`Cache`行并释放流水线。

写直达简单粗暴，但是效率极差。

##### 写回(Write back)

回写通过引入`dirty`位、懒操作的方式解决了写直达的效率问题：

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/writeBackCache.svg" title="6. 写回Cache行结构" >}}

与写直达`Cache`相比，写回`Cache`行中加入`dirty`位，标记数据是否被写。当数据被修改后，仅在`Cache`中修改`Data`并置`dirty`为`1`。等到该行被还出时，若`dirty`位为`1`，则向内存发起写请求并`Stall`流水线，等待写入结束后再换出。

写回操作的本质是将写操作推后，对于反复写的场景，写回操作有明显的优势。

#### 写队列优化

无论是写回(write back)还是写直达(write through)，都会在同步到内存时产生`Stall`。写队列通过异步写操作部分避免了由写入内存产生的`Stall`。

具体的操作就是：
- `Cache`写入内存时，将写入任务下发给写队列，写队列异步执行写任务；
- `CPU`从`Cache`中读取数据时，`Cache`需要同时从`CacheLines`、`写队列`获取数据；

## 多核CPU中的一致性问题

### 问题的产生

在单核心`MIPS32_CPU`中，只有一个`CPU`和一个`Cache`交互，只需保证`Cache`与内存间的数据同步即可。但是在多核心`CPU`中，情况有所不同：

{{< figure src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/sync_problem.svg" title="7. 多核CPU存储结构" >}}

- 一致性问题

## 总结