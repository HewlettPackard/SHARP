# Setup k8s

## Installation

Follow the official installation [manual](https://kubernetes.io/docs/setup) or other [guides](https://www.armosec.io/blog/setting-up-kubernetes-cluster/).

## Additional steps if K8s is deployed with kubeadm

Setup a Persistent Volume storage class in k8s:

```sh
    kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml
```

Attach this storage class to pods as default:

```sh
    kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

## Moving from k3s

If you've previously set up [k3s](./setup/k3s), make sure that this line you added to .bashrc is no longer there:

```sh
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

## Additional node setup


## Setting up nodes with Nvidia GPUs

First, make sure to follow the additional setup instructions for all nodes in the previous section.

Second, follow NVidia's [instructions](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) to install the container toolkit.
If you're getting error messages finding files, you've probably skipped the [step](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#setting-up-nvidia-container-toolkit) of setting up the distribution:

```sh
distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
      && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
      && curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```
