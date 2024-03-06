---
title: Cache 的一致性问题
date: 2021-07-29 10:35:06.0
updated: 2021-09-03 10:44:17.629
url: /archives/cache的一致性问题
categories: 
- 基础知识
tags: 
- CPU
- 硬件
- 基础知识

---

Cache是CPUCore与Memory之间的桥梁，这篇文章从MIPS单核CPU开始，逐层深入讲解多种情况下的缓存一致性问题
<!--more-->

## 从五级流水 MIPS32 入手

### 什么是五级流水

CPU会不断地从内存中取出指令并执行，一条指令的执行过程可以被概括为：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/cache_sync_flow_mod.svg" title="1. 阻塞式运行" />

<center><b>1. 阻塞式运行</b></center>

如果在一个时钟周期内顺序执行所有内容，那么**同一时间内只有一个模块在运行，其他模块都处于等待状态**，这将导致**时钟周期过长、指令执行效率低下**的问题。**五级流水**在各模块间**插入锁存器**，**各个模块在时钟周期内同时运算**，当监测到时钟上升沿时将**运算结果通过锁存器传入下一模块**。五级流水的实质是通过**拆分执行逻辑、存储中间状态**达到 **提高并行度、缩短时钟周期、提高IPS(Instr per Second)** 的目的。

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/五级流水线.svg" title="2. 五级流水并发执行" />

<center><b>2. 五级流水并发执行</b></center>

### 五级流水中的访存场景

我们讨论`CPU`何时需要访问内存。

- `访问内存`: `lw`, `sw` 等指令会对内存进行读写；
- `取出指令`：会根据`pc`寄存器(即`指令计数器`)，在内存中读取待执行的指令；

`访问内存`、`取出指令`两个阶段往往并发执行，为了降低设计成本，`哈佛架构`应运而生。在哈佛架构中，指令存储器、数据存储器相互独立、互不影响。

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/hafo.svg" title="3. 哈佛结构" />

<center><b>3. 哈佛结构</b></center>

存储器的概念较为模糊，接下来会继续讲解。

### `Cache`在访存操作中的位置

将视线聚焦到`CPU`与内存之间的`IO`操作上。一次常规的操作可以分为三个阶段：

- 请求`IO`：`CPU`向内存发送读请求；
- 等待内存：`CPU`部分`Stall`，等待内存操作完成；
- `IO`完成：内存完成读写操作，`CPU`获取到数据并解除`Stall`状态继续运行；


<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/cacheInCPUView.svg" title="4. Cache与CPU、内存的关系" />

<center><b>4. Cache与CPU、内存的关系</b></center>

`Cache`实质上是内存的代理，`CPU`并不在意访问的是内存还是`Cache`，只要能取到数据就可以。与直接访问内存相比，`Cache`的引入能够尽量缩短`等待内存`阶段耗费的时间。

### `Cache`的内部实现

这一部分不会关注`Cache`内的组相连等设计，只会关注`Cache`与内存的同步性问题。

#### 通过读操作了解`Cache`整体结构

`Cache`是由一些顺序排列的行组成的，传入目标地址后，根据地址的`Index`段访问相应的`Cache`行，并判断该行内数据是否有效、存储的是否是目标地址的数据。总体结构如下图所示：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/SimpleCacheStruct.svg" title="5. 简易Cache结构" />

<center><b>5. 简易Cache结构</b></center>

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

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/writeBackCache.svg" title="6. 写回Cache行结构" />

<center><b>6. 写回Cache行结构</b></center>

与写直达`Cache`相比，写回`Cache`行中加入`dirty`位，标记数据是否被写。当数据被修改后，仅在`Cache`中修改`Data`并置`dirty`为`1`。等到该行被还出时，若`dirty`位为`1`，则向内存发起写请求并`Stall`流水线，等待写入结束后再换出。

写回操作的本质是将写操作推后，对于反复写的场景，写回操作有明显的优势。

#### 写队列优化

无论是写回(write back)还是写直达(write through)，都会在同步到内存时产生`Stall`。写队列通过异步写操作部分避免了由写入内存产生的`Stall`。

具体的操作就是：

- `Cache`写入内存时，将写入任务下发给写队列，写队列异步执行写任务；
- `CPU`从`Cache`中读取数据时，`Cache`需要同时从`CacheLines`、`写队列`获取数据；


#### `InstrCache` 与 `DataCache` 的一致性问题

程序运行过程中可能会修改自己的代码段，该操作数据访存操作，会与`DataCache`进行交互。此时访问`InstrCache`将面临两个问题：

1. `DataCache`使用写回策略，更新未同步到内存，`InstrCache`访存时获取到的是老数据；
2. `InstrCache`存储了旧指令，写入新数据时没有同步`InstrCache`，后续访问时，`InstrCache`直接命中，返回旧指令；

想要解决这个问题，核心在于：写入`DataCache`时，需要对`InstrCache`进行同步更新。

**解决方案1：硬件同步**

- 对于问题1：访问`InstrCache`时先判断`DataCache`是否命中，若`DataCache`命中，则使用`DataCache`中的数据；
- 对于问题2：写入`DataCache`时先判断`InstrCache`是否命中，如果命中，则更新`InstrCache`；


**解决方案2：软件同步**

操作系统直接通过程序的代码段范围来判断访存指令的修改目标是否是代码段。当修改目标为代码段时，直接使用Cache同步语句进行同步操作；

**解决方案对比**

- 方案1: 能够让软件层不关心一致性问题，把所有一致性问题放到硬件层面解决；但是两部判断带来的延迟过高，可能导致流水线主频下降的问题；
- 方案2: 需要在OS或者是编译器层面去解决问题；

总体来说，运行时修改代码段的情况较少，在硬件层面解决该问题代价过高，因此大部分情况下是使用方案二。

## 多核CPU中的一致性问题

### 问题的产生

在单核心`MIPS32_CPU`中，只有一个`CPU`和一个`Cache`交互，只需保证`Cache`与内存间的数据同步即可。但是在多核心`CPU`中，情况有所不同：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/sync_problem.svg" title="7. 多核CPU存储结构" />

<center><b>7. 多核CPU存储结构</b></center>

在这种场景下，当`CPU1`, `CPU2`同时读写一块内存时，会出现数据的不同步问题。

### 问题的解决

这里讲解`MESI`协议的处理方法。在单核CPU中，使用`valid`标识当前`Cache`行的有效性；在回写`Cache`中用`dirty`标识当前行是否被修改。**`MESI`与之类似，它也是作为特殊的标识，记录在缓存行中**并在此基础上考虑了多核场景中的状态变化。

与其他教程不一样的是，我不想放一张四个点一堆线的图和16行的大表，我只想讲一下`MESI`四个字母是啥意思，他们之间有哪些操作。相信在了解这些之后，大家都能够自己推导出来。

#### `MESI`分别代表什么

在看这个表之前要记住，**`MESI`作为标识位，标记所在缓存行的数据状态。**

| 状态名            | 意义                                               |
| ----------------- | -------------------------------------------------- |
| **M (Modified)**  | 数据仅在本`CPU`中被修改，没有与内存、其他`CPU`同步 |
| **E (Exclusive)** | 数据只在本`CPU`中被缓存，其他`CPU`没有缓存         |
| **S (Shared)**    | 数据在多个`CPU`中被缓存，数据是一致的              |
| **I (Invalid)**   | 数据是无效的                                       |

#### 对缓存进行的四种操作

| 操作            | 含义                             |
| --------------- | -------------------------------- |
| **LocalRead**   | 当前`Cache`所在`CPU`发起了读请求 |
| **LocalWrite**  | 当前`Cache`所在`CPU`发起了写请求 |
| **RemoteRead**  | 其他`CPU`发起了读请求            |
| **RemoteWrite** | 其他`CPU`发起了写请求            |

#### `MESI`状态变化（举例）

- 任何情况下检测到`RemoteWrite`，都会将状态切换到`Invalid`；
- 任何情况下监测到`LocalWrite`，都会将状态切换到`Invalid`；
- 除`Invalid`状态外，监测到`RemoteRead`都会将状态切换到`Shared`；



把这几个状态变化想明白之后，再去想一下`LocalRead`导致的变化，`MESI`协议其实非常好理解。




## 总结

这一篇文章从`MIPS`五级流水入手，分别讲解了三种不一致问题：

- 单核CPU中，缓存与内存不一致；
- 单核CPU中，指令缓存与数据缓存不一致；
- 多核CPU中，缓存不一致；

并简单讲解其解决方法，对于部分解决方法，还给出了优化策略。