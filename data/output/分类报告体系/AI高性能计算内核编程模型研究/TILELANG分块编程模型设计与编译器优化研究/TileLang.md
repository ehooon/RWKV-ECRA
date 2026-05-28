# TILELANG分块编程模型设计与编译器优化研究 分析报告
## 1. 研究背景与模型定位
现代AI工作负载依赖优化计算内核，当前手动优化方式涉及线程绑定、内存布局调整、内联函数调用、流水线配置等多环节，人力投入占比高，优化成本显著。为降低高性能AI内核开发门槛，提出TILELANG通用分块编程模型，核心思路为解耦调度空间（含线程绑定、内存布局、张量化、流水线配置维度）与数据流定义，允许开发人员聚焦数据流逻辑编写，将硬件相关优化逻辑交付编译器自动化完成。
TILELANG设计遵循三项原则：采用Pythonic编程风格，最小化类型注解要求，实现与Python生态系统兼容；以数据流为中心抽象调度复杂性；支持组件可组合性，提供显式数据类型定义与内存分配接口。
## 2. 核心编程模型组件
### 2.1 基础核心概念
Tile是TILELANG的核心数据抽象，属于可被分配和操作的数据对象：
- 内存分配接口：`T.alloc_shared`用于分配共享内存空间，适用于矩阵乘法等场景下的块数据缓存；`T.alloc_fragment`用于分配寄存器文件内的累加器空间，降低计算延迟。
- 数据传输接口：`T.copy`用于管理全局内存与各级硬件私有/共享内存之间的数据移动。
- 并行操作接口：`T.Parallel`用于实现循环迭代的自动并行赋值与初始化。
### 2.2 可组合块操作符
所有块操作符均抽象底层数据流逻辑，无需开发人员手动实现底层细节，统一提供两个标准接口：Lower接口负责将操作符降低为包含线程绑定、向量化内存访问逻辑的中间表示（IR），InferLayout接口负责自动推断对应缓冲区的内存与循环布局：
1. `T.gemm`矩阵乘法操作符：支持ss、sr、rs、rr四种内存访问模式，在CUDA后端自动调用CUTLASS优化实现，在AMD后端自动生成适配HIP的优化代码。
2. `T.reduce`归约操作符：支持sum、min、max、product等聚合类型，适配CUDA与AMD GPU后端，依托warp/block级并行完成性能优化。
3. `T.atomic`原子操作符：提供add、min、max等原子操作实现，依托硬件原生原子指令保障并发更新的线程安全性。
### 2.3 调度原语与布局抽象
TILELANG提供四类可组合布局抽象：Layout基于IterVar和步长定义实现线性地址映射，支持非线性变换与缓冲区转换；Fragment Layout专门描述GPU寄存器文件的块级分配方案；Layout Function通过代数函数形式表示地址映射逻辑；内置padding、swizzle等基础布局变换原语。
配套调度原语清单：
- `T.Parallel`：将循环迭代直接映射到硬件线程，支持向量化优化。
- `T.Pipelined`：启用循环级流水线机制，重叠计算与内存操作，减少内存访问瓶颈，开发人员仅需配置num_stages参数即可自动完成依赖分析与流水线排布。
- `T.annotate_layout`：支持用户自定义内存布局，默认提供适配NVIDIA、AMD GPU的预定义布局，消除共享/全局内存访问冲突。
- `T.use_swizzle`：启用内存地址交错变换，提升L2缓存访问局部性。
## 3. Fragment Layout与自动线程绑定推断
Fragment Layout定义GPU寄存器文件在块级别的分配规则，内置repeat、repeat_on_thread、replicate等扩展原语：从基础base_layout（单线程承载16x16矩阵的布局，适配mma_ldmatrix指令），通过扩展生成warp_layout（单线程承载32x16矩阵），再进一步扩展生成128x16维度的块级block_layout。
TILELANG引入LayoutMap统一记录所有缓冲区的布局信息，采用优先级机制实现布局自动推断：GEMM操作约束优先级最高，元素级操作约束优先级最低，按优先级从高到低遍历所有未确定布局的缓冲区，完成布局与线程绑定策略的自动推导。
## 4. 编译器架构与全流程优化
TILELANG的编译全流程分为5个阶段：解析、AST转换、IR构建、优化、代码生成，通过`tilelang.compile`接口将用户编写的Python代码转换为中间表示后，最终生成LLVM IR、CUDA C/C++、HIP C/C++等可执行低级代码。内置自动化优化通道清单：Layout Inference布局推断、动态参数简化、自动流水线推导、循环尾部分割。
硬件特定优化能力：
1. NVIDIA GPU系列适配：
   - RTX 3090硬件指令吞吐量：IMAD为17.8 TOPS，DP4A为71.2 TOPS，32x32x32规格MMA为284 TOPS，文档中存在RTX 3090 DP4A吞吐量17.8 TOPS的记录。
   - 硬件指令调用支持三种模式：通过`T.import_source`和`T.call_extern`注入C++包装的硬件指令，通过`T.ptx`接口直接内联PTX硬件指令，调用封装后的Tile Libraries高级API如`tl::gemm_ss`自动选择最优指令。
   - Ampere架构支持自动插入`cp.async`异步内存拷贝指令，重叠全局内存到共享内存的数据传输与计算任务。
   - Hopper架构适配特性：支持TMA单元实现全局内存到共享内存的高速数据拷贝，调用wgmma PTX指令优化Tensor Core利用率，通过Warp Specialization机制将线程划分为生产者、消费者两个角色，依托Live Variable Analysis自动确定同步点并插入mbarriers屏障，完成异步MMA指令调度。
2. AMD CDNA架构适配：通过封装HIP版本的Copy原语，调用`s_waitcnt lgkmcnt`、`buffer_load_dword lds`等原生异步拷贝与DMA指令，优化数据传输效率。
## 5. 基准测试性能数据
所有测试数据均为硬件实测结果：
1. GEMM工作负载：
   - 在RTX 4090、A100、H100、MI300X四款GPU上，TILELANG性能相对cuBLAS等供应商官方库的加速比分别为1.10×、0.97×、1.00×、1.04×。
   - 同硬件下相对Triton的加速比分别为1.08×、1.03×、1.13×、1.25×。
2. 注意力类工作负载：
   - FlashAttention场景：性能相对FlashAttention-3为1.36×提升，相对Triton为1.41×提升，相对PyTorch为1.70×提升；序列长度为8k时性能接近FlashAttention-3。
   - Linear Attention场景：相对Triton平均加速1.77×、2.10×。
   - MLA工作负载：在H100上相对Torch性能提升1075.9×，实现代码行数约70行，性能达到未开源核心的手写库AITER的95%，接近FlashMLA性能；在MI300X上相对Torch性能提升129.2×。
3. 去量化矩阵乘法工作负载：
   - 采用BitBLAS-TileLang-W_INT2A_INT8配置时，相对cuBLAS-W_FP16A_INT8最大实现7.65倍加速。
   - W_INT4A_FP16格式场景下相对Marlin平均加速1.04倍；W_NF4A_FP16格式场景下相对BitsandBytes平均加速1.62倍。
## 6. 基准测试算子规格
### 6.1 通用矩阵乘法基准
算子分为V组（m维度固定为1，n、k取不同大尺寸参数）与M组（m、n、k均取大尺寸参数），部分维度值为28672或8192。
### 6.2 FlashAttention基准
共5组配置，batch值均为1，nheads值均为32，head_dim值均为128，seq_len依次为512、512、1024、1024、4096，causal属性依次为true、false、true、false、true。
### 6.3 线性注意力基准
共6组配置，batch值均为1，nheads值均为64，head_dim值均为64，d_state值均为128，seq_len包含1024、2048、8192等参数。
## 7. 后续规划与开源信息
已支持动态参数、动态形状特性，可用于AI核心库开发，后续工作方向包括构建自举Tile Library、扩展分布式计算支持、设计自动化成本模型、优化动态形状调整策略。项目开源地址为https://github.com/tile-ai/tilelang。