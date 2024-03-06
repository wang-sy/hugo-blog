---
title: 简易微服务集群搭建指南
date: 2021-12-06 21:18:34.946
updated: 2021-12-08 18:14:35.715
url: /archives/microservicedeployink8s
categories: 
- k8s
tags: 
- k8s

---

从完成一个grpc服务开始逐步搭建微服务集群
<!--more-->

# 简易微服务集群搭建指南

这篇文章是一篇偏操作的文章，跟随这篇文章，你可以学会：

- 搭建一个简单的`grpc`服务；
- 使用`Docker`将服务打包；
- 使用`k8s`将服务以`Deployment`的形式部署，并以`Service`的形式对外开放；
- 在`k8s`中，区分内部服务与外部服务；



这篇文章主要面对基本什么都不会的hxd，所以比较细致，比较流水账，可以自行选择需要的部分来看。

同时，这篇文章只负责教怎么做，至于`grpc`、`k8s`都是啥可以自行百度。



# 完成一个简单的`grpc`服务并在本机运行

## `grpc`安装

`grpc`是谷歌推出的一款`rpc`框架，它支持多种语言并且使用范围颇广，它的安装也可以参考[`grpc`官方文档](https://www.grpc.io/docs/languages/go/quickstart/)。在安装`grpc`前，需要先安装好`golang`，并且对`GOPATH`进行配置，并将`$GOPATH/bin`添加入`PATH`。

首先安装`Protocol Buffer`：

```shell
sudo apt install -y protobuf-compiler
```

安装完成后，需要使用`protoc --version`进行验证，确保工具可用。

接下来安装`go`语言的插件：

```shell
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.26
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.1
```

如果没有意外的话，`grpc`就安装好了。

## `grpc`创建简单服务并在本地运行

在这一小节中，我们使用`grpc`完成一个简单的`ping-pong`服务：

- 服务端开放一个远程调用方法，接收来自客户端的字符串
  - 客户端发来的是`ping`，那么服务端返回`pong`
  - 客户端发来的不是`ping`，服务端返回错误。

完成这一服务后，我们将在本地运行该程序。

### 项目结构

在`GOPATH`下，先新建`pingpong`文件夹，并在进入文件夹后执行：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [17:35:56] 
$ go mod init
go: creating new go.mod: module pingpong
```



在本项目中，所有文件都存储在一个项目中，其中`gomod`用于存储项目名称和依赖的包信息，项目的其他部分由三个文件夹组成：

```zsh
client protobuf go.mod service
```

- `protobuf`：用于定义服务端接口，生成中间代码；
- `service`：引用并实现`protobuf`中定义的接口，对外提供服务；
- `client`：通过`protobuf`生成的中间代码访问`service`，完成远程过程调用；

在项目编译完成后，将存在两个可执行文件：

- `service`：运行`service`后，将开启服务，等待客户端访问；
- `client`：用于访问`service `；



### `protobuf`的定义与中间代码的生成

在`protobuf`文件夹中新建`pingpong.proto`进行编辑，我们希望：

- 服务端对外提供`pingpong`服务；
- 服务端接收`pingpongRequest`，并且返回`pingpongResponse`给客户端。

因此做出如下定义：

```protobuf
syntax = "proto3";

option go_package = "pingpong/protobuf";

service Ops {
  // PingPong return pong if request.message euqal to ping.
  rpc PingPong (PingPongRequest) returns (PingPongResponse) {}
}

message PingPongRequest {
  string message = 1;
}

message PingPongResponse {
  string message = 1;
}
```

- 通过`service Ops`定义了一个`Ops`服务，其中有一个远程调用方法`PingPong`，该方法接收`PingPongRequest`，返回`PingPongResposne`。
- 通过`message PingPongRequest`定义了消息，消息中包含一个`string`类型的成员，被称为`message`；

除此之外，还对包名等进行了定义：

- 通过`option go_package`：定义包所在路径为`pingpong/protobuf`，`pingpong/protobuf`就是当前项目的包名（与gomod项目名一致）；



接下来，我们生成中间代码：

```zsh
protoc ./pingpong.proto  --go_out=. --go-grpc_out=.  
```

将生成的代码放到本目录下，然后运行`go mod tidy`即可。

运行完`go mod tidy`后，`go.mod`文件如下：

```go
module pingpong/protobuf

go 1.17

require (
	google.golang.org/grpc v1.42.0
	google.golang.org/protobuf v1.27.1
)

require (
	github.com/golang/protobuf v1.5.0 // indirect
	golang.org/x/net v0.0.0-20200822124328-c89045814202 // indirect
	golang.org/x/sys v0.0.0-20200323222414-85ca7c5b95cd // indirect
	golang.org/x/text v0.3.0 // indirect
	google.golang.org/genproto v0.0.0-20200526211855-cb27e3aa2013 // indirect
)
```

到此为止，`protobuf`已经编写完成。



### 实现`service`

接下来在`service`中实现服务接口，服务接口的实现与运行分为两部分：

- 首先：需要实现`protobuf`中定义的接口；
- 其次：需要将实现好的对象注册到服务中；

实现代码如下：

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net"

	"pingpong/protobuf"

	"google.golang.org/grpc"
)

// service impl protobuf.Ops to provide pingpong service.
type service struct {
	protobuf.UnimplementedOpsServer
}

// PingPong check req.Message, for msg euqal to ping, return pong, else return error.
func (s *service) PingPong(ctx context.Context, req *protobuf.PingPongRequest) (*protobuf.PingPongResponse, error) {
	if req.Message == "ping" {
		return &protobuf.PingPongResponse{Message: "pong"}, nil
	}

	return nil, fmt.Errorf("expect message = ping, but get message = %v", req.Message)
}

func main() {
	lis, err := net.Listen("tcp", "0.0.0.0:23333")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	s := grpc.NewServer()
	protobuf.RegisterOpsServer(s, &service{})

	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
```



在这里，我们定义了`service`结构体，它实现了`protobuf`中的`OpsServer`接口，定义如下：

```go
// OpsServer is the server API for Ops service.
// All implementations must embed UnimplementedOpsServer
// for forward compatibility
type OpsServer interface {
	// PingPong return pong if request.message euqal to ping.
	PingPong(context.Context, *PingPongRequest) (*PingPongResponse, error)
	mustEmbedUnimplementedOpsServer()
}
```



随后，在`main`函数中，我们监听了`23333`端口，并且使用`protobuf.RegisterOpsServer`方法注册服务，最终使用` s.Serve(lis)`的方法运行服务。

到此为止，`pingpong`服务已经实现了，运行`service`后，会开启并长期保持`grpc`服务。



### 实现`client`

接下来我们实现`client`，在这里我们会利用`protobuf`生成的代码来访问`service`；访问的过程也是非常简单：

- 首先：指定目标服务的`ip:port`，新建一个`client`；
- 随后：通过`client`封装好的方法直接访问即可；

实现如下：

```go
package main

import (
	"context"
	"log"
	"pingpong/protobuf"

	"google.golang.org/grpc"
)

func main() {
	conn, err := grpc.Dial("localhost:23333", grpc.WithInsecure())
	if err != nil {
		log.Fatalf("did not connect: %v", err)
	}
	defer conn.Close()

	client := protobuf.NewOpsClient(conn)

	pingReq := &protobuf.PingPongRequest{Message: "ping"}
	pingResp, err := client.PingPong(context.Background(), pingReq)
	log.Printf("send req = %v, get resp = %v, %v", pingReq, pingResp, err)

	otherReq := &protobuf.PingPongRequest{Message: "not ping"}
	otherResp, err := client.PingPong(context.Background(), otherReq)
	log.Printf("send req = %v, get resp = %v, %v", otherReq, otherResp, err)
}
```

在这里：

- 首先：使用`grpc.Dial`方法指定`service`地址为`localhost:23333`，建立与`service`的连接，并通过该链接生成`client`；
- 随后：使用`client`封装的`PingPong`方法，分别向`service`发送`message`为`ping`和`not ping`的两条消息，并分别打印其结果；



这里的`client`代码，会向`service`发送两个`rpc`请求，并输出其返回结果，运行结束后将直接退出。



### 编译并运行服务端与客户端

通过`go build`进行编译，编译时通过`-o`指定输出文件名称分别为`client_exec`、`service_exec`：

```zsh
go build -o ./client_exec ./client/main.go
go build -o ./service_exec ./service/main.go
```

先运行`service_exec`，效果如下（没有输出任何提示信息，因为我没有`Println`）：

```go
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [17:58:37] 
$ ./service_exec 
```

再运行`client_exec`，效果如下：

```go
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [18:01:59] 
$ ./client_exec 
2021/12/06 18:02:04 send req = message:"ping", get resp = message:"pong", <nil>
2021/12/06 18:02:04 send req = message:"not ping", get resp = <nil>, rpc error: code = Unknown desc = expect message = ping, but get message = not ping
```

这里一共输出了两条记录：

- 第一条记录表示向服务端发送了`ping`，并且收到了`message = pong`；
- 第二条记录表示向服务端发送了`not ping`，并且：
  - 收到的`resp = nil`，表示消息体为空；
  - 同时收到了来自服务端的错误提示；



## 简单总结

在这一节中，你学习到了：如何安装、编写、运行`grpc`。并且在本机上运行了`grpc`服务，还通过自定义的`client`访问了其中的`pingpong`方法。

你已经完成了一个类似于`helloworld`的`grpc`项目！

接下来，我们会将这个项目通过`docker`打包成镜像，并且在`kubernetes`集群中以服务的方式运行。



# 将`grpc`服务打包为镜像并发布到`DockerHub`

## 编写`Dockerfile`

`Dockerfile`用于描述镜像的构建过程，我们写了如下的`dockerfile`：

```dockerfile
FROM golang:1.16 as builder

WORKDIR /go/src/pingpong
COPY . .

RUN go env -w GO111MODULE=on && \
    go env -w GOPROXY=https://goproxy.io && \
    go build -tags netgo -o pingpong_service ./service/main.go

FROM busybox

COPY --from=builder /go/src/pingpong/pingpong_service /pingpong_service

EXPOSE 23333
ENTRYPOINT [ "/pingpong_service" ]
```

这里可以分为上下两部分理解：

- 第一部分中，这一部分将根据源码构建可执行文件，过程中使用`golang:1.16`作为`builder`：
  - 通过`WORKDIR`规定，所有指令在路径`/go/src/pingpong`中执行
  - 同时，将本地`pingpong`下的所有代码拷贝到容器中的工作目录中；
  - 最后，运行`go build`，编译`service`代码，生成可执行文件到`/go/src/pingpong/pingpong_service`
- 第二部分中，构建运行镜像，第二部分的构建结果将作为最终的结果：
  - 本部分基于`busybox`，相较于第一部分基于的镜像，这是一个非常轻量的`linux`环境；
  - 随后：使用`COPY`指令，指定从`builder`的`/go/src/pingpong/pingpong_service`拷贝到`/pingpong_service`；这一步将刚才编译好的可执行文件拷贝到运行镜像中。
  - 最后：通过`EXPOSE`指令对外暴漏`23333`端口，并通过`ENTRYPOINT`指定，容器运行时，直接执行编译好的可执行文件`pingpong_service`；



上面这种写法的主要优势在于通过利用了`golang:1.16`这个非常完备的编译镜像进行编译，再利用`alpine`这个体积非常小的镜像进行执行，最终构建出的镜像体积非常小。



## 编译容器并在本地运行

执行命令:

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [18:29:47] C:1
$ docker build -t pingpong_service .
```

这表示基于当前目录的`Dockerfile`构建镜像，并将构建结果命名为`pingpong_service`，等待指令运行结束后，可以观察到提示：

![image-20211206183829425](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211206183829425.png)



通过`docker images`来看一下本地是否有相应的镜像存在：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [18:39:06] C:130
$ docker images                     
REPOSITORY         TAG       IMAGE ID       CREATED         SIZE
pingpong_service   latest    673a79eb4ef3   5 minutes ago   17.1MB
```

这个镜像的大小仅有`17.1MB`。



接下来，需要通过`docker run`指令来将容器跑起来，但是在跑容器之前，需要注意：

- `pingpong_service`在启动时会绑定`23333`接口，将其封装到镜像内后，绑定的不是本机的`23333`接口；

因此需要将镜像的`23333`接口，映射到本地的`23333`接口，这个概念非常容易理解，因此在运行时，通过`-p host_port:container_port`方法进行映射，同时使用`-d`使得服务能够后台运行：

```zsh
docker run -d -p 23333:23333 pingpong_service
```

运行起来后，使用指令`docker ps`来查看跑起来的镜像：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [20:31:39] 
$ docker ps -a
CONTAINER ID   IMAGE                    COMMAND                  CREATED         STATUS         PORTS                                                                                                                                  NAMES
3defb55eace9   pingpong_service         "/pingpong_service"      4 minutes ago   Up 4 minutes   0.0.0.0:23333->23333/tcp, :::23333->23333/tcp                                                                                          competent_mayer
```



接下来，继续使用上一节中编译出来的`client_exec`来验证是否可用，得到结果如下，证明服务可用：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [20:41:52] C:130
$ ./client_exec
2021/12/06 20:41:53 send req = message:"ping", get resp = message:"pong", <nil>
2021/12/06 20:41:53 send req = message:"not ping", get resp = <nil>, rpc error: code = Unknown desc = expect message = ping, but get message = not ping
```

## 将容器推送到`DockerHub`

`DockerHub`和`GitHub`有点相似，`GitHub`作为代码的存储仓库存在，而`DockerHub`作为docker镜像的存储仓库存在。

想要使用`DockerHub`，需要现在[`DockerHub`官网](https://registry.hub.docker.com/)注册账号，注册账号完毕后，在命令行中通过`docker_id`和密码登录：

```zsh
docker login
```



首先使用`docker tag`为镜像命名，其中`pcgvphonebackend`是`docker_id`，需要根据自身情况修改：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [21:04:50] C:130
$ docker tag pingpong_service:latest pcgvphonebackend/pingpong_service:v1    
```

在打好标签后就可以推送到远端了：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [21:08:16] C:130
$ docker push pcgvphonebackend/pingpong_service:v1                       
The push refers to repository [docker.io/pcgvphonebackend/pingpong_service]
4df9e337354e: Pushed 
9f2549622fec: Mounted from library/busybox 
v1: digest: sha256:e443f60b2bfa24ea89c984a815f1f753b810934a37d55c74c8ce3463b9276270 size: 738
```

经过推送后，在任何机器上都可以通过`docker pull pcgvphonebackend/pingpong_service:v1`来拉取该镜像。



## 简单总结

在这一节中，我们学会了将一个服务包装成镜像，并把它通过`docker`运行。在包装、部署的过程中：

- 我们通过区分 `builder`和运行容器的方法降低运行容器的体积；
- 通过将容器推送到`DockerHub`降低远程部署难度；



但是在实际开发过程中，一个服务会在集群中被部署多份，服务间的访问往往不能通过`ip:port`直接访问。在下一节中，将学习如何使用`k8s`部署容器到集群。



# k8s集群搭建

`k8s`需要一个`master`节点和多个`worker`节点，这就意味着需要多台物理机或是虚拟机，对多台机器进行操作无疑是繁琐的。`minikube`将这个过程简化，直接敲两行命令就能起一个集群，非常适合我这种搭个玩具的需求。

因此，在这节中，我们会：使用`minikube`搭建3节点`k8s`集群，并且使用`kubectl`对集群进行管理。

## 安装`kubectl`

在安装`minikube`前需要先安装`kubectl`，从名字上就能看出来，`kubectl`是用于管理`k8s`集群的命令行工具。安装过程可以参考[`k8s`官方文档](https://kubernetes.io/zh/docs/tasks/tools/install-kubectl-linux/)。下面基本上就是把官方文档抄了一遍，没啥意思。



首先使用`curl`下载`kubectl`的可执行文件。

```zsh
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
```

再下载校验和文件，并且进行校验

```zsh
curl -LO "https://dl.k8s.io/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl.sha256"
echo "$(<kubectl.sha256) kubectl" | sha256sum --check
```

收到结果`kubectl: OK`说明校验通过，最后直接安装：

```zsh
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

安装完成后，验证一下是否可用：

```zsh
$ kubectl version

Client Version: version.Info{Major:"1", Minor:"22", GitVersion:"v1.22.4", GitCommit:"b695d79d4f967c403a96986f1750a35eb75e75f1", GitTreeState:"clean", BuildDate:"2021-11-17T15:48:33Z", GoVersion:"go1.16.10", Compiler:"gc", Platform:"linux/amd64"}
```

此时`k8s`集群根本不存在，所以`kubectl`还没啥用。



## 安装`minikube`并搭建集群

接下来安装`minikube`并且用它搭个集群，这个过程也是跟着[`minikube`官方文档](https://minikube.sigs.k8s.io/docs/start/)进行操作即可，看二道贩子写的也没啥意思。

直接下载二进制文件，并安装即可。

```zsh
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

安装完成后，验证一下是否安装成功：

```zsh
$ minikube version
minikube version: v1.24.0
commit: 76b94fb3c4e8ac5062daf70d60cf03ddcc0a741b
```



接下来，使用`minikube`搭建一个集群，这个过程[`minikube`官方文档](https://minikube.sigs.k8s.io/docs/start/)中写的也是非常详细，建议直接看官方文档。

使用`minikube start`命令，新建一个`k8s`集群：

![image-20211206161618773](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211206161618773.png)

> 需要注意的是，在`start`集群时需要使用`minikube start --cni=flannel`，`minikube`会自动安装`flannel`插件，这使得`pod`可以跨节点通信。

安装完成后，`minikube`会将集群的配置信息放到`~/.kube/config`中，`kubectl`可以通过`config`对集群进行访问和管理，我们使用`kubectl`查看节点：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/.kube [16:21:29] C:130
$ kubectl get nodes
NAME       STATUS   ROLES                  AGE   VERSION
minikube   Ready    control-plane,master   11m   v1.22.3
```

可以看到，当前的集群中存在一个 `master`节点，`master`节点对内进行管理、统计，对外和用户交互，根据用户的指令执行操作或是提供信息。除了`master`节点外，集群还需要`worker`节点，`worker`会被`master`管理，在其调度下，服务会被部署到`worker`节点中。

下面我们使用`minikube node add`指令向集群中添加`worker`节点：

![image-20211206163118000](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211206163118000.png)

如上图所示，经过两次`node add`后，我们的集群中已经有一个`master`节点和两个`worker`节点。



# 将`grpc`服务部署到集群

在这一节中，我们将学习：

- `k8s`集群中服务的组织结构；
- 如何在`k8s`集群中部署服务；

`k8s`还是比较复杂的，在这一节中，只会讲解一小部分相关的概念，以支持

## k8s中的组织结构

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/module_04_services.svg" alt="img" style="zoom: 125%;" />

自下而上观察`k8s`集群，可以将集群中的容器分为三层：

- 最底层的是容器`container`，每个容器就是一个运行中的`docker`镜像，就像我们上一节中构建出来的一样；
- 中层的是一个`Pod`，`Pod`就像是以往服务中的一台物理机一样，其中可能包含多个`container`。每个`Pod`在集群中都拥有独立的`IP`地址，供其他节点访问；
- 最上层是`Deployment`：每一个`Deployment`下会有多个完全一致的`Pod`；



可以看作一组`Deployment`是一组完全相同的`Pod`的集合（虽然这么说很死板），这往往难以理解， 你可以带着疑问继续阅读。



现在，我们可以通过`Deployment`在集群中批量部署`Pod`，但是外部用户无法访问具体的服务，于是`Service`就应运而生。`Service`对内或对外暴漏一组`Pod`，来供用户访问。换而言之：`k8s`中记录了`Service`和一组`Pod`的对应关系，在用户用户的视角中，只存在`Service`的概念，用户通过`Service`进行访问，`k8s`分配某一个具体的`Pod`进行响应。



在这一小节中，我们学习了`k8s`集群的简单组成，在下一小节中，将学习如何通过`Deployment`将之前开发的`pingpong_service`部署到集群中。

## 通过`Deployment`部署`pingpong_service`并通过`Service`访问

在这一节中，我们先将`pingpong_service`通过`depolyment`的形式部署到集群中，再通过`service`的形式对外暴露。



### 通过`Deployment`部署`pingpong_service`

`k8s`中存在着非常多种的对象，为了简化维护过程，`k8s`创造了一套使用`yaml`对象描述被管理对象的通用描述方法，你可以在[官方文档](https://kubernetes.io/zh/docs/tasks/manage-kubernetes-objects/declarative-config/)中查看更多关于配置文件的描述：

新建一个描述文件`pingpong_service_deployment.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pingpong-service-backend-deployment
spec:
  selector:
    matchLabels:
      app: pingpong-service-backend
  replicas: 3
  template:
    metadata:
      labels:
        app: pingpong-service-backend
    spec:
      containers:
      - name: pingpong-service-backend
        image: pcgvphonebackend/pingpong_service:v1
        ports:
        - containerPort: 23333
```

这个配置文件描述了一个`Deployment`对象，其中记录了很多的信息：

- `metadata`元数据，用于记录这个`Deployment`的名称，以及他的标签、`namespace`等等信息。在这里只记录了它的名称；
- `spec`字段定义了该`Deployment`的期望状态，我们拆解来看
  - `replicas`记录该`Deployment`需要有多少份相同的`Pod`副本；
  - `template`记录每一个`Pod`副本的内容，其中：
    - `containers`以列表的形式记录`Pod`中的每一个容器；



在完成描述文件后，可以通过`kubectl apply`来将对象提交到集群：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [22:40:46]
$ kubectl apply -f ./pingpong_service_deployment.yaml
deployment.apps/pingpong-service-backend-deployment created
```



提交成功后，可以通过`kubectl get deployment`、`kubectl get pods`来观察部署的情况，部署成功后如图所示：

![image-20211206225850113](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211206225850113.png)



同时，可以通过`kubectl describe pods`来获取每一个`pod`的详细信息，以我们的`deployment`中的`pod`之一为例：

![image-20211206230113360](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211206230113360.png)

该命令可以获取到`Pod`的状态、描述信息，我们也可以发现，服务被部署在`minikube-m03`上。



经过统计，我们部署的`Deployment`中，有两个部署在`minikue-m03`，一个部署在`minikube-m02`，部署在哪一台机器上完全由`k8s`决定。当服务宕机或是节点缺失导致`Pod`副本数量降低时，`k8s`会自动将重新选择节点部署`Pod`，直到节点数量达到提交的`replicas=3`为止。

### 通过`Service`将`deployment`暴漏给外部用户

在上一节中，我们通过`Deployment`将服务部署在集群中，但是我们怎么去访问这个服务呢？在这一节中，我们将使用`Service`来将`Deployment`暴漏给外部用户进行访问。

与`Deployment`对象一样，`Service`对象也可以通过同样的方法进行描述：

新建文件`pingpong_service.yaml`：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pingpong-service-backend-service
  labels:
    app: pingpong-service-backend
spec:
  ports:
  - port: 23333
    targetPort: 23333
    protocol: TCP
  selector:
    app: pingpong-service-backend
  type: NodePort
```

这个信息非常易懂，我们只讲解下半部分内容：

- `ports`描述需要对外开放的端口，我们的服务在23333上，使用`TCP`协议；
- 使用`selector`选择需要开放的服务，在这里我们使用`app: pingpong-service-backend`作为选择器，将相应的`pod`暴漏；
- 这里的`Service`存在多种类型，我们选择了`NodePort`，这种方法会将服务映射到`workNode`物理机上；



关于`NodePort`类型的服务，其访问方式如下：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/v2-df8803d614f4c39e5994200932ee5da1_b.jpg" alt="img" style="zoom:80%;" />

服务打到某一个`Node`后，`Node`会将请求转发到`Service`中的某一个`Pod`中。





我们使用`kubectl apply -f ./pingpong_service.yaml`提交修改：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [23:27:12] C:130
$ kubectl apply -f ./pingpong_service.yaml           
service/pingpong-service-backend-service created
```



使用`kubectl get service`查看效果：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [0:21:32] 
$ kubectl get service
NAME                               TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)           AGE
kubernetes                         ClusterIP   10.96.0.1      <none>        443/TCP           8h
pingpong-service-backend-service   NodePort    10.102.10.54   <none>        23333:31485/TCP   59m
```

其中`kubernetes`是`k8s`默认对外提供的服务，`pingpong-service-backend-service`是我们新建的服务。



使用`kubectl describe nodes | grep ip`查看各个节点的`IP`：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [0:35:19] 
$ kubectl describe nodes | grep IP
  InternalIP:  192.168.49.2
  InternalIP:  192.168.49.3
  InternalIP:  192.168.49.4
```

集群中有三个节点，其中`master`节点的`ip`为`192.168.49.3`，剩下两个是`worker`节点的`ip`。



我们修改`client`中目标的`ip`：

```go
conn, err := grpc.Dial("192.168.49.4:31485", grpc.WithInsecure())
if err != nil {
    log.Fatalf("did not connect: %v", err)
}
defer conn.Close()
```

重新编译、运行：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [0:39:43] C:130
$ go build -o ./client_exec ./client/main.go && ./client_exec
2021/12/07 00:39:44 send req = message:"ping", get resp = message:"pong", <nil>
2021/12/07 00:39:44 send req = message:"not ping", get resp = <nil>, rpc error: code = Unknown desc = expect message = ping, but get message = not ping
```

这样就可以通过节点的`ip:port`访问集群内的服务了。



## 简单总结

在这一节中，我们将`grpc`服务的镜像通过`k8s deployment`的形式进行部署，并通过`NodePort service`的形式对外开放访问。

但美中不足的是：`Nodeport`能够将服务暴漏在所有的`Node`节点上，但是用户应该选择哪一个`Node`节点呢？这是难以指定的，在此基础上，还需要在集群外添加一`Nginx`才能够对`Node`节点进行负载均衡。



除此之外，还有两个重要的任务没有完成：

- 如何控制服务是否暴漏给集群外访问？
- 在集群内访问时能否不通过动态的`port:ip`，而是通过形如`rpc.project.service`的方式进行访问呢？

在接下来的小节中，我们会一一回答。



# 区分内部服务与外部服务

在上一节中，我们将`pingpong_service`以`NodePort`的服务类型部署到`k8s`集群中，利用多个副本对外提供服务。但并非所有服务在部署时都想被外部用户访问，因此区分内部服务与外部服务是很有必要的。

我们会将原有的`pingpong_service`转化为`k8s`集群中的内部服务，同时继续包装`client`，将其作为对外的`http`服务。

## 将`client`包装为http服务

原有的`client`会创建一个可以访问`pingpong_service`的`client`，并发送两条消息已验证服务的可用性。现在我们希望将`client`继续封装，将`PingPong`方法包装成一个`HTTP GET`请求，这样我们可以在集群外的机器上直接通过`curl`来检查服务是否可用，我们期望：

- 用户发送`HTTP GET`请求到，`http://host:port/pingpong?message=xxx`；
- 封装后的`client`发送`PingPongRequest`到`pingpong_service`，其中`message=xxx`；
- 封装后的`client`接收`pingpong_service`的`resposne`，并以`HTTP Response`的形式返回给用户；

修改可以分为两部分讨论：

- 对外`http`服务：需要使用`go`原生的http框架对外提供服务，为此需要实现其`http.HandleFunc`；
- 对内由于集群内的`Pod`地址不固定，因此希望通过服务名称进行访问；



根据以上需求，修改`client/main.go`：

```go
package main

import (
	"log"
	"net/http"
	"pingpong/protobuf"

	"google.golang.org/grpc"
)

var serviceLocation = "pingpong-service-backend-service:23333"

func handlePingPong(rw http.ResponseWriter, r *http.Request) {
	conn, err := grpc.Dial(serviceLocation, grpc.WithInsecure())
	if err != nil {
		rw.WriteHeader(http.StatusInternalServerError)
		return
	}
	defer conn.Close()

	message := r.URL.Query().Get("message")
	client := protobuf.NewOpsClient(conn)

	resp, err := client.PingPong(r.Context(), &protobuf.PingPongRequest{Message: message})
	if err != nil {
		rw.Write([]byte(err.Error()))
		return
	}

	rw.Write([]byte(resp.GetMessage()))
}

func main() {
	http.Handle("/pingpong", http.HandlerFunc(handlePingPong))

	if err := http.ListenAndServe("0.0.0.0:8080", nil); err != nil {
		log.Println(err.Error())
	}
}
```



在这个`client`中，我们将原有创建`client`、发送`msg`的逻辑封装到`handlePingPong`函数中，`handlePingPong`实现了`go`语言中通用的`http`请求处理函数。它接收`http.Request`，并将响应的结果写入`rw http.ResponseWriter`，该函数`return`后，`go http`框架会进行后续处理。在这里，收到请求后：

- 首先利用`serviceLocation`创建`client`；
- 再通过`r.URL.Query()`提取出请求`URL`中的`query`部分，从其中获取`message`参数；
- 最终将消息发送，无论收到什么，都将以字符串的形式返回；



完成`http`请求处理函数后，使用`http.Handle`方法，将该函数注册到`/pingpong`路径下，最终使用`http.ListenAndServe("0.0.0.0:8080", nil)`方法，指定监听机器的`8080`端口提供服务。



到此为止，`client`服务的包装已经完成，可以在本地运行该服务，并通过`curl`工具访问，访问结果如下图所示：

![image-20211207202445365](https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/image-20211207202445365.png)

原因非常明显，是因为`pingpong-service-backend-service`这个域名不存在，这个问题需要在集群中解决。



我们将被包装后的`client`称为`pingpong_client_server`。

## 将`pingpong_client_server`包装为镜像并发布到`k8s`

这一节是纯流水账，自己能完成就不需要看。

### 修改`dockerfile`并编译镜像

修改`dockerfile`：

```dockerfile
FROM golang:1.16 as builder

WORKDIR /go/src/pingpong
COPY . .

RUN go env -w GO111MODULE=on && \
    go env -w GOPROXY=https://goproxy.io && \
    go build -tags netgo -o pingpong_client_service ./client/main.go

FROM busybox

COPY --from=builder /go/src/pingpong/pingpong_client_service /pingpong_client_service

EXPOSE 8080
ENTRYPOINT [ "/pingpong_client_service" ]
```

编译`docker`镜像：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [20:27:38] C:130
$ docker build -t pcgvphonebackend/pingpong_client_service:v1 .
```

推送`docker`镜像到`dockerhub`：

```zsh
# wangsaiyu @ SaiyuWangPC in ~/go/src/pingpong [20:28:48] 
$ docker push pcgvphonebackend/pingpong_client_service:v1 
```

### 将`pingpong_client_service`发布为对外服务

这一过程与之前的`pingpong_service`完全相同：

`deployment`描述文件`pingpong_client_service_deployment.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pingpong-client-service-deployment
spec:
  selector:
    matchLabels:
      app: pingpong-client-service
  replicas: 3
  template:
    metadata:
      labels:
        app: pingpong-client-service
    spec:
      containers:
      - name: pingpong-client-service
        image: pcgvphonebackend/pingpong_client_service:v1
        ports:
        - containerPort: 8080
```

使用`kubectl apply -f ./pingpong_client_service_deployment.yaml`将应用变更，并使用`kubectl get pods`观察部署情况，等待全部部署完成：

```zsh
# ubuntu @ VM-0-10-ubuntu in ~ [17:12:59]
$ kubectl get pods
NAME                                                  READY   STATUS    RESTARTS   AGE
flask-pod                                             1/1     Running   0          16h
pingpong-client-service-deployment-6b97ccd969-6rg5p   1/1     Running   0          16h
pingpong-client-service-deployment-6b97ccd969-dqhxz   1/1     Running   0          16h
pingpong-client-service-deployment-6b97ccd969-ld4sb   1/1     Running   0          16h
pingpong-service-backend-service-84b86f765f-chxjz     1/1     Running   0          16h
pingpong-service-backend-service-84b86f765f-cr4tq     1/1     Running   0          16h
pingpong-service-backend-service-84b86f765f-gpjxt     1/1     Running   0          16h
```



最后，我们需要创建`Service`将`Deployment`暴漏给外部访问，因此还是选择`NodePort`形式，但这一次我们直接借助`kubectl`工具完成这一过程：

```zsh
# ubuntu @ VM-0-10-ubuntu in ~/k8s [17:16:07]
$ kubectl expose --type='NodePort' deployment/pingpong-client-service-deployment
service/pingpong-client-service-deployment exposed

# ubuntu @ VM-0-10-ubuntu in ~/k8s [17:16:37]
$ kubectl get svc
NAME                                 TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)           AGE
kubernetes                           ClusterIP   10.96.0.1       <none>        443/TCP           17h
pingpong-client-service-deployment   NodePort    10.104.99.251   <none>        8080:31598/TCP    3s
pingpong-service-backend-service     NodePort    10.109.59.76    <none>        23333:32303/TCP   42s
```

这里直接使用了`kubectl expose`命令，将`deployment/pingpong-client-service-deployment`以服务的形式暴漏，并指定了`NodePort`类型。



部署完成后，需要使用`curl`试一试跑步跑得通：

```zsh
# ubuntu @ VM-0-10-ubuntu in ~/k8s [17:16:42]
$ kubectl describe nodes | grep IP
  InternalIP:  192.168.49.2
  InternalIP:  192.168.49.3
  InternalIP:  192.168.49.4
```

这里我们访问`192.168.49.3`这一`Node`节点的`31598`端口，就可以访问到`pingpong-client-service`：

```zsh
# ubuntu @ VM-0-10-ubuntu in ~/k8s [17:16:57]
$ curl 192.168.49.3:31598/pingpong\?message=ping
pong
```



到此为止，我们将`pingpong_client_service`以`NodePort`的形式部署并供外部访问，在发送`curl 192.168.49.3:31598/pingpong\?message=ping`请求到达`pingpong_client_service`服务后，`pingpong_service`通过`"pingpong-service-backend-service:23333"`访问到`pingpong-service`完成调用。



但美中不足的是，`pingpong-service`仍然以`NodePort`形式提供服务，这代表外部用户仍然能够直接访问`pingpong-service`，这不符合我们的期望。



## 使用`ClusterIP`形式限制外部用户访问`pingpong-service`

这一小节中，我们将介绍如何将服务隔离，仅供集群内部访问。

`k8s`提供了多种`Service`类别，上一节中使用的`NodePort`形式，可以将服务映射到物理机端口上，供外部用户访问。在这一节中，我们将学习`ClusterIP`类型服务，首先将原有的服务删除，并重建一个`ClusterIP`类型服务：

```zsh
# ubuntu @ VM-0-10-ubuntu in ~ [17:44:16]
$ kubectl delete svc pingpong-service-backend-service
service "pingpong-service-backend-service" deleted

# ubuntu @ VM-0-10-ubuntu in ~ [17:44:32]
$ kubectl expose deployment/pingpong-service-backend-service
service/pingpong-service-backend-service exposed

# ubuntu @ VM-0-10-ubuntu in ~ [17:44:57] C:1
$ kubectl get svc
NAME                                 TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
kubernetes                           ClusterIP   10.96.0.1       <none>        443/TCP          17h
pingpong-client-service-deployment   NodePort    10.104.99.251   <none>        8080:31598/TCP   28m
pingpong-service-backend-service     ClusterIP   10.96.152.213   <none>        23333/TCP        7s
```

现在我们建立起了`ClusterIP`类型的`pingpong-service-backend-service `，对于该服务，`k8s`为其分配了一个`ClusterIP`，集群内的节点可以使用`ClusterIP`访问该服务，其原理如下：

<img src="https://goleveldb-1301596189.cos.ap-guangzhou.myqcloud.com/v2-53c5ca4b2b421512615ca48a927416aa_1440w.jpg" alt="img" style="zoom: 50%;" />

当`pod-nginx`需要访问`pod-python`时，会使用`service-python`的`clusterIP`进行访问，该`IP`是集群中的虚拟`IP`，在`iptable`模式下，`kube-proxy`会将`ClusterIP`到`PodIP`的映射关系记录到节点的`iptable`中，这样在请求时，会在本地将`IP`地址进行转换，`ClusterIP`会被随机转换为一个`PodIP`进行访问。换而言之，节点在通过`CluserIP`访问一个服务时，实质上是访问了服务背后的一个`Pod`。



回忆一下`pingpong_client_service`的源码，是通过服务名称进行访问的，这是因为`k8s`中存在一`coreDNS`服务，专门将`serviceName`解析到`cluserIP`。



到此为止，我们已经将`pingpong-service`转化为`k8s`集群内的内部服务，我们已经完成了一个简单集群的构建。

