---
title: 由先中后序遍历序列构造二叉树
---
  

不同二叉树的中序遍历

![image-20200805191801166](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013711.jpg)

![image-20200805191851595](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013825.jpg)

![image-20200805191913602](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013835.jpg)

![image-20200805191946368](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013854.jpg)

![image-20200805192027276](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013904.jpg)

## 前+中

![image-20200805192120760](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013912.jpg)

### 后+中

![image-20200805202834877](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013921.jpg)

### 层+中

![image-20200805202945647](https://cdn.jsdelivr.net/gh/KimYangOfCat/MyPicStorage/2021-CSPostgraduate-408/20200810013929.jpg)

### 总结回顾

![image-20200805203145525](https://tva1.sinaimg.cn/large/007S8ZIlly1ghg7n5qtacj31q00u0u0x.jpg)

若前序、后序、层序序列两两组合，是否能确定唯一的一颗二叉树？

答案是：不能，必须有中序序列划分左右子树🌲

