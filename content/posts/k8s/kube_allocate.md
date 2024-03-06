---
title: Kubelet-Allocate 过程解析
date: 2021-04-14 20:46:10.0
updated: 2021-09-03 20:48:24.183
url: /archives/kubelet-allocateguo-cheng-jie-xi
categories: 
- k8s
tags: 
- k8s

---


从Kubelete在Allocate操作中的函数调用过程理解资源
<!--more-->

# Kubelet-Allocate 过程解析



在`kubelet`中的`allocateContainerResources`过程中，会调用`devicesToAllocate`来获取设备资源，



## allocateContainerResources

在该函数中，会遍历`container.Resources.Limits`，该`Limits`结构如下:

```go
type ResourceList map[ResourceName]resource.Quantity
```

```go
// Extended resources are not allowed to be overcommitted.
// Since device plugin advertises extended resources,
// therefore Requests must be equal to Limits and iterating
// over the Limits should be sufficient.
for k, v := range container.Resources.Limits {
    resource := string(k)
    needed := int(v.Value())
    klog.V(3).Infof("needs %d %s", needed, resource)
    if !m.isDevicePluginResource(resource) {
        continue
    }
    // Updates allocatedDevices to garbage collect any stranded resources
    // before doing the device plugin allocation.
    if !allocatedDevicesUpdated {
        m.UpdateAllocatedDevices()
        allocatedDevicesUpdated = true
    }
    allocDevices, err := m.devicesToAllocate(podUID, contName, resource, needed, devicesToReuse[resource])
    if err != nil {
        return err
    }
    if allocDevices == nil || len(allocDevices) <= 0 {
        continue
    }

    ...
}
```

对于每种扩展资源，该函数会调用`m.devicesToAllocate`对该资源进行请求，下面我们来看`m.devicesToAllocate`函数。



## devicesToAllocate

这个函数的目标就是为了获取分配给当前`Container`的Device列表，拿到这个列表后，`allocateContainerResources`函数会调用`Allocate`函数，正式的向`DevicePlugin`请求资源。

```go
// Returns list of device Ids we need to allocate with Allocate rpc call.
// Returns empty list in case we don't need to issue the Allocate rpc call.
func (m *ManagerImpl) devicesToAllocate(podUID, contName, resource string, required int, reusableDevices sets.String) (sets.String, error) 

```

这个函数拿到了资源你的名称、需求的数量、能够被复用的设备三个关键信息，在这里存在一个问题:

- (ASK)reusableDevices是如何分配的？什么样的Device会被划分为reusableDevice



```go
// Returns list of device Ids we need to allocate with Allocate rpc call.
// Returns empty list in case we don't need to issue the Allocate rpc call.
func (m *ManagerImpl) devicesToAllocate(podUID, contName, resource string, required int, reusableDevices sets.String) (sets.String, error) {
	m.mutex.Lock()
	defer m.mutex.Unlock()
	needed := required
	// Gets list of devices that have already been allocated.
	// This can happen if a container restarts for example.
	devices := m.podDevices.containerDevices(podUID, contName, resource)
	if devices != nil {
		klog.V(3).Infof("Found pre-allocated devices for resource %s container %q in Pod %q: %v", resource, contName, string(podUID), devices.List())
		needed = needed - devices.Len()
		// A pod's resource is not expected to change once admitted by the API server,
		// so just fail loudly here. We can revisit this part if this no longer holds.
		if needed != 0 {
			return nil, fmt.Errorf("pod %q container %q changed request for resource %q from %d to %d", string(podUID), contName, resource, devices.Len(), required)
		}
	}
	if needed == 0 {
		// No change, no work.
		return nil, nil
	}
	klog.V(3).Infof("Needs to allocate %d %q for pod %q container %q", needed, resource, string(podUID), contName)
	// Check if resource registered with devicemanager
	if _, ok := m.healthyDevices[resource]; !ok {
		return nil, fmt.Errorf("can't allocate unregistered device %s", resource)
	}

	// Declare the list of allocated devices.
	// This will be populated and returned below.
	allocated := sets.NewString()

	// Create a closure to help with device allocation
	// Returns 'true' once no more devices need to be allocated.
	allocateRemainingFrom := func(devices sets.String) bool {
		for device := range devices.Difference(allocated) {
			m.allocatedDevices[resource].Insert(device)
			allocated.Insert(device)
			needed--
			if needed == 0 {
				return true
			}
		}
		return false
	}

	// Allocates from reusableDevices list first.
	if allocateRemainingFrom(reusableDevices) {
		return allocated, nil
	}

	// Needs to allocate additional devices.
	if m.allocatedDevices[resource] == nil {
		m.allocatedDevices[resource] = sets.NewString()
	}

	// Gets Devices in use.
	devicesInUse := m.allocatedDevices[resource]
	// Gets Available devices.
	available := m.healthyDevices[resource].Difference(devicesInUse)
	if available.Len() < needed {
		return nil, fmt.Errorf("requested number of devices unavailable for %s. Requested: %d, Available: %d", resource, needed, available.Len())
	}

	// Filters available Devices based on NUMA affinity.
	aligned, unaligned, noAffinity := m.filterByAffinity(podUID, contName, resource, available)

	// If we can allocate all remaining devices from the set of aligned ones, then
	// give the plugin the chance to influence which ones to allocate from that set.
	if needed < aligned.Len() {
		// First allocate from the preferred devices list (if available).
		preferred, err := m.callGetPreferredAllocationIfAvailable(podUID, contName, resource, aligned.Union(allocated), allocated, required)
		if err != nil {
			return nil, err
		}
		if allocateRemainingFrom(preferred.Intersection(aligned)) {
			return allocated, nil
		}
		// Then fallback to allocate from the aligned set if no preferred list
		// is returned (or not enough devices are returned in that list).
		if allocateRemainingFrom(aligned) {
			return allocated, nil
		}

		return nil, fmt.Errorf("unexpectedly allocated less resources than required. Requested: %d, Got: %d", required, required-needed)
	}

	// If we can't allocate all remaining devices from the set of aligned ones,
	// then start by first allocating all of the  aligned devices (to ensure
	// that the alignment guaranteed by the TopologyManager is honored).
	if allocateRemainingFrom(aligned) {
		return allocated, nil
	}

	// Then give the plugin the chance to influence the decision on any
	// remaining devices to allocate.
	preferred, err := m.callGetPreferredAllocationIfAvailable(podUID, contName, resource, available.Union(allocated), allocated, required)
	if err != nil {
		return nil, err
	}
	if allocateRemainingFrom(preferred.Intersection(available)) {
		return allocated, nil
	}

	// Finally, if the plugin did not return a preferred allocation (or didn't
	// return a large enough one), then fall back to allocating the remaining
	// devices from the 'unaligned' and 'noAffinity' sets.
	if allocateRemainingFrom(unaligned) {
		return allocated, nil
	}
	if allocateRemainingFrom(noAffinity) {
		return allocated, nil
	}

	return nil, fmt.Errorf("unexpectedly allocated less resources than required. Requested: %d, Got: %d", required, required-needed)
}
```



### 发现已申请设备（在容器重启等情况下发生）

这里，会先使用这样一段语句：

```go
devices := m.podDevices.containerDevices(podUID, contName, resource)
if devices != nil {
    klog.V(3).Infof("Found pre-allocated devices for resource %s container %q in Pod %q: %v", resource, contName, string(podUID), devices.List())
    needed = needed - devices.Len()
    // A pod's resource is not expected to change once admitted by the API server,
    // so just fail loudly here. We can revisit this part if this no longer holds.
    if needed != 0 {
        return nil, fmt.Errorf("pod %q container %q changed request for resource %q from %d to %d", string(podUID), contName, resource, devices.Len(), required)
    }
}
if needed == 0 {
    // No change, no work.
    return nil, nil
}
```

这条语句会获取当前这个Pod已经申请到了的Device，一般情况下这里的`devices`是`nil`。但是当容器重启等事件发生时，这里的devies就会是之前申请到的资源。这里会把需要的减掉已经拥有的，如果最后的结果不是0的话，就会报错。因为这里重启的时候，需求的资源不应该发生变化。

- (ASK)换句话说就是我们不用考虑这种情况？

一般情况下，这里会直接返回一个空的列表，告诉上层，不需要继续Allocate设备了



### 检验可复用资源能否满足需求

```go
// Declare the list of allocated devices.
// This will be populated and returned below.
allocated := sets.NewString()

// Create a closure to help with device allocation
// Returns 'true' once no more devices need to be allocated.
allocateRemainingFrom := func(devices sets.String) bool {
    for device := range devices.Difference(allocated) {
        m.allocatedDevices[resource].Insert(device)
        allocated.Insert(device)
        needed--
        if needed == 0 {
            return true
        }
    }
    return false
}

// Allocates from reusableDevices list first.
if allocateRemainingFrom(reusableDevices) {
    return allocated, nil
}
```



这里新建了一个函数，用于检验可复用资源能否满足需求，如果能够满足需求，那么就将可复用的设备添加到`allocated`中，并且：

```go
return allocated, nil
```



### 可复用资源不能满足全部需求时向DevicePlugin请求

```go
// Needs to allocate additional devices.
if m.allocatedDevices[resource] == nil {
    m.allocatedDevices[resource] = sets.NewString()
}

// Gets Devices in use.
devicesInUse := m.allocatedDevices[resource]
// Gets Available devices.
available := m.healthyDevices[resource].Difference(devicesInUse)
if available.Len() < needed {
    return nil, fmt.Errorf("requested number of devices unavailable for %s. Requested: %d, Available: %d", resource, needed, available.Len())
}
// Filters available Devices based on NUMA affinity.
aligned, unaligned, noAffinity := m.filterByAffinity(podUID, contName, resource, available)

```

不能满足全部需求时，获取所有在使用中的`DevicePlugin`以及所有可申请的的`DeviecePlugin`，使用下方函数，进行对齐：

```go
 m.filterByAffinity(podUID, contName, resource, available)
```



#### m.filterByAffinity

```go
func (m *ManagerImpl) filterByAffinity(podUID, contName, resource string, available sets.String) (sets.String, sets.String, sets.String) {
	// If alignment information is not available, just pass the available list back.
	hint := m.topologyAffinityStore.GetAffinity(podUID, contName)
	if !m.deviceHasTopologyAlignment(resource) || hint.NUMANodeAffinity == nil {
		return sets.NewString(), sets.NewString(), available
	}

	// Build a map of NUMA Nodes to the devices associated with them. A
	// device may be associated to multiple NUMA nodes at the same time. If an
	// available device does not have any NUMA Nodes associated with it, add it
	// to a list of NUMA Nodes for the fake NUMANode -1.
	perNodeDevices := make(map[int]sets.String)
	nodeWithoutTopology := -1
	for d := range available {
		if m.allDevices[resource][d].Topology == nil || len(m.allDevices[resource][d].Topology.Nodes) == 0 {
			if _, ok := perNodeDevices[nodeWithoutTopology]; !ok {
				perNodeDevices[nodeWithoutTopology] = sets.NewString()
			}
			perNodeDevices[nodeWithoutTopology].Insert(d)
			continue
		}

		for _, node := range m.allDevices[resource][d].Topology.Nodes {
			if _, ok := perNodeDevices[int(node.ID)]; !ok {
				perNodeDevices[int(node.ID)] = sets.NewString()
			}
			perNodeDevices[int(node.ID)].Insert(d)
		}
	}

	// Get a flat list of all of the nodes associated with available devices.
	var nodes []int
	for node := range perNodeDevices {
		nodes = append(nodes, node)
	}

	// Sort the list of nodes by how many devices they contain.
	sort.Slice(nodes, func(i, j int) bool {
		return perNodeDevices[i].Len() < perNodeDevices[j].Len()
	})

	// Generate three sorted lists of devices. Devices in the first list come
	// from valid NUMA Nodes contained in the affinity mask. Devices in the
	// second list come from valid NUMA Nodes not in the affinity mask. Devices
	// in the third list come from devices with no NUMA Node association (i.e.
	// those mapped to the fake NUMA Node -1). Because we loop through the
	// sorted list of NUMA nodes in order, within each list, devices are sorted
	// by their connection to NUMA Nodes with more devices on them.
	var fromAffinity []string
	var notFromAffinity []string
	var withoutTopology []string
	for d := range available {
		// Since the same device may be associated with multiple NUMA Nodes. We
		// need to be careful not to add each device to multiple lists. The
		// logic below ensures this by breaking after the first NUMA node that
		// has the device is encountered.
		for _, n := range nodes {
			if perNodeDevices[n].Has(d) {
				if n == nodeWithoutTopology {
					withoutTopology = append(withoutTopology, d)
				} else if hint.NUMANodeAffinity.IsSet(n) {
					fromAffinity = append(fromAffinity, d)
				} else {
					notFromAffinity = append(notFromAffinity, d)
				}
				break
			}
		}
	}

	// Return all three lists containing the full set of devices across them.
	return sets.NewString(fromAffinity...), sets.NewString(notFromAffinity...), sets.NewString(withoutTopology...)
}
```

这个函数的大体含义是:

- 如果没有对齐信息(没有设备与`NUMA`节点的依附信息，那么就直接将传进来的可用设备列表传回)

- 如果有对齐信息（那么就考虑他们的亲和性之类的东西，最后生成三个列表返回），这三个列表分别是：

  ```go
  fromAffinity
  notFromAffinity
  withoutTopology
  ```

  具体意思我没有探究，可以看上面的注释（我没看懂）



### 回到主线：拿到对齐后的节点后发生了什么？

首先明确，这里拿到了三个集合，`aligned, unaligned, noAffinity`

#### aligned集合足够多

首先，如果对齐后的集合`aligned`能够满足全部需求:

```go
if needed < aligned.Len() {
    // First allocate from the preferred devices list (if available).
    preferred, err := m.callGetPreferredAllocationIfAvailable(podUID, contName, resource, aligned.Union(allocated), allocated, required)
    if err != nil {
        return nil, err
    }
    if allocateRemainingFrom(preferred.Intersection(aligned)) {
        return allocated, nil
    }
    // Then fallback to allocate from the aligned set if no preferred list
    // is returned (or not enough devices are returned in that list).
    if allocateRemainingFrom(aligned) {
        return allocated, nil
    }

    return nil, fmt.Errorf("unexpectedly allocated less resources than required. Requested: %d, Got: %d", required, required-needed)
}
```

那么这里`callGetPreferredAllocationIfAvailable`从`align ∪ allocated`这个`set`中选择`required`个，其中`allocated`集合中的内容为必选，向`DevicePlugin`发送优选请求，获取`preferred`这个`set`，随后：

```go
allocateRemainingFrom(preferred.Intersection(aligned))
```

将优选`preferred ∩ aligned`加入，如果能满足需求，那么就返回。

如果我们的`DevicePlugin`没有返回足够多的设备，那么他会退而求其次，继续将`aligned `部分添加到本次请求中，进行返回，如果还是没有成功，那么就报错。



#### aligned集合不够多

会先分配`aligned`，然后

```go
preferred, err := m.callGetPreferredAllocationIfAvailable(podUID, contName, resource, available.Union(allocated), allocated, required)
if err != nil {
    return nil, err
}
if allocateRemainingFrom(preferred.Intersection(available)) {
    return allocated, nil
}

// Finally, if the plugin did not return a preferred allocation (or didn't
// return a large enough one), then fall back to allocating the remaining
// devices from the 'unaligned' and 'noAffinity' sets.
if allocateRemainingFrom(unaligned) {
    return allocated, nil
}
if allocateRemainingFrom(noAffinity) {
    return allocated, nil
}
```

从`available∪allocated`中取优选，尝试添加，如果添加后没有结束，那么就顺序添加其他集合。



## 回到allocateContainerResources

当前，我们使用：

```go
allocDevices, err := m.devicesToAllocate(podUID, contName, resource, needed, devicesToReuse[resource])
```

获取到了需要请求的`Devices`列表:`allocDevices`后发生了什么呢？

### 向DevicePlugin发送Allocate请求

```go
startRPCTime := time.Now()
m.mutex.Lock()
eI, ok := m.endpoints[resource]
m.mutex.Unlock()
if !ok {
    m.mutex.Lock()
    m.allocatedDevices = m.podDevices.devices()
    m.mutex.Unlock()
    return fmt.Errorf("unknown Device Plugin %s", resource)
}

devs := allocDevices.UnsortedList()
// TODO: refactor this part of code to just append a ContainerAllocationRequest
// in a passed in AllocateRequest pointer, and issues a single Allocate call per pod.
klog.V(3).Infof("Making allocation request for devices %v for device plugin %s", devs, resource)
resp, err := eI.e.allocate(devs)
metrics.DevicePluginAllocationDuration.WithLabelValues(resource).Observe(metrics.SinceInSeconds(startRPCTime))
if err != nil {
    // In case of allocation failure, we want to restore m.allocatedDevices
    // to the actual allocated state from m.podDevices.
    m.mutex.Lock()
    m.allocatedDevices = m.podDevices.devices()
    m.mutex.Unlock()
    return err
}

if len(resp.ContainerResponses) == 0 {
    return fmt.Errorf("no containers return in allocation response %v", resp)
}

allocDevicesWithNUMA := checkpoint.NewDevicesPerNUMA()
// Update internal cached podDevices state.
m.mutex.Lock()
```



### 将资源添加到podDevices中

```go
allocDevicesWithNUMA := checkpoint.NewDevicesPerNUMA()
// Update internal cached podDevices state.
m.mutex.Lock()
for dev := range allocDevices {
    if m.allDevices[resource][dev].Topology == nil || len(m.allDevices[resource][dev].Topology.Nodes) == 0 {
        allocDevicesWithNUMA[0] = append(allocDevicesWithNUMA[0], dev)
        continue
    }
    for idx := range m.allDevices[resource][dev].Topology.Nodes {
        node := m.allDevices[resource][dev].Topology.Nodes[idx]
        allocDevicesWithNUMA[node.ID] = append(allocDevicesWithNUMA[node.ID], dev)
    }
}
m.mutex.Unlock()
m.podDevices.insert(podUID, contName, resource, allocDevicesWithNUMA, resp.ContainerResponses[0])
```

会遍历所有被申请的设备，检查其中是否存在拓扑信息，如果存在则根据拓扑信息添加到不同的NUMA中，没有就都放到默认的`allocDevicesWithNUMA[0]`中。

最后，会调用`m.podDevices.insert(podUID, contName, resource, allocDevicesWithNUMA, resp.ContainerResponses[0])`将设备信息添加到`podDevices`中。



### 记录请求到的信息

```go
func (pdev *podDevices) insert(podUID, contName, resource string, devices checkpoint.DevicesPerNUMA, resp *pluginapi.ContainerAllocateResponse) {
	pdev.Lock()
	defer pdev.Unlock()
	if _, podExists := pdev.devs[podUID]; !podExists {
		pdev.devs[podUID] = make(containerDevices)
	}
	if _, contExists := pdev.devs[podUID][contName]; !contExists {
		pdev.devs[podUID][contName] = make(resourceAllocateInfo)
	}
	pdev.devs[podUID][contName][resource] = deviceAllocateInfo{
		deviceIds: devices,
		allocResp: resp,
	}
}
```

这里实质上就是将这次请求到的信息进行了记录



### 存在的问题

#### (ASK)devicePlugin怎么是有拓扑关系，怎么是没拓扑关系?

(ANSWER)这个问题是没看完的时候写的，现在已经解决了，和后面写的差不多：我看到了一个NV的更新：
![](C:\Users\jaegerwang\AppData\Roaming\Typora\typora-user-images\image-20210318202403125.png)

想要加入拓扑，需要在返回时加入特殊字段（但是我们不想要拓扑，所以就顺其自然就行了

#### (ASK)reusableDevice是怎么回事？

(ANSWER)在`allocateContainerResources`中`devicesToReuse`这个字典也是传入的，所以需要向上追溯，在`ManagerImpl.Allocate`中，如下：

```go
m.allocateContainerResources(pod, container, m.devicesToReuse[string(pod.UID)])
```

这个来自于这个`ManagerImpl`中的`devicesToReuse`字典。

这时，我们来重新审视`Allocate`函数，刚刚进入`Allocate`后有如下代码段:

```go
if _, ok := m.devicesToReuse[string(pod.UID)]; !ok {
    m.devicesToReuse[string(pod.UID)] = make(map[string]sets.String)
}
// If pod entries to m.devicesToReuse other than the current pod exist, delete them.
for podUID := range m.devicesToReuse {
    if podUID != string(pod.UID) {
        delete(m.devicesToReuse, podUID)
    }
}
```



- 如果没有`devicesToReuse`，那么就新建一个
- 遍历所有的`m.devicesToReuse`中的`k-v`，如果`k`不是当前创建的`pod`就删除（这是在干啥??）



除此之外，暂时没有看到相关的内容，应该不会产生什么影响。