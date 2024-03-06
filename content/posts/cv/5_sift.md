---
title: 图像处理（五）——SIFT（尺度不变特征变换）
date: 2020-04-15 23:44:46.0
updated: 2021-09-03 20:17:48.892
url: /archives/图像处理五sift尺度不变特征变换
categories: 
- 图像处理
tags: 
- 图像处理
- python

---
SIFT是业界常用的特征描述子，它可以用于特征匹配，学习
<!--more-->

#  图形学笔记（五）——SIFT（尺度不变特征变换）

**SIFT(Scale-Invariant Feature Transform)**的中文名字是**尺度不变特征变换**。SIFT描述子具有非常强的稳健性，自从SIFT出现，许多其他本质上使用相同描述子的方法也相继出现。它可以用于三维视角和噪声的可靠匹配。

## 参考资料

- Jan Erik Solem. Python计算机视觉编程 (图灵程序设计丛书) (p. 39). 人民邮电出版社.
- 6.SIFT(尺度不变特征变换)_[bilibili](https://www.bilibili.com/video/BV1Qb411W7cK?from=search&seid=15704537567770530949)
- 特别推荐一下，上面那个作者做的东西都特别良心，做的都特别好，讲得很透彻，不过可惜的是他不更新了，这是他的[主页](https://space.bilibili.com/14672002?spm_id_from=333.788.b_765f7570696e666f.1)
- [Sift中尺度空间、高斯金字塔、差分金字塔（DOG金字塔）、图像金字塔](https://blog.csdn.net/dcrmg/article/details/52561656)

## 建立高斯差分金字塔

首先要说的是，这个部分又可以拆分成两个部分：

- 建立**高斯金字塔**
- 根据高斯金字塔建立**DOG金字塔**

首先，我们来讨论一个问题，什么是金字塔?

### 什么是金字塔

相信大家都从电视上（或者亲眼）看见过所谓的金字塔：

![image-20200415203653196](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191640008.png)

图像金字塔是一种以多分辨率来解释图像的结构，通过对原始图像进行多尺度像素采样的方式，生成N个不同分辨率的图像。把具有最高级别分辨率的图像放在底部，以金字塔形状排列，往上是一系列像素（尺寸）逐渐降低的图像，一直到金字塔的顶部只包含一个像素点的图像，这就构成了传统意义上的图像金字塔。（[ref](https://blog.csdn.net/dcrmg/article/details/52561656)）

![image-20200415203821286](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191640008.png)

可以看得出来，还是有丶小像的。那么构建这个图像金字塔包括两个步骤：

- 一、使用低通滤波器平滑图像
- 二、对平滑图像进行抽样（采样）

而采样的方法又分为两种：

- 一、**上采样**：越采样图片尺寸越大（**分辨率逐级升高**）
- 二、**下采样**：越采样图片尺寸越小（**分辨率逐级下降**）

那么我们说，从一张高分辨率照片，来构建一个金字塔的过程，往往是对该图片进行上采样或下采样的过程。



### 高斯金字塔

需要声明的是，高斯金字塔并不是一个金字塔，而是由很多**组（Octave）**金字塔构成的，并且每组金字塔都包含若干**层（Interval）**。

高斯金字塔的构建

- 先将原图像扩大一倍之后作为高斯金字塔的第1组第1层，将第1组第1层图像经高斯卷积（其实就是高斯平滑或称高斯滤波）之后作为第1组金字塔的第2层，高斯卷积函数为：

  

  对于参数，在Sift算子中取的是固定值1.6。

- 将乘以一个比例系数k,等到一个新的平滑因子，用它来平滑第1组第2层图像，结果图像作为第3层。

- 如此这般重复，最后得到L层图像，在同一组中，每一层图像的尺寸都是一样的，只是平滑系数不一样。它们对应的平滑系数分别为：

- 将第1组倒数第三层图像作比例因子为2的降采样，得到的图像作为第2组的第1层，然后对第2组的第1层图像做平滑因子为的高斯平滑，得到第2组的第2层，就像步骤2中一样，如此得到第2组的L层图像，同组内它们的尺寸是一样的，对应的平滑系数分别为：。但是在尺寸方面第2组是第1组图像的一半。

这样反复执行，就可以得到一共O组，每组L层，共计O*L个图像，这些图像一起就构成了高斯金字塔，结构如下：

![image-20200415210138370](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMTAxMzgzNzAucG5n?x-oss-process=image/format,png)

高斯金字塔的性质

1. 在同一组内，不同层图像的尺寸是一样的，后一层图像的高斯平滑因子σ是前一层图像平滑因子的k倍；
2. 在不同组内，后一组第一个图像是前一组倒数第三个图像的二分之一采样，图像大小是前一组的一半；

说白了就是：

- 高斯金字塔中每一组内图像的大小相同，组中的图像高斯模糊程度不同
- 高斯金字塔中不同组之间，大小不同，但是对应位置的高斯模糊程度相同。

至此为止，我们的高斯金字塔已经建好了



### 高斯差分金字塔，DOG（Difference of Gaussian）

DOG金字塔的第1组第1层是由高斯金字塔的第1组第2层减第1组第1层得到的。以此类推，逐组逐层生成每一个差分图像，所有差分图像构成差分金字塔。概括为DOG金字塔的第o组第l层图像是有高斯金字塔的第o组第l+1层减第o组第l层得到的。

![image-20200415211857252](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMTE4NTcyNTIucG5n?x-oss-process=image/format,png)

说白了就是：高斯差分金字塔中的值就是高斯金字塔中每一组内相邻的两个层的图片相减而得到的。因此高斯差分金字塔每一组中都要比高斯金字塔中少一张图片。

有一些特征是在不同模糊程度、不同尺度下都存在的，这些特征正是Sift所要提取的“稳定”特征，这里如果看不懂，我们会放在最后，根据代码和结果进行详解。



## 兴趣点

我们认为稳定的点，不会变化的点，包含很多信息的点，是关键点，也就是兴趣点，关键点是由DOG空间的局部极值点组成的。在这个小节内，我们来看一下如何在高斯差分金字塔中寻找极值点。

### 阈值化

只保留满足下式条件的点以消除噪音：

### 在高斯差分金字塔中寻找极值点

![image-20200415214103646](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191640695-20210903191723447.png)

我们检测一个点连通的个点，来确定该点是否是附近区域内的极值点，当然，我们这种找法，只能找到近似的极值点，所以就有了下一步。

### 调整极值点位置

想要调整极值点位置，那么就需要先知道为什么极值点的位置可能有错。错误是由于：我们的极值点的选取是离散的，而非连续的，所以就有可能出现下图中的情况：

![image-20200415214457589](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191640885.png)

我们看到，我们的取点是等间距的、离散的，但是真正的极值点的位置并没有被我们取到。这时就需要我们化离散为连续，使用泰勒展开就能化离散为连续了。

![image-20200415214911852](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMTQ5MTE4NTIucG5n?x-oss-process=image/format,png)

看不懂别慌，我也看不懂。。最后化简完我们就看得懂了：

我们知道，极值点实际上是在我们找到的近似极值点附近的，上面式子中的代表的是极值点相对于的相对位移量，那么怎么将这个给求出来呢？我们需要对上面的式子进行求导，求导后得到：

将上面的式子带回到初始的函数中，得到:

### 舍去低对比度的点

如果 ，则舍去点X。

### 边缘效应的去除

使用海森矩阵

海森矩阵的特征值代表方向的梯度：





看过讲表示矩阵H对角线元素之和，表示矩阵H的行列式。假设是α较大的特征值，而是β较小的特征值，令，就有：

如果不满足：

那么就舍去X，这个过程和Harris角点检测器非常的相似，实际上他们想要达到的目标也是非常相似的，他们的目标都是为了尽量选择角点，因为我们默认角点才是包含更多信息的点。

## 有限差分法求导

一堆公式

![image-20200415225407394](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMjU0MDczOTQucG5n?x-oss-process=image/format,png)

![image-20200415225919372](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191641649.png)

![image-20200415225924658](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191641649-20210903191744371.png)

## 为关键点赋予方向

以当前位置为圆心，高斯图像尺度的1.5倍为半径画圆，统计该圆内所有像素的梯度方向及其梯度幅值，这里相当于是在投票，但是每个像素点投得票数不是1，而是该梯度的幅值。

![image-20200415230410605](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMzA0MTA2MDUucG5n?x-oss-process=image/format,png)

在投票的过程中，我们还需要使用高斯滤波进行加权，其实说白了就是：离中心点近的点投票的重要性更大。其中，结果最大的方向是主方向。当有其他的柱的幅值大于主方向的，我们就叫他辅方向。

到此为止，我们有了：

- 特征点
- 特征点对应的方向
- 特征点对应的幅值

## 构建关键点的描述符

我们在一张图片中，找到关键点是没啥作用的。我们需要在两张图片中分别找到关键点，然后把它们相对应的点匹配起来，所以我们需要找到一种匹配的方法，这里我们使用的是KNN。

我们找到以中心点为中心的16个格子，分别统计十六个格子中八个方向的梯度的长度（高斯加权后的）。

![image-20200415231824609](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMzE4MjQ2MDkucG5n?x-oss-process=image/format,png)

这样我们就得到了下面的：

![image-20200415231844872](https://imgconvert.csdnimg.cn/aHR0cDovL3NhaXl1d2FuZy1ibG9nLm9zcy1jbi1iZWlqaW5nLmFsaXl1bmNzLmNvbS8lRTUlOUIlQkUlRTUlODMlOEYlRTUlQUQlQTYlRTQlQjklQTBjaDUvaW1hZ2UtMjAyMDA0MTUyMzE4NDQ4NzIucG5n?x-oss-process=image/format,png)

这样我们就得到了一个8*16的向量，用于描述这个区域。但是在做这些之前，我们需要先将区域内的点旋转到主方向上，然后再进行统计。

![image-20200415232058803](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/format,png-20210903191642426.png)

## 代码

下面这个代码是从网上copy的，用cv2直接掉的包，下面还有一个b站up主自己写的，大家可以去学习一下。

```python
"""
Created on Sat Sep 29 14:43:02 2018

@author: qgl
"""

import numpy as np
import cv2
from matplotlib import pyplot as plt

imgname = 'C:/Users/qgl/Desktop/articles/test1.jpg'

sift = cv2.xfeatures2d.SIFT_create()

img = cv2.imread(imgname)
gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
kp,des = sift.detectAndCompute(img,None)

cv2.imshow('gray',gray)
cv2.waitKey(0)

img1=cv2.drawKeypoints(img,kp,img,color=(255,0,255))

cv2.imshow('point',img1)
cv2.waitKey(0)
```



这份代码是学习之前说的那个up主的项目写的，希望大家去给他打个星：

https://github.com/o0o0o0o0o0o0o/image-processing-from-scratch