---
title: 【LevelDB】 Log 设计与实现
date: 2021-04-28 01:13:08.0
updated: 2021-10-26 21:49:37.769
url: /archives/leveldblogdesignandimpl
categories: 
- LevelDB
tags: 
- LevelDB
- 数据库

---

Log即日志系统，在写入数据前会先通过Log对写入的内容进行记录，这篇文章会讲解其记录的内容与原理
<!--more-->

## LogWriter

先讲写日志的部分。

### WriteableFile

我们先从可写文件讲起，先看定义（这里不讨论他的实现，只讨论如何使用）：

```cpp
class LEVELDB_EXPORT WritableFile {
 public:
  WritableFile() = default;

  WritableFile(const WritableFile&) = delete;
  WritableFile& operator=(const WritableFile&) = delete;

  virtual ~WritableFile();

  virtual Status Append(const Slice& data) = 0;
  virtual Status Close() = 0;
  virtual Status Flush() = 0;
  virtual Status Sync() = 0;
};
```

可写文件是一个抽象类，它定义了四种操作接口：

- `Append`：向文件写缓冲区后追加一个切片
- `Close`：关闭写缓冲区
- `Flush`：通过系统调用，将写缓冲区的内容交给操作系统，让操作系统写入文件
- `Sync`：通过系统调用，强制让操作系统将缓冲区内内容写入文件

看完这四个接口的定义，会产生一个疑问：`Flush`/`Sync`之间区别何在？

实质上`Flush`仅仅是将当前程序的写缓冲区中的内容拷贝到了操作系统写缓冲区，内容并没有真正被写入到文件，还需要等待操作系统将其写入文件。在执行`Flush`后若掉电，内容可能没有被写入。

而`Sync`会强制将系统缓冲区的内容写入磁盘，这样可以保证：执行完成后内容已经写入到磁盘。此时掉电，内容不会丢失。了解更多，可以 [flow link](https://linux.die.net/man/8/sync)

可以看到，两者的区别在于：`Flush`的安全性较低，但是更快，`Sync`比较安全，但是较慢，两难全。

### LogWriter

接下来我们讨论 `LogWriter`， 我们将套路以下几个问题：

- 写到哪里？
- 写什么？
- 特殊情况处理？

#### 写到哪里

是的，写到前面的`WritableFile`中。

#### 写什么

这就是这个文章中最重要的部分了，首先我们来学习一下：

##### 日志信息格式：

日志是由一条条信息组成的，在这里我们将探讨，每一条信息长什么样。

首先，每条日志想要记录的就是一个字符串，在`LevelDB`中，字符串就是`Slice`。其次，为了方便读取、同时为了读取的安全性考虑，为每条日志封装了头部`Header`。

封装后的日志结构如下：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/log_fmt.png" title="1. 日志数据格式" />

<center><b>1. 日志数据格式</b></center>

其中：

- `check_sum`：与各种网络协议中的`check_sum`相同，用于检测信息是否出错
- `lenth`：标记数据段长度
- `type`：标记当前段的状态

在这里，我们会产生一个疑问：这个`type`是做什么用的呢？这个问题，我们放在下一部分来讲。



#### 日志文件格式：

接下来，我们来讨论一条条日志信息，在文件中是如何排列的。

首先，在`LevelDB`中，我们将日志文件分成若干个`Block`，其中每个`Block`大小为`32768Byte`，如下图所示。

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/log_file_devide_into_block.png" title="2. block排列" />

<center><b>2. block排列</b></center>

在理想情况下，日志信息的排列方式如下：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/prefer_log_in_block.png" title="3. 预期的数据分布" />

<center><b>3. 预期的数据分布</b></center>

但是，由于日志信息的长度不固定，这里的`Block`不可能完美的放完每个日志，所以我们需要对特殊情况进行讨论，请看下一小节。

### 特殊情况处理

#### 情况枚举

接着上一小节来讲，这里我们来看一下，可能出现哪些情况：

- **最好的情况**：当前的Block剩余的空间能够塞下整条`Log`
- **放不下的情况**：当前Block剩余的空间不能塞下整条`Log`，这种情况可以细分为：
  - **放得下头**：剩余空间大于等于`7Byte`，能够放下头
  - **放不下头**：剩余空间小于`7Byte`，放不下头了

#### 解决方案

一句话概括：能直接在一个Block中塞进去就直接塞，塞不进去就拆成多条塞。

`TCP`协议中使用一个字段标记当前块是否为最后一块，这里也是如此：使用`type`字段标识当前快是哪一块，`type`字段可选值如下：

```cpp
enum RecordType {
  // Zero is reserved for preallocated files
  kZeroType = 0,

  kFullType = 1,

  // For fragments
  kFirstType = 2,
  kMiddleType = 3,
  kLastType = 4
};
```

这里，如果当前条目能够直接塞入当前的Block，那么就是`kFullType`，否则，就会将当前条目拆分为多条：

- 第一条标记为：`kFirstType`
- 中间条目标记为：`kMiddleType`
- 最后一条标记为：`kLastType`

为了加强理解，我们看一个张图：它展示了：写入一个长度为`2 * BlockSize - HeaderSize`的`Record`后的Log文件

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/write_in_larger_slice.png" title="4. 跨Block日志条目" />

<center><b>4. 跨Block日志条目</b></center>

### `golang` 实现

请见[flow link](https://github.com/goleveldb/goleveldb/tree/develop) 目录：

- `slice`：切片实现
- `file`：文件接口声明
- `log`：可写文件实现



## LogReader

再讲读日志的部分，先明确：读日志的目标就是把刚才写进去的东西再读出来。

### SequentialFile

同样，讲一下对应的文件接口：

```cpp
class LEVELDB_EXPORT SequentialFile {
 public:
  SequentialFile() = default;

  SequentialFile(const SequentialFile&) = delete;
  SequentialFile& operator=(const SequentialFile&) = delete;

  virtual ~SequentialFile();
  virtual Status Read(size_t n, Slice* result, char* scratch) = 0;
  virtual Status Skip(uint64_t n) = 0;
};
```

`SequentialFile`的中文含义是：顺序文件，意思就是他只能顺序读取，需要提供两个方法：

- `Read`：从文件中读`n`个`byte`到`Slice`，其中`scratch`类似于缓冲区
- `Skip`：跳过`n`个`byte`

### LogReader

`LogReader`接口定义如下：

```cpp
class Reader {
 public:
  // Interface for reporting errors.
  class Reporter {
   public:
    virtual ~Reporter();

    virtual void Corruption(size_t bytes, const Status& status) = 0;
  };
  Reader(SequentialFile* file, Reporter* reporter, bool checksum,
         uint64_t initial_offset);

  Reader(const Reader&) = delete;
  Reader& operator=(const Reader&) = delete;

  ~Reader();
  bool ReadRecord(Slice* record, std::string* scratch);
  uint64_t LastRecordOffset();
 private:
  // Extend record types with the following special values
  enum {
    kEof = kMaxRecordType + 1,
    kBadRecord = kMaxRecordType + 2
  };

  bool SkipToInitialBlock();

  unsigned int ReadPhysicalRecord(Slice* result);

  void ReportCorruption(uint64_t bytes, const char* reason);
  void ReportDrop(uint64_t bytes, const Status& reason);

  SequentialFile* const file_;
  Reporter* const reporter_;
  bool const checksum_;
  char* const backing_store_;
  Slice buffer_;
  bool eof_;  // Last Read() indicated EOF by returning < kBlockSize

  uint64_t last_record_offset_;
  uint64_t end_of_buffer_offset_;

  uint64_t const initial_offset_;

  bool resyncing_;
}
```

它对外提供了以下方法：

- `ReadRecord`：从当前文件中读取一个`Record`
- `LastRecordOffst`：这个就是用于获取当前读取到的最后一个`Record`的偏移量

除了对外的方法外，还需要特别在意：

- `resyncing_`：这个置为`true`时会略过当前的`Record`，直接读下一个`Record`（通过忽略当前的`MiddleKind,LastKind`实现）

此外，`Reader`中还定义了一个`Reporter`接口，用来进行错误报告。Reporter接口下一步再讲。



#### ReadRecord方法实现

总体来说可以用这样一张图来概括：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/read_record.png" title="5. 读取日志流程" />

<center><b>5. 读取日志流程</b></center>

实质上就是去读一个个被分片了的`Record`，把他们封装成一个完整的`Record`。

这其中，还需要关注一下读物理`Record`这一步，其过程如下：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/read_phy_record.png" title="6. 恢复日志流程" />

<center><b>6. 恢复日志流程</b></center>

#### 代码实现：[flow Link](https://github.com/goleveldb/goleveldb/tree/6189ae1a9683b3553c70ee3171d437482fc74ee6)