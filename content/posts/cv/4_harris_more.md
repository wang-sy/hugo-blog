---
title: 图像处理（四）—— Harris 角点检测器延申
date: 2020-04-15 16:48:13.0
updated: 2021-09-03 20:17:06.432
url: /archives/图像处理四harris角点检测器延申
categories: 
- 图像处理
tags: 
- 图像处理
- python

---
根据角点检测结果进行图像特征点匹配
<!--more-->

# 图像处理（四）—— Harris 角点检测器延申

## Harris 角点检测器延申——在图像间寻找对应点

### 原理

Harris角点检测器可以检测出来图像中的兴趣点，但是没有给出比较图像间兴趣点来寻找匹配角点的方法。我们需要在每个点上加上描述子信息，并给出比较这些描述子的方法。

兴趣点描述子是分配给兴趣点的一个向量，描述该点附近的图像的表观信息，描述子越好，寻找到的对应点也越好。我们用**对应点**或**点的对应**来描述相同物体和场景点在不同图像上形成的像素点.

Harris角点的描述子通常是由周围图像像素块的灰度值,以及用于比较的归一化互相关矩阵构成的.图像的像素块由以该像素点为中心的周围矩阵部分图像构成.（其实我们可以把这个矩阵，看成一个窗口，因为我们很难从全局去考虑这个点的位置，所以我们需要在这个点附近开一个窗口，然后通过对应点之间的窗口进行比较，来达到描述两个角点的相似性的目的）

我们可以定义一个函数:
$$
c(I_1,I_2) = \Sigma_x f(I_1(x),I_2(x))
$$
其中，函数f随着相关方法的变化而变化，上式取像素块中所有像素位置x的和，对于互相关矩阵，函数$f(I_1,I_2) = I_1I_2$，因此$c(I_1,I_2) = I_1\cdot I_2$，其中$\cdot$代表向量乘法。$c(I_1,I_2)$的值越高，像素块$I_1,I_2$的相似度也越高。（另一个常用的是$f(I_1,I_2)= (I_1-I_2)^2$）

上面说的其实就是用余弦法来度量两个向量的相似度，余弦的值越大，两个向量就越接近。

归一化的互相关矩阵是互相关矩阵的一种变形，可以被定义为：
$$
ncc(I_1,I_2) = \frac{1}{n-1} \Sigma_{x}  \frac{I_1(x)-\mu_1}{\sigma_1}\cdot \frac{I_2(x)-\mu_2}{\sigma_2}
$$
学过高斯的都知道，这里的$\mu$代表的是平均值，$\sigma$代表的是标准差，而这里的统计范围是以某个点为中心的窗口中的所有像素点。这里实际上在干的事情是：求每张图片的相对亮度，所构成的向量的余弦，这样可以有效地消除由于左右目相机接收到的光照条件不同而引起的差异。

我们使用非常有名的tsukuba来进行测试，这个数据集是一个用于立体匹配的数据集：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20200415080724859.png" alt="image-20200415080627078" style="zoom:50%;" />

### 代码

```python
from PIL import Image
from numpy import *
from pylab import *
from scipy. ndimage import filters


# 计算比值得分的函数,即计算finalScore
def computeHarrisResponse(im, sigma = 3):
    """
        在一幅灰度图像中，对每个像素计算角点器响应函数
        输入:
            im:表示需要求R的图像（需要是灰度图）
            sigma：考虑半径
        返回：
            Wdet / Wtr ： lambda1*lambda2 与 (lambda1+lambda2)^2的比
    """
    
    # 计算导数
    # I_x
    imx = zeros(im.shape)
    filters.gaussian_filter(im, (sigma, sigma), (0, 1) , imx)
    # I_y
    imy = zeros(im.shape)
    filters.gaussian_filter(im, (sigma, sigma), (1, 0) , imy)
    
    # 计算Harris矩阵的分量
    Wxx = filters.gaussian_filter(imx * imx, sigma)
    Wxy = filters.gaussian_filter(imx * imy, sigma)
    Wyy = filters.gaussian_filter(imy * imy, sigma)
    
    # 计算特征值和迹
    Wdet = Wxx * Wyy - Wxy ** 2
    Wtr = Wxx + Wyy
    
    return Wdet / Wtr


# 从每个像素计算角点器响应函数到图像中的所有角点
def getHarrisPoints(harrisim, minDist = 10, threshold = 0.1):
    """
        从一幅Harris响应图像中返回角点。
        输入：
            minDist：分割角点和图像边界的最少像素数目
        输出：
            角点们
    """
    
    # 寻找高于阈值的候选角点
    # 角点阈值等于得分矩阵中最大的*0.1
    cornerThreshold = harrisim.max() * threshold
    #harrisim_t为1的位置就是可能是角点的
    harrisimT = (harrisim > cornerThreshold) * 1
    
    # 得到候选点的坐标
    coords = array(harrisimT.nonzero()).T
    
    # 候选点的Harris 响应值
    candidateValues = [harrisim[c[0], c[1]] for c in coords]
    
    # 对候选点按照Harris 响应值进行排序
    index = argsort(candidateValues)
    
    # 将可行点的位置保存到数组中
    allowedLocations = zeros(harrisim.shape) 
    allowedLocations[minDist : -minDist, minDist : -minDist] = 1

    # 按照minDistance 原则，选择最佳Harris点
    filteredCoords = []
    for i in index:
        if(allowedLocations[coords[i, 0], coords[i, 1]] == 1):
            filteredCoords.append(coords[i])
            allowedLocations[(coords[i, 0] - minDist) : (coords[i, 0] + minDist),
                             (coords[i, 1] - minDist) : (coords[i, 1] + minDist)] = 0
    
    return filteredCoords

# 显示角点
def plotHarrisPoints(img, filteredCoords):
    """
        绘制图像中检测到的角点
    """
    figure()
    #灰度图
    gray()
    #显示图
    imshow(img)
    # 显示点
    plot([p[1] for p in filteredCoords], [p[0] for p in filteredCoords], "*")
    # 关闭坐标
    axis('off')
    show()
    
## 返回周围点    
def getDescriptors(image, filteredCoords, wid = 5):
    """
        对于每个返回的点，给出周围2*wid+1个像素的值
    """
    desc = []
    for coords in filteredCoords:
        patch = image[coords[0] - wid:coords[0] + wid + 1, 
                      coords[1] - wid:coords[1] + wid + 1].flatten()
        desc.append(patch)
        
    return desc


# 对于第一个图片中的每个角点描述子，使用归一化互相关，选取他再第二幅图像中的匹配角点
def match(desc1, desc2, threshold = 0.5):
    n = len(desc1[0])
    d = -ones((len(desc1),len(desc2)))
    
    for i in range(len(desc1)):
        for j in range(len(desc2)):
            d1 = (desc1[i] - mean(desc1[i])) / std(desc1[i])
            d2 = (desc2[j] - mean(desc2[j])) / std(desc2[j])
            nccValue = sum(d1 * d2) / (n-1)
            if(nccValue > threshold):
                d[i][j] = nccValue
    ndx = argsort(-d)
    matchscores = ndx[:,0]
    return matchscores


# 使用match函数正反各匹配一次，舍去两次匹配中不同的
def matchTwoSided(desc1, desc2, threshold = 0.5):
    """
     两边对称的match 
    """
    match12 = match(desc1, desc2, threshold)
    print(match12)
    match21 = match(desc2, desc1, threshold)
    print(match21)
    # 舍去不同的
    index12 = where(match12>=0)[0]
    for n  in index12:
        if(match21[match12[n]] != n):
            match12[n] = -1
    print("mathc12")
    print(match12)
    return match12


# 返回将两张图片并排拼接成一幅新的图像
def appendImages(im1, im2):
    # 选取具有最少行数的图像，然后填充足够的空行
    rows1 = im1.shape[0]
    rows2 = im2.shape[0]
    
    if (rows1 < rows2):
        im1 = concatenate((im1, zeros((rows2 - rows1, im1.shape[1]))), axis = 0)
    elif (rows1 > rows2):
        im2 = concatenate((im2, zeros((rows1 - rows2, im2.shape[1]))), axis = 0)
    # 都没有说明行数相同，无需填充
    
    return concatenate((im1,im2), axis = 1)

def plotMatches(im1, im2, locs1, locs2, matchscores, showBelow = True):
    """
        显示一幅带有连接匹配之间连线的图片
        输入：
            im1, im2 图像
            locs1，locs2 特征位置
            matchscores：match的输出
            showBelow：如果图像应该显示在匹配的下方
    """
    im3 = appendImages(im1, im2)
    if showBelow:
        im3 = vstack((im3,im3))
    imshow(im3)
    cols1 = im1.shape[1]
    for i,m in enumerate(matchscores):
        if(m > 0):
            plot([locs1[i][1], locs2[m][1] + cols1], [locs1[i][0],locs2[m][0]],'c')
    axis('off')
    

def doIt(im1, im2):
    wid = 5
    harrisim = computeHarrisResponse(im1, 5)
    filteredCoords1 = getHarrisPoints(harrisim, wid + 1, 0.3)
    d1 = getDescriptors(im1, filteredCoords1, wid)
    plotHarrisPoints(im1, filteredCoords1)
    harrisim = computeHarrisResponse(im2, 5)
    filteredCoords2 = getHarrisPoints(harrisim, wid + 1, 0.3)
    d2 = getDescriptors(im2, filteredCoords2, wid)
    plotHarrisPoints(im2, filteredCoords2)
    
    print("MATCHING!!!")
    matches = matchTwoSided(d1,d2)
    
    figure()
    gray()
    plotMatches(im1, im2, filteredCoords1, filteredCoords2, matches)
    show()
    

def imresize(im, sz):
    """
    使用PIL对象重定义图像数组大小
    im : 重定义大小的图像
    sz : 重定义的大小
    """
    pil_im = Image.fromarray(uint8(im))
    return array(pil_im.resize(sz))
if __name__ == "__main__":
    im = array(Image.open(r'C:\Users\wangsy\Desktop\learning\ch4\tsukuba\scene1.row3.col1.ppm').convert('L'))
    im2 = array(Image.open(r'C:\Users\wangsy\Desktop\learning\ch4\tsukuba\scene1.row3.col5.ppm').convert('L'))
    
    doIt(im, im2)

```

### 结果

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20200415080724859.png" alt="image-20200415080724859" style="zoom: 67%;" />

可以看到，这个匹配结果还凑活，但是说实话，不咋地。我准备以后开个专题来讲一下几个传统的立体匹配方法，因为最近也有可能要做相关的东西，正好复习一下。所以这一次，这方面的就先带过去了。

我们可以看出来，匹配的核心是相似性的度量，也就是描述子，在下一节我们会学习最好的一种描述子之一。