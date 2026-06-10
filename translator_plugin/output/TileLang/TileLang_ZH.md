# TileLang



第 1 页

# TiLELANG：用于AI系统的可组合拼图式编程模型

李旺§, 北京大学, 中国

杨成§，北京大学，中国

易宁·施, 北京大学, 中国

郑俊堂，北京大学，中国

张维文，英国帝国理工学院

魏昊先生，北京大学，中国

林晓玛，微软研究院，中国

杨秋霞，微软研究院，中国

刘乐雄，微软研究院，中国

范扬，微软研究院，中国

张扬，北京大学，中国

现代AI工作负载高度依赖于优化的计算核心，用于训练和推理。这些AI核心遵循明确的数据流模式，例如将DRAM和SRAM之间的网格块移动，并在这些网格块上执行一系列计算。然而，编写高性能核心仍然复杂，尽管这些模式清晰。实现最佳性能需要精心的硬件中心优化，以充分利用现代加速器。尽管领域特定的编译器试图减少编写高性能核心的负担，但它们往往在易用性和表达能力方面面临差距。

在本文中，我们提出了TILELANG，这是一种用于更高效AI核心编程的通用分块编程模型。TILELANG将调度空间（绑定、布局、张量化和管道）与数据流分离，并将其封装为一组自定义注释和原语。这种方法使用户能够专注于数据流本身，而将大部分其他优化留给编译器。我们在常用设备上进行了广泛的实验，在多个实验中，我们的评估表明，TILELANG可以在关键核心中实现最先进的性能，这表明其统一的块和线程范式以及透明调度能力能够提供现代AI系统开发所需的力量和灵活性。

第1章 引言

近年来，追求在AI工作负载中的更高性能[13, 16, 17, 23]加速了专用内核[4, 6, 11, 12]的发展，这些内核推动了训练和推理。矩阵乘法特别是，支撑着从简单的前馈层到庞大的Transformer模型的各种神经网络架构。为了应对这些网络的巨大计算负担，FlashAttention等专用内核被开发出来，以优化注意力机制，降低内存开销并提高处理吞吐量。然而，在先进的专用硬件上实现高效性能，需要硬件感知的设计和复杂的调优的精妙结合——这促使了对更具表达力的领域特定编译器的兴趣日益增长。

第 2 页

深度学习核心通常表示为数据流模式，涉及将存储器中的瓦片移动到SRAM中，并在这些瓦片上执行序列的计算。尽管这些模式看起来清晰，但开发高性能核心仍然具有挑战性，因为开发人员必须手动解决几个关键优化：

- 线程绑定。绑定指的是将图形操作和数据映射到适当的线程。在现代加速器架构中，例如GPU，这涉及到将任务分配到线程块、瓦片和单个线程的精心分配，以最大化并行性并减少负载不平衡。一个最佳的绑定策略增强了数据局部性，并减少了线程同步和发散的开销，从而提高了计算吞吐量。

- 内存布局优化。内存布局优化涉及对内存中数据的系统性组织，以消除硬件冲突并确保高效的访问模式。如最近的研究[14, 18]所示，这个过程通常需要将自然的数据表示转换为块化或分块格式，以适应架构的内存子系统。这种重组有助于实现连续访问和有效的缓存利用，从而降低内存延迟并提高整体系统性能。

- 内在张量化。利用内在函数涉及直接使用针对性能优化的目标特定指令。现代处理器和加速器提供了专门的操作，例如张量核 $ ^{[2]} $ 和矩阵核 $ ^{[1]} $，这些操作可以同时执行多项算术运算，并结合向量复制和异步复制等机制，以更好地利用带宽。使用这些内在指令需要精确管理数据类型、内存对齐和控制流，以充分利用硬件的计算能力，从而在关键内核操作中实现显著的性能提升。

- 流水线。流水线是一种将数据移动与计算并行处理的技术，以减少内存访问延迟。通过同时调度数据传输和计算任务，流水线确保处理单元保持活跃，并最小化由于内存延迟导致的空闲时间。在先进的Nvidia Hopper架构中，Tensor Memory Accelerator (TMA) $ [10] $ 可以促进这一过程，通过为不同的计算单元（如CUDA核心和Tensor核心）实现异步处理，进一步增强并发性。

尽管近期针对AI工作负载的领域特定编译器[7, 24, 25]极大地简化了创建高性能核心的过程，但它们仍然将大部分低级优化与实现代码紧密结合，即使数据流显式暴露。例如，Triton[20]提供了直观的块级原语，但隐藏了线程行为、内存布局和地址空间注释，这些原语是通过自动生成策略实现的。这种抽象简化了编程，但也使经验丰富的开发者难以发挥最大性能——例如，在实现具有量化权重的矩阵乘法时[15]。这类核心通常需要汇编级别的 inline assembly 来执行向量化数据类型转换[15]和与特定内存布局的缓冲区精心对齐的数据布局[21]。虽然Triton提供了向量化操作，如t1.dot，但将其扩展到特定用例——例如，通过注册手工制作的高性能tile操作符——仍然困难重重。此外，尽管Triton提供了一个用户友好的管道旋钮（num_stage），但它并不允许用户定义完全自定义的管道。因此，领域专家在开发需要显式控制内存层次结构和其他精细优化的内核时受到限制。

为了解决这些局限性，我们提出了TILELANG，这是一种保留了Triton简单性的编程模型，同时提供了更大的灵活性。TILELANG旨在为用户提供

第 3 页

通过对调度空间的细粒度控制来提高性能。我们认为，使这一目标成为可能的关键因素是数据流与调度的解耦：用户只需专注于使用可组合的tile操作符定义数据流，而编译器则负责探索和应用调度策略。当编译器的默认优化不足时，用户可以在前端施加更精细的控制。我们引入了一种可组合的tile编程抽象，其中核心计算模式（如GEMM、COPY、ATOMIC和REDUCE）通过tile操作符表示。这些操作符独立定义了kernel的数据流，而调度操作符和注解则提供了捕获额外优化的选项，从而使用户可以选择依赖编译器生成的调度，或者手动精细调整kernel的关键部分。

为了提高TILELANG的可用性，我们在Python中实现了前端语言，以实现灵活的编程风格和最少的类型注解。此外，我们引入了一个TILELANG编译器，它将用户定义的程序转换为高度优化的低级代码，以实现在现代硬件上的高效执行。编译器自动化了关键优化，减少了手动调整性能的工作量。总之，我们的贡献如下：

(1) 瓦片级编程语言。我们设计了一种瓦片级编程语言，允许用户在硬件内存层次结构中明确声明缓冲区的位置。通过利用布局推断机制，系统可以自动简化并行化缓冲区操作的复杂性，同时暴露出线程级控制接口，使专家能够精确地管理每个线程如何与缓冲区交互。

(2) 带自动优化的编译器。我们为TILELANG提供了一个配套的编译器，其中包含一系列自动编译通道。这些通道包括通过布局推断机制实现的自动并行化、动态参数简化、自动管道推导以及对动态形状的循环尾分割优化等。这个编译器确保了TILELANG程序既高效又易于编写。

(3) 最先进性能。在真实世界AI内核上的实证评估表明，TILELANG实现了与专用供应商库和其他基于DSL的方法（如Triton）相当的性能，并且在NVIDIA和AMD GPU上都实现了超越。

在本文的余下部分，我们介绍了TileLang的设计和实现。我们首先描述了语言语法和底层编程模型。然后我们详细说明了TileLang JIT编译器架构，涵盖了硬件无关和硬件感知优化。最后，我们将TileLang与现有工作进行比较，并总结我们的发现，并概述了这一统一方法在高性能AI内核开发中的未来方向。我们已经开源了TileLang $ ^{1} $。

## 2 TiLELANG 示例

现有的机器学习编译器，如TVM，将调度与计算分开，用户需要明确区分计算和调度。此外，用户必须手动注册新的张量指令，并指定缓冲区布局，以实现最佳性能。然而，编写和理解调度程序仍然具有挑战性。尽管现代框架如Triton允许用户关注Tile级别的编程，但其数据流表示往往不清晰，并且需要使用某些工作around—如掩码条件加载—或硬件特定功能，如Tensor Memory Accelerator (TMA)。尽管框架如ThunderKitten将程序抽象为Tile级别的组合加载、

第 4 页

<div style="text-align: center;"><img src="imgs/img_in_image_box_169_239_1881_984.jpg" alt="Image" width="84%" /></div>

<div style="text-align: center;">(a) 一个 TileLang 程序示例</div>

<div style="text-align: center;">(b) 中间张量 IR</div>

<div style="text-align: center;">(c) 生成的CUDA代码</div>

图1. TILELANG程序的一个示例以及对应的降低后的IR和生成的CUDA C代码。代码片段为简化演示目的而简化。

计算、存储和同步操作的数据流仍然不够透明，这限制了用户进一步优化的能力。此外，随着Python深度学习框架的广泛应用[3, 22]，手动将模型转换为C++以进行优化是不切实际的。因此，在设计TILELANG时，我们强调三个关键原则：(1) Pythonic设计，它与Python生态系统无缝集成，提供熟悉的编码体验，降低学习曲线；(2) 数据流导向，它使用户能够专注于数据流，而无需处理底层调度复杂性。它将调度方面（如绑定、内存布局、张量化和流水线）与数据流解耦，将它们封装为可自定义注释和原语的集合，以提高可编程性和可维护性；并（3）可组合性，确保内核、原语和调度策略可以无缝结合，构建复杂设计。

在接下来的部分，我们将在TILELANG中实现一个通用矩阵乘法（GEMM）核心，以展示其基本语法并说明它如何提高生产力。如图11(a)所示，实现从定义GEMM核心的输入和输出开始（第8行），指定它们的形状和数据类型。接下来，初始化核心上下文（第9–11行），确定网格大小和总线程数量。然后是核心体（第12–27行），包括内存分配和数据流管理。由于TILELANG是一种嵌入式Python编程语言，它支持Python的所有 imperative 语法（例如if-else、for和while），关键区别在于用户必须为函数参数和变量声明提供显式类型注解。这种要求源于Python的动态类型，它可能不适合设备代码生成（例如CUDA/HIP），其中静态数据类型对于确定精确的数据位宽至关重要。在TILELANG中，类型标注明确地定义了元素类型和张量形状，确保了代码生成的正确性和高效性。此外，TILELANG允许显式内存分配，为数据的存储和访问模式提供了更大的控制。在给定的实现中，TILELANG使用T. alloc_shared将A和B的子矩阵存储在共享内存中，而T. alloc_fragments则在块级别使用寄存器文件分配累加器。此外，流水线执行（T. Pipelined）的使用使得内存传输与计算的并行执行成为可能，从而有效地隐藏了内存延迟并提高了整体吞吐量。T. gemm操作利用了NVIDIA

第 5 页

使用CUTLASS或手动编写的HIP代码来执行矩阵计算的片级优化。通过自动化低级调度和同步，TILELANG使开发人员能够专注于算法设计而不是硬件特定的优化，从而提高生产力的同时保持计算效率。

最后，我们调用tilelang.compile（第31行）将tilelang程序编译成中间表示（IR），如图11(b)所示。这个IR进一步编译成可执行程序，生成最终优化的代码，如图11(c)所示。

3. 瓦片语言

在本节中，我们介绍了我们的基于瓷砖的编程模型的基础，详细说明了TIELANG如何系统地高效地管理AI核心开发，并阐述了TIELANG的设计哲学，即将数据流与其他调度空间分离。

图2展示了TILELANG的五阶段编译管道。首先，开发者使用TileLang编写高级程序，描述计算逻辑和数据访问模式。在解析器阶段，TileLang程序被解析为Python AST，并转换为TileLang AST。接下来，IR构建器将AST转换为TVM中间表示（IR），使我们能够利用TVM的语法树和相关基础设施。随后，优化阶段执行一系列图优化和调度转换，以提高执行效率。最后，代码生成阶段将优化后的IR转换为底层代码，如LLVM IR、CUDA C/C++或HIP C/C++，支持多种硬件平台。

<div style="text-align: center;"><img src="imgs/img_in_image_box_171_1384_1872_1561.jpg" alt="Image" width="84%" /></div>

<div style="text-align: center;">图2. TiLELANG编译管道的阶段。</div>

表1展示了TILELANG提供的数据流操作符和调度原语的一个代表性子集。Tile Language采用数据为中心的编程范式，其核心计算语义通过tile级别的操作符如T. copy、T. gemm和T. reduce来表达。为了补充这些操作符，TILELANG还提供了一套调度原语，允许开发人员对性能关键的方面（如并行性、流水线化和内存布局）进行细粒度调整。我们将在下一节中解释这两个组件的设计。

表 1 列出了 TiLELANG 支持的数据流操作符和调度原语的一个部分列表。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td colspan="2">Dataflow Centric Tile Operators</td><td style='text-align: center; word-wrap: break-word;'>Scheduling Primitives</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>T. copy</td><td style='text-align: center; word-wrap: break-word;'>A specialized memory copy operator that abstracts parallel data movement among registers, shared memory, and global memory.</td><td style='text-align: center; word-wrap: break-word;'>T. Parallel</td><td style='text-align: center; word-wrap: break-word;'>Automates parallelization of loop iterations, mapping them to hardware threads, can also enable vectorization for additional performance gains.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>T. gemm</td><td style='text-align: center; word-wrap: break-word;'>Automatically selects implementations (cute/cuda/hip) for high-performance matrix multiplication on different GPUs.</td><td style='text-align: center; word-wrap: break-word;'>T. Pipelined</td><td style='text-align: center; word-wrap: break-word;'>Enables loop-level pipelining to overlap data transfers with computation and supports hardware-specific instructions such as async copy and TMA.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>T. reduce</td><td style='text-align: center; word-wrap: break-word;'>A flexible reduction operator (e.g., sum, min, max) exploiting warp- and block-level parallelism.</td><td style='text-align: center; word-wrap: break-word;'>T. annotate_layout</td><td style='text-align: center; word-wrap: break-word;'>Allows the definition of custom memory layouts to minimize bank conflicts and optimize thread binding.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>T. atomic</td><td style='text-align: center; word-wrap: break-word;'>Provides atomic operations (e.g., add, min, max) to ensure thread-safe updates in shared or global memory.</td><td style='text-align: center; word-wrap: break-word;'>T. use_swizzle</td><td style='text-align: center; word-wrap: break-word;'>Improves L2 cache locality via swizzle thread blocks.</td></tr></table>
第 6 页

### 3.1 基于瓦片的编程模型

图11提供了一个在TILELANG中的矩阵乘法（GEMM）的简明示例，展示了开发人员如何使用诸如瓦片、内存放置、流水线和操作调用等高级概念来精细控制数据移动和计算。特别是，图11(a)展示了如何利用多级瓦片技术利用不同的内存层次结构（全局、共享和寄存器）来优化带宽利用和减少延迟。总的来说，图11(b)展示了TILELANG的Python-like语法如何使开发人员能够在易于理解的编程模型中对性能关键的优化进行推理。

<div style="text-align: center;"><img src="imgs/img_in_image_box_156_718_1909_1324.jpg" alt="Image" width="86%" /></div>

<div style="text-align: center;">(a) GPU上的高效GEMM使用多级分块</div>

<div style="text-align: center;">(b) 使用TileLang描述的Tiled GPU GEMM</div>

图3. 通过TiLELANG在GPU上优化GEMM的多级折叠。

瓦片声明。我们方法的核心是将瓦片作为首要对象纳入编程模型。瓦片代表一个有形的数据部分，可以由一个并行单元（如线程块、线程组等）所拥有和操作。在Matmul示例中，A和B缓冲区是以块形式读取的（由block_M、block_N、block_K决定），在循环内部由T.Kernel执行。TILELANG定义了执行上下文，包括线程块索引（bx和by）和线程数量。这些上下文可以帮助我们计算每个线程块的索引，并使TILELANG更容易自动推断和优化内存访问和计算。此外，这些上下文还允许用户手动控制每个独立线程块内的线程行为。

显式硬件内存分配。TILELANG的一个标志性特点是能够将这些缓冲区显式地放置在硬件内存层次结构中。而不是将其留给编译器的神秘优化通道，TILELANG通过面向用户的内联汇编语言暴露了映射到物理内存空间或特定硬件构造的内联汇编语言。特别是：

• T.alloc_shared：在快速的、内部存储空间中分配内存，这对应于NVIDIA GPU上的共享内存。共享内存非常适合用于缓存中间数据，因为它比全局内存快得多，并且允许在同一个线程块中的线程之间高效地共享数据。例如，在矩阵乘法中，可以将矩阵片段加载到共享内存中，以减少全局内存带宽的需求，并提高性能。

• T.alloc_fragment: 在片段内存中分配累加器，这对应于NVIDIA GPU上的寄存器文件。通过将输入和部分和保留在寄存器或硬件级缓存中，延迟进一步降低。请注意，在这个片段程序中，每个片段分配相同的本地缓冲区，这与共享内存相同，但共享内存通常更快但更丰富，而寄存器文件是有限的。这是因为

第 7 页

分配在这里指的是整个线程块的寄存器文件。TILELANG在编译过程中使用布局推断通道来推导一个布局对象T. Fragment，它确定如何为每个线程分配相应的寄存器文件。这一过程将在后续章节中详细讨论。

数据在全局内存和硬件特定内存之间的传输可以使用T. copy来管理。此外，硬件特定缓冲区可以使用T. clear或T. fill进行初始化。对于数据分配，也可以使用T. Parallel进行并行操作，如8节所示。

3.2 数据流中心的Tile操作符

TileLang抽象了一组Tile操作符，使开发人员能够专注于数据流逻辑，而无需管理低级实现细节。图4展示了Tile操作符的接口，以及几个代表性示例，包括GEMM、Copy和并行。每个Tile操作符必须实现两个关键接口：Lower和InferLayout。Lower接口定义了如何将高级Tile操作符降级为更低层级的IR，例如绑定线程或向量化内存访问。例如，Copy可以被降级为包含绑定线程和向量化读写的循环。InferLayout接口负责确定与Tile操作符相关的内存和循环布局。这包括推断缓冲区布局（例如，交织内存）或循环级布局（例如，绑定线程）。例如，T. gemm将其共享内存输入应用到分块布局上，并使用矩阵特定的布局来写回MMA片段。类似地，T. Parallel中的并行循环结构可以用绑定和向量化访问模式来表示，这些模式都是通过布局推断得出的。第4.1节提供了布局组合及其在降低过程中作用的更详细讨论。

<div style="text-align: center;"><img src="imgs/img_in_image_box_160_1579_1950_1841.jpg" alt="Image" width="88%" /></div>

图4. 拼图操作的界面，以及TileOP的示例实例。

表1列出了一组TILELANG操作符，以简化基于瓦片的编程中的常见操作。这些内置操作符抽象了硬件内存访问和计算的底层细节，使开发人员能够从数据流的角度关注高级算法设计，同时保持对性能关键方面的细粒度控制。每个操作符都设计为无缝集成到瓦片编程模型中，确保在硬件内存层次结构中高效的数据移动和计算。下面，我们将描述几个关键操作符及其在优化内存传输和算术计算中的作用。

- 拷贝：拷贝操作是 T 的糖语法，与内存拷贝类似，可以从和到范围片段拷贝寄存器，共享范围的静态共享内存，共享。dyn 的动态共享内存，以及全局内存。

- gemm: 内置的T.gemm操作符是一个高度优化的通用矩阵乘法实现，支持各种内存访问模式（ss，sr，rs，rr），其中r表示寄存器内存，s表示共享内存。该操作符会根据内核配置自动选择最优实现。对于CUDA后端，T.gemm利用Nvidia的CUTLASS库来高效利用Tensor Cores或CUDA Cores，而对于AMD GPUs，它使用可组合的内核和手写的HIP代码来实现。

第 8 页

性能优化。用户还可以通过在Python中注册自定义原语来扩展T.gemm，使其适用于特定用例。

- reduce: T. reduce提供了一种灵活且高效的聚合数据的机制，用于在不同维度上进行聚合。它支持各种聚合操作，如求和、最小值、最大值和乘积等。聚合可以在指定的轴上进行，例如在矩阵中进行行聚合或列聚合。T. reduce利用了warp级别和块级别的并行性，以在CUDA和AMD后端上实现最佳性能。用户还可以通过定义自己的聚合核来自定义聚合操作。

- 原子：T. atomic 提供了用于在并行上下文中安全更新共享或全局内存的原子操作。常见的原子操作，如加法、min 和 max，都是原生支持的。T. atomic 确保在并发更新时的线程安全，这对于例如累加器、共享内存中的最小值和最大值更新以及无需同步计数器等操作至关重要。它旨在利用 NVIDIA 和 AMD GPU 上的原生硬件原子指令，确保在并行执行中保持高性能和正确性。

### 3.3 时间表标注和原语

尽管数据流模式构成了计算组织的基础，但现代高性能计算需要更精细的执行模式控制。为了满足这一需求，TILE-LANG提供了一套全面的调度原语，使开发人员能够精确调整性能关键应用的细节，如表1所示：

- 流水线化：T. Pipelined 模式允许高效流水线化循环以提高性能，通过重叠计算和内存操作来实现。在图11中，对k（减少维度）进行循环的流水线化，使用num_stages=3，创建了一个3级流水线。这种流水线允许数据传输、计算和随后的数据准备重叠，从而有效减少内存瓶颈并提高计算吞吐量。将T. Pipelined模式降低到CUDA源代码的详细设计将在第4.4节中讨论。

• 并行：T.Parallel 使用并行化循环，将迭代映射到线程。在图8中，数据从A_shared中复制到A中的操作使用T.Parallel(8, 32)进行并行化，同时在8和32维度上进行并行化。它不仅通过利用硬件并行性提高性能，还自动将线程映射到迭代，并支持向量化以进一步优化。

- annotate_layout: T.annotate_layout 原语允许您使用用户定义的内存布局为共享或全局内存指定内存布局优化。默认情况下，TiLELANG 采用优化的内存布局，旨在最小化 Nvidia 和 AMD GPU 上的内存冲突。

- 使用swizzle：T.use_swizzle 原语通过启用 swizzled 内存访问，提高了 L2 缓存的局部性，从而提高了数据重用，这对于并行线程块处理栅格化数据特别有效。

4. 调度设计与自动化

在本节中，我们将讨论四种调度空间及其在TileLang中的自动化设计，除了数据流之外。其中一些相对独立（如流水线和张量化），而另一些则更加耦合，例如线程绑定和内存布局设计。在接下来的几节中，我们将首先解释内存布局基础设施的设计，然后是线程

第 9 页

绑定。然后，我们将讨论张量化的自动化设计，最后分享管道的设计。

### 4.1 内存布局组成

在TIELANG中，我们支持通过高级接口如A[i, k]对多维数组进行索引。这种高级索引最终通过一系列软件和硬件抽象层转换为物理内存地址。为了建模这个索引转换过程，我们引入了关键抽象层次Layout，它描述了数据在内存中的组织和映射方式。在物理地址级别，一个布局可以表示为线性化地址表达式的形式  $ \sum_{i} y_i s_i $，其中  $ y_i $ 表示第  $ i $ 维的索引，  $ s_i $ 是该维度对整体线性内存地址的贡献。给定一个布局  $ L = s : d = (s_0, s_1, \ldots, s_{n-1}) : (d_0, d_1, \ldots, d_{n-1}) $, TIELANG采用了一种灵感来自TVM [8]的设计，引入了一个可组合且可堆叠的布局函数抽象，基于IterVar。由于IterVar可以封装步长信息，布局表达式可以简化为关于IterVar的代数形式。因此，布局函数可以形式化地表示为一个映射  $ f : \mathbb{K}^n \rightarrow \mathbb{K}^m $，其中  $ f $ 编码了从高级索引到内存地址的转换。

<div style="text-align: center;"><img src="imgs/img_in_image_box_192_1169_1341_1522.jpg" alt="Image" width="56%" /></div>

<div style="text-align: center;">(b) 缓冲区展平布局函数</div>

<div style="text-align: center;"><img src="imgs/img_in_image_box_1378_1166_1919_1521.jpg" alt="Image" width="26%" /></div>

<div style="text-align: center;">(c) 缓冲区填充布局函数</div>

<div style="text-align: center;">图5. 界面和布局功能的示例实例。</div>

图5(a)描述了TILELANG中布局的定义。其核心组件包括iter_vars，它们可以带有范围信息，以及一组forward_index表达式，用于计算基于这些迭代变量的内存位置。这些表达式共同定义了一个代数函数$ f : \mathbb{K}^n \rightarrow \mathbb{K}^m $。如图5(b)所示，这允许表示2D到1D布局的转换。给定缓冲区的形状，iter_vars被绑定到特定区域，并将这些表达式传递给算术分析器，以确定符号或常数边界。这些边界用于推断缓冲区的形状，并相应地调整缓冲区访问索引。

TILELANG 还支持非目标布局转换。例如，图 5(c) 展示了如何使用布局来为缓存访问应用填充。这些布局转换是可组合的，TILELANG 包含了几种内置的布局策略，例如布局旋转，这通常用于在 GPU 上缓解共享内存冲突。

此外，TILELANG 引入了一个布局抽象的扩展，称为 Fragment。与标准布局相比，Fragment Layout 总是产生输出形式为 $ f : \mathbb{K}^{n} \rightarrow \mathbb{K}^{2} $，其中两个输出维度分别表示线程在寄存器文件中的位置和局部寄存器文件中的索引。例如，在图 11 中，块级别分配了一个寄存器文件 $ C_{local} $。然而，由于 GPU 寄存器文件必须在线程之间进行分区，Fragment Layout 提供了对这种分区方案的准确描述。

图6(a)展示了Fragment布局的定义，TILELANG提供了四种原始操作来帮助用户扩展现有的Fragment布局。图6(b)展示了一个例子，说明如何使用这些操作。

第 10 页

这些原语用于从 mma_ldmatrix 指令中的基本布局推导出完整的块级布局，其中 base_layout 表示单个 warp 消耗 m16k16 矩阵的布局。通过重复原语将其扩展为 warp_layout，这允许单个 warp 消耗 m32k16 矩阵。图 6(c) 可视化了这种转换。然后，使用像 repeat_on_thread 和 replicate 这样的原语将 warp_layout 扩展为 block_layout，这表示四个 warp 共同消耗一个 m128k16 矩阵。

<div style="text-align: center;"><img src="imgs/img_in_image_box_174_647_1910_1485.jpg" alt="Image" width="85%" /></div>

(b) 例子：从基础 LDMATRIX 16x16 到块布局 128x16

(c) 从基础LDMATRIX 16x16到布局32x16的可视化

图6. 分片布局的界面和示例实例。

### 4.2 线程绑定

在Fragment布局的抽象基础上，一个关键挑战是如何将这些布局映射到线程以便在执行过程中运行。这导致了Thread Binding问题，即如何将块级寄存器文件分配给单个线程，以及如何推断出合适的Fragment布局。此外，它还需要识别如何正确并行化循环以满足布局约束。

尽管第4.1节介绍了Fragment Layouts以帮助简化这个过程，但为所有缓冲区确定适当的Fragment Layout仍然对于任意计算表达式来说具有挑战性。我们提出两个关键观察来指导这个过程。首先，由于多个Tile操作通常共享相同的缓冲区，因此它们的布局和线程绑定策略是相互依赖的。其次，布局和线程绑定要求的严格程度在不同操作之间是不同的。例如，在GPU上，GEMM操作（它利用Tensor Cores）对布局和线程绑定施加了严格的约束，而元素级操作通常允许更多的灵活性。

基于这些观察结果，我们提出了一种基于布局和Fragment对象的推理方案，以优化布局和线程绑定。为了系统地管理布局，我们维护一个布局映射表，记录所有缓冲区的布局信息。我们为tile操作符布局定义了一个等级优先级系统，其中更高的优先级等级表示更严格的布局要求和更大的性能影响。TILELANG采用自上而下的推理方式，按照优先级等级顺序推理布局，从最高优先级等级开始。在每个优先级等级上，TILELANG尝试为所有未确定的缓冲区推理布局，直到无法再取得进展，然后才转移到下一个较低优先级等级。

第 11 页

如图7所示，考虑一个场景，其中矩阵C代表GEMM操作的结果，对应于Fragment对象，需要在GEMM计算后添加偏置D。由于GEMM在推理过程中具有最高优先级，其线程绑定配置已经预先确定，而D的线程绑定策略仍需确定。矩阵C的输出矩阵大小为4×4，共8个线程，每个线程负责2个元素。因此，偏置缓冲区D的布局必须与此配置相匹配。由于每行的矩阵C由2个线程处理，这两个线程都需要访问D中的相同元素进行加法操作。因此，D必须复制以确保每个线程都能访问相应的元素。D的布局可以使用相同的方法推断出来。

<div style="text-align: center;"><img src="imgs/img_in_image_box_334_840_1722_1165.jpg" alt="Image" width="68%" /></div>

<div style="text-align: center;">图7. 碎片的线程绑定推理示例。</div>

图8展示了线程绑定推理过程的示例。特别是，图8(a)展示了一个简单的代码片段，用于数据复制，该代码片段描述了从全局内存到共享内存的数据流。适当的线程绑定和向量化访问可以充分利用GPU的并行性，并利用高性能内存访问指令。在图8(b)中，T. copy操作被展开为多个循环轴。经过布局推理pass的应用，如图8(c)所示，程序自动向量化和并行化。最后，在图8(d)中，应用了布局交换。

<div style="text-align: center;"><img src="imgs/img_in_image_box_138_1703_1884_2684.jpg" alt="Image" width="86%" /></div>

图8. 多阶段自动线程绑定推理以实现高效并行内存访问。

第 12 页

### 4.3 利用高性能硬件指令

现代硬件架构通常支持多种指令路径来实现相同的计算操作。在NVIDIA GPU上，例如，8位乘法累加操作可以通过多种指令类型来实现。IMAD指令执行标量融合乘加操作，计算 $ d = a \cdot b + c $，其中所有操作数都被内部提升为32位整数进行计算。DP4A指令实现向量化点积操作，计算 $ d = \langle a, b \rangle + c = \sum_{i=0}^{3} a_i b_i + c $，其中a和b是8位整数向量，长度为4，而偏移量c和输出d都以32位整数精度表示。对于高吞吐量矩阵计算，MMA指令利用张量核心执行计算：$ \mathbf{D} = \mathbf{A} \cdot \mathbf{B} + \mathbf{C} $，其中 $\mathbf{A} \in \mathbb{R}^{16 \times 32} $，$\mathbf{B} \in \mathbb{R}^{32 \times 8} $，$\mathbf{C} $，$\mathbf{D} \in \mathbb{R}^{16 \times 8} $；在此情况下，A和B是8位整数矩阵，而C和D的结果使用32位整数精度。在NVIDIA RTX 3090 GPU上，这些指令的吞吐量分别约为17.8 TOPS，71.2 TOPS和284 TOPS。此外，MMA指令支持多种形状，在相同的精度设置下。

在TILELANG中，如图10(a)和(b)所示，有两种调用硬件张量指令的方法。第一种方法（图10(a)）使用C++源代码注入，其中通过C++模板手动包装指令（如dp4a），并通过T.import_source和T.call_extern将其注入到内核中。这允许低级别的控制，同时利用熟悉的C风格语法。在内核中定义的函数将在代码的开头生成，并在内核中调用。另一方面，如图10(b)所示，TILELANG提供了一个内置的T.ptx原语，允许直接嵌入PTX指令（例如，mma.m16n8k32.row.col.s32.s8.s8.s32）。这提供了另一种低级别的机制，用于利用专用指令，尤其是用于warp级别的操作。

<div style="text-align: center;"><img src="imgs/img_in_chart_box_159_1503_990_1795.jpg" alt="Image" width="41%" /></div>

<div style="text-align: center;">(a) 使用C源注入实现指令</div>

<div style="text-align: center;"><img src="imgs/img_in_chart_box_1012_1488_1446_1797.jpg" alt="Image" width="21%" /></div>

<div style="text-align: center;">(b) 通过T.ptx进行杠杆指令</div>

<div style="text-align: center;"><img src="imgs/img_in_chart_box_1459_1485_1854_1788.jpg" alt="Image" width="19%" /></div>

<div style="text-align: center;">(c) 通过瓷砖库利用杠杆教学</div>

图9. 使用高性能硬件指令的不同方法在tilelang中

然而，根据输入形状和数据类型选择最合适的指令可能具有挑战性。为了简化这一过程，TiLELANG还支持与Tile库的集成，如图10(c)所示。Tile库——如NVIDIA的cute或AMD的可组合核心（ck）——提供了高级别、标准化的基于tile的API（例如，tl : :gemm_ss），用于GEMM等操作。这些库隐藏了硬件特定的细节，允许底层实现自动选择对给定输入配置最有效的指令。在TiLELANG中，开发人员可以使用T.call_extern以简单且一致的方式调用这些库。

总之，TILELANG提供了两种互补的方法来利用高性能指令。第一种利用Tile库，简化了集成并受益于优化的性能。然而，高级抽象可能会限制低级控制。例如，cute::gemm_ss接口在共享内存输入上执行GEMM操作，但内部数据流从共享内存到寄存器的管理由cute模板处理。这使得无法外部标注或覆盖内部布局，从而降低了灵活性。此外，由于模板的大量使用，编译可能会显著变慢。分析

第 13 页

使用NVCC 12.8跟踪工具显示，模板展开大约占CUDA由tilelang生成的代码编译时间的90%。

<div style="text-align: center;"><img src="imgs/img_in_image_box_594_398_1463_860.jpg" alt="Image" width="42%" /></div>

图10. 使用DP4A和mma的不同方法在tilelang中

相比之下，TILELANG允许通过TILELANG本身直接实现T. gemm指令。这避免了布局注释的限制，并减少了编译时间。然而，它要求用户在TILELANG中实现完整的指令集，以支持每个目标硬件指令。目前，TILELANG支持这两种方法，默认采用Tile Library方法，以便快速支持新的硬件指令。

### 4.4 软件定义管道

TILELANG采用自动软件管道推理机制来分析计算块之间的依赖关系（例如，在本例中的Copy和GEMM），并生成一个结构化的管道调度计划，以最大化并行性，同时保持正确的执行顺序。特别是，该机制将Copy任务与其他计算密集型操作交织在一起，以减少空闲时间，并在检测到异步处理机会时，自动将这些任务映射到可用的硬件资源上进行并行执行。因此，TILELANG只能暴露一个单一的num_stages接口给用户，这大大简化了过程。然而，我们也允许用户在必要时提供关于顺序和阶段的信息。

<div style="text-align: center;"><img src="imgs/img_in_image_box_163_1863_1889_2159.jpg" alt="Image" width="85%" /></div>

图11. TiLELANG软件管道调度。该示意图展示了TiLELANG如何交错Copy和GEMM。

对于 Ampere 架构，TileLang 提供了对异步内存复制操作的支持，使用 cp.async 指令。cp.async 指令有助于全局内存和共享内存之间的快速数据移动，从而实现内存传输与计算的重叠，以提高性能。TileLang 通过分析循环结构，自动插入适用于可以的内存传输的 cp.async 指令。此外，TileLang 还确保正确使用 cp.async.commit 和 cp.async.wait 指令来处理同步，以保证数据的正确性。这种优化对于缓解寄存器文件的压力非常有效，并且能够更有效地利用硬件带宽。

第 14 页

在霍珀架构中，引入了两个新特性。首先，引入了一个新的TMA单元，作为专门的硬件单元，负责全局内存和共享内存之间的数据拷贝。其次，PTX指令集引入了一个新的wgmma指令，使得由四个wargp（由四个warp组成）执行矩阵乘法（MMA）操作成为可能，以提高TensorCore的利用率。此外，wgmma\_mma\_async指令是异步的。此外，霍珀架构的内核优化通常涉及warp专业化，其中线程被分为生产者和消费者。生产者线程使用TMA进行数据移动，而消费者线程负责计算。

在TileLang中，我们在下降过程中自动执行warp专业化优化。具体来说，TileLang分析所有语句的缓存使用情况，并确定它们的角色（生产者或消费者）。根据threadIdx，生产者和消费者被分配到不同的执行路径。为了确保计算正确性，TileLang利用Live变量分析来确定适当的同步点，并插入内存屏障（mbarriers）。

异步复制指令和DMA支持也在AMD CDNA架构中提供，TILELANG通过HIP包装的Copy原语来利用这些特性，以支持。具体来说，TILELANG利用如s_waitcnt lgkmcnt和buffer_load_dword lds等指令来高效地管理内存传输。这种集成使得系统能够充分利用硬件的能力，将数据移动与计算过程重叠，进一步提高管道性能并减少空闲时间。

5 数值实验

在本节中，我们通过一系列广泛的数值实验，在不同的硬件平台和工作负载上评估了TILELANG的性能。我们的目标是展示TILELANG在优化关键算子内核方面的有效性、通用性和可扩展性，这些内核是现代机器学习工作负载的基础。通过与最先进的解决方案进行比较，我们旨在突出TILELANG在处理混合精度计算方面的灵活性，以及它在多个GPU架构上实现显著性能提升的能力。

### 5.1 实验设置

硬件平台。我们在NVIDIA和AMD GPU上评估TiLELANG，因为它们是最广泛使用的加速器之一。我们的实验使用了三款尖端GPU：NVIDIA H100（80 GB）[10]，NVIDIA A100（80 GB）[9]和AMD Instinct MI300X（192 GB）[5]。对于NVIDIA H100，我们使用CUDA 12.4；对于MI300X，我们使用ROCm 6.1.0。所有平台均在Ubuntu 20.04上运行。

操作员工作量。我们在大规模深度学习流水线中常见的一系列操作员工作量上评估TILELANG。在NVIDIA H100上，我们重点关注多头注意力（MHA）、线性注意力和通用矩阵乘法（GEMM）。对于NVIDIA A100，我们测量我们去量化的GEMM内核的性能。同时，在AMD Instinct MI300X上，我们测量GEMM和MHA，以捕捉代表不同GPU架构的典型使用情况。这些工作量构成了许多现代神经网络模型的基本构建块，包括大型语言模型。

基准线。为了评估TiLELANG的性能，我们将其与几种最先进的基准线进行比较，这些基准线广泛应用于机器学习和GPU编程。这些基准线包括FlashAttention-3，专为多头注意力优化，使用CUDA指令如tma和wgmma.mma_async；Triton，一个开源框架，用于高效的GPU内核，支持

第 15 页

Nvidia和AMD的GPU，但需要手动优化；cuBLAS，NVIDIA的高性能稠密线性代数库；AMD的BLAS库，rocBLAS；PyTorch，具有手动优化的内核，如GEMM和FlashAttention-2，但未完全优化；BitsandBytes，支持格式如 $ W_{NF4}A_{FP16} $ 并提供高效内核；以及Marlin，针对 $ W_{INT4}A_{FP16} $ 计算的高度优化内核。这些选择提供了对不同优化策略和硬件兼容性的全面比较，用于TiLELang。

### 5.2 实验

闪存注意力性能。与FlashAttention-3、Triton和PyTorch相比，TileLang实现了  $ 1.36\times $、  $ 1.41\times $ 和  $ 1.70\times $ 的加速。由于FlashAttention-3是一种手工设计的方法，它无法高效地适应工作负载大小的变化。特别是，其固定的瓦片大小导致在较短的序列长度下表现不佳。对于较长的序列长度（例如8k），TileLang的性能与FlashAttention-3保持一致。PyTorch使用一个手工优化的FlashAttention-2核心，这导致其性能低于FlashAttention-3。

<div style="text-align: center;"><img src="imgs/img_in_chart_box_426_1060_1627_1957.jpg" alt="Image" width="59%" /></div>

图12. FlashAttention、LinearAtten在Hopper架构上的性能。

与这些基于手动模板实现相比，TileLang可以自动利用诸如cp.async.bulk和wgmma.mma_async等指令，并且还可以自动应用诸如warp specialization等优化。值得注意的是，在H100 GPU上，TileLang能够表达诸如FlashAttention-3中使用的管道调度方案等复杂的调度方案。

线性注意力性能。在我们的线性注意力实验中，我们使用了Mamba-2中的块扫描和块状态函数。与Triton相比，TileLang平均实现了  $ 1.77 \times $ 和  $ 2.10 \times $ 的加速。

多头隐藏注意力性能。图14展示了MLA及其对应的代码行数（LOC）在H100和MI300X GPU上的性能。在H100上，TILELANG相比Torch实现了1075.9倍的加速，显著优于Triton和FlashInfer，并接近手动优化的FlashMLA实现的性能。此外，TILELANG仅需约70行Python代码，证明了其相比其他基线具有更好的可用性。在MI300X上，TILELANG实现了129.2倍的加速。

第 16 页

<div style="text-align: center;"><img src="imgs/img_in_chart_box_82_237_1908_674.jpg" alt="Image" width="90%" /></div>

图13. GEMM在Nvidia和AMD GPU上的性能。

<div style="text-align: center;"><img src="imgs/img_in_chart_box_144_783_969_1391.jpg" alt="Image" width="40%" /></div>

<div style="text-align: center;">(a) MLA 在 H100 上的性能和代码行数。</div>

<div style="text-align: center;"><img src="imgs/img_in_chart_box_1077_798_1878_1384.jpg" alt="Image" width="39%" /></div>

<div style="text-align: center;">(b) MLA 在 M1300X 上的性能和代码行数。</div>

图14. H100和M1300X上MLA性能和代码行数的比较。

速度优于Torch，并且在性能和代码紧凑性方面超过了Triton。与手写的AITER库相比，TiLELANG实现了95%的性能。由于AITER的内核实现不是开源的，因此其LOC未包含在图中。

矩阵乘法性能。图13展示了NVIDIA和AMD GPU上GEMM工作负载的性能，将TiLELANG与Triton和优化的库进行比较。在RTX 4090、A100、H100和MI300X上，TiLELANG分别实现了与优化库相比的速度提升为$ 1.10\times $、$ 0.97\times $、$ 1.00\times $和$ 1.04\times $。与Triton相比，TiLELANG在相同的GPU上实现了速度提升为$ 1.08\times $、$ 1.03\times $、$ 1.13\times $和$ 1.25\times $。对于矩阵乘法，TiLELANG使用简单的语法与优化的库性能相匹配。此外，通过使用布局转换，TiLELANG确保在所有测试的设备上实现无冲突的执行。

去混合矩阵乘法性能。BitBLAS是一个高性能混合精度计算库，具有先进的自定义类型系统和调度，用于数值类型和属性的张量。最初基于TensorIR构建，我们已将其底层后端替换为TILELANG，使其能够与其他混合精度加速库进行直接比较。与cuBLAS- $ W_{FP16}A_{FP16} $相比，TILELANG最高可达7.65×的速度提升，这得益于BitBLAS-TileLang- $ W_{INT2}A_{INT8} $配置。此外，对于 $ W_{INT4}A_{FP16} $ 格式，我们的方法平均比Marlin快1.04倍，对于 $ W_{NF4}A_{FP16} $ 格式，我们比BitsandBytes快1.62倍。通过暴露基于线程的编程接口，并允许对数据布局和管道配置进行控制，TILELANG为开发者提供了更细粒度的优化能力。例如，开发者可以利用基于PTX的快速数值精度转换指令，并利用 Ladder 实现更平滑的内存

第 17 页

标题：TileLang：一种可组合的用于AI系统的瓦片编程模型

<div style="text-align: center;"><img src="imgs/img_in_chart_box_152_196_1931_821.jpg" alt="Image" width="87%" /></div>

<div style="text-align: center;">图15. A100 GPU上的去量化Matmul性能。</div>

在瓦片内的访问。这些优化在Triton中实现起来很困难，这使得TiLELANG独一无二地能够提供Triton难以实现的卓越性能。

## 6 结论与讨论

为了解决为现代硬件加速器编写高性能内核的挑战，本文介绍了TILELANG，这是一种Python风格的领域特定语言（DSL），它允许用户在前端以及利用布局推断机制高效并行化缓冲区操作。这意味着用户只需要描述缓冲区的计算逻辑，而无需担心如何实现并行化。同时，TILELANG为专家提供了在前端明确指定不同层次硬件内存层次结构中缓冲区行为的灵活性，并利用布局推断机制高效并行化缓冲区操作。这种方法在提供易用性和细粒度控制之间取得了平衡，既具有灵活性又具有性能。

与 ThunderKittens [4] 相比，TILELANG 简化了编程过程，允许开发者在不显式管理管道的情况下，通过 Python 编写整个程序，并默认优化细节，例如管道化。例如，在 Flash Attention 实现中，TILELANG 会自动在 Ampere GPU 上使用异步复制来传输数据，并在 Hopper GPU 上将管道降级到 TMA。然而，TILELANG 仍然为用户提供了在前端显式实现管道的选项。此外，TILELANG 还提供了对动态参数、动态形状等高级功能的强大支持，这使得它特别适合编写库。

我们还希望讨论几个有前景的方向，用于扩展和增强TILELANG，以便在未来的工作中：首先，我们计划基于TILELANG构建一个自托管的Tile库，消除对CUTLASS的当前依赖以及对CUDA/HIP代码的手动包装。其次，我们计划扩展TILELANG，以支持一系列分布式场景，通过引入tile级别的通信原语和调度策略，使用户能够实现针对特定通信和计算资源配置的高性能核心。此外，我们计划调查TILELANG的成本模型的设计。鉴于TILELANG采用基于Tile的编程范式，显式地暴露了线程映射细节，内存访问模式和计算行为都是明确定义的，这为硬件行为分析和开发更有效的成本模型提供了便利。最后，我们计划探索对动态形状调优的优化，具体关注于为具有动态变化维度的程序选择最合适的Tile配置。TILELANG设计中显式暴露的内存层次结构将进一步支持适用于多种硬件平台的后端。

## 第 18 页

如CPU、NPU等。我们将探讨一种通用的设计方法，以扩展多
...
[中间内容继续]
...
[结尾]
---
**注意：** 由于您提供的文本内容在“multi-”之后被截断，因此我无法提供完整的翻译。如果您能提供完整的文本，我将能够给出更准确的翻译。

后端支持，使TILELANG能够无缝适应多种硬件架构。

我们的系统是开源的，以支持未来的发展和社区贡献：https://github.com/tile-ai/tilelang。

## 参考文献

[1] AMD CDNA架构。https://www.amd.com/en/technologies/cdna。

[2] NVIDIA Tensor Cores. https://www.nvidia.com/en-us/data-center/tensor-cores/.

[3] PyTorch. https://pytorch.org/.

[4] ThunderKittens. https://github.com/HazyResearch/ThunderKittens.

[5] 微芯科技。AMD cDNA™ 3 架构。技术报告，微芯科技，2023

[6] 英伟达（NVIDIA）。NVIDIA 可组合内核。https://github.com/ROCm/composable_kernel。

[7] Tianqi Chen, Thierry Moreau, Ziheng Jiang, Lianmin Zheng, Eddie Yan, Haichen Shen, Meghan Cowan, Leyuan Wang, Yuwei Hu, Luis Ceze, 等。TVM：一个自动端到端优化的深度学习编译器。在第13届USENIX操作系统设计与实现会议（OSDI 18）上，页码578-594，2018年。

[8] Tianqi Chen, Thierry Moreau, Ziheng Jiang, Lianmin Zheng, Eddie Yan, Haichen Shen, Meghan Cowan, Leyuan Wang, Yuwei Hu, Luis Ceze, Carlos Guestrin, and Arvind Krishnamurthy. TVM: 一个自动端到端优化的深度学习编译器。在13th USENIX Symposium on Operating Systems Design and Implementation (OSDI 18)上，加利福尼亚州卡尔斯巴德，2018年，USENIX协会。

[9] NVIDIA Corporation. Nvidia a100 Tensor Core GPU架构. 技术报告, NVIDIA Corporation, 2020.

[10] NVIDIA Corporation. Nvidia H100 Tensor Core GPU架构。技术报告，NVIDIA Corporation，2023。

[11] NVIDIA Corporation. Cutlass: Cuda 模板用于线性代数子程序。https://github.com/NVIDIA/cutlass，2024。

[12] 崔道、丹福、斯坦福·埃尔蒙、阿特里·鲁德拉和克里斯·雷. 闪电注意力：精确且内存高效的IO感知注意力. 进步神经信息处理系统, 35:16344–16359, 2022.

[13] Google. Google assistant with bard: Generative ai. https://blog.google/products/assistant/google-assistant-bard-generative-ai/, 2024.

[14] 巴斯蒂安·哈格登、宾·范、韩峰、克里斯·塞卡、迈克尔·加伦和维诺德·格罗弗。石墨烯：用于GPU上优化张量计算的理想架构。在第28届ACM计算机体系结构支持编程语言和操作系统会议上，第3卷，302–313页，2023年。

[15] 金英基、拉夫·亨利、拉菲·法希姆和汉尼斯·哈桑·阿瓦达拉。谁说大象不能跑：将大规模模型带入云端大规模生产。arXiv预印本 arXiv:2211.10017，2022。

[16] 微软。新的bing。https://www.microsoft.com/en-us/edge/features/the-new-bing?form=MT00D8, 2024.

[17] OpenAI. 介绍ChatGPT，2022. 可在网址：https://openai.com/blog/chatgpt. 查阅。

[18] Phitchaya Mangpo Phothilimthana, Archibald Samuel Elliott, An Wang, Abhinav Jangda, Bastian Hagedorn, Henrik Barthels, Samuel J Kaufman, Vinod Grover, Emina Torlak, 和 Rastislav Bodik. Swizzle 发明者：GPU 内核数据移动性的数据流合成。在第 24 届国际计算机体系结构与编程语言与操作系统会议上，2019 年。

[19] Jay Shah, Ganesh Bikshandi, Ying Zhang, Vijay Thakkar, Pradeep Ramani, and Tri Dao. Flashattention-3: 快速且准确的注意力，采用异步性和低精度。arXiv preprint arXiv:2407.08608, 2024。

[20] Philippe Tillet, H. T. Kung, and David Cox. Triton: An Intermediate Language and Compiler for Tiled Neural Network Computations, page 10–19. Association for Computing Machinery, New York, NY, USA, 2019.

[21] 王磊、林晓梅、施志梅、张全长、朱良轩、殷宁、郑新星、赵明微、方洋、曹廷、等。《梯形：通过硬件感知的张量转换实现高效低精度深度学习计算》。2024年美国操作系统设计与实现会议（OSDI 24），第307-323页。

[22] Thomas Wolf, Lysandre Debut, Victor Sanh, Julien Chaumond, Clement Delangue, Anthony Moi, Pierric Cistac, Tim Rault, Rémi Louf, Morgan Funtowicz, 等. Huggingface的Transformers：自然语言处理的最先进技术。arXiv预印本，2019。

[23] 杨玲, 张泽龙, 宋思红, 洪盛, 徐瑞雪, 赵伟, 张文韬, 崔斌, 杨明. 扩散模型：一个综合性的方法与应用综述. 计算机学报, 56(4):1–39, 2023.

[24] 李南明、郑佳、孙敏、吴兆、阿斯尔·海亚姆、阿米尔·哈吉-阿里、王一、朱洋、段扬、库什克·森、约瑟夫·E·戈登和伊顿·斯托卡. Ansor: 为深度学习生成高性能张量程序. 第14届USENIX操作系统设计与实现会议（OSDI 20），2020年11月，页码863-879. USENIX协会。

第 19 页

[25] 朱浩宇，吴若凡，杨迪，谢滨开，李海洋，张辰，朱晓龙，许睿，王小妹，魏启聪，杨帆，杨洋，周亮，Cidon Asaf，Zhou Gennady. ROLLER：快速且高效的张量编译，用于深度学习。在第16届USENIX操作系统设计与实现会议（OSDI 22）上，2022年7月，加利福尼亚州旧金山，USENIX协会。

## A 操作符形状在我们的基准测试中


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>V0</td><td style='text-align: center; word-wrap: break-word;'>V1</td><td style='text-align: center; word-wrap: break-word;'>V2</td><td style='text-align: center; word-wrap: break-word;'>V3</td><td style='text-align: center; word-wrap: break-word;'>V4</td><td style='text-align: center; word-wrap: break-word;'>V5</td><td style='text-align: center; word-wrap: break-word;'>V6</td><td style='text-align: center; word-wrap: break-word;'>V7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>m</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>n</td><td style='text-align: center; word-wrap: break-word;'>16384</td><td style='text-align: center; word-wrap: break-word;'>43008</td><td style='text-align: center; word-wrap: break-word;'>14336</td><td style='text-align: center; word-wrap: break-word;'>57344</td><td style='text-align: center; word-wrap: break-word;'>14336</td><td style='text-align: center; word-wrap: break-word;'>9216</td><td style='text-align: center; word-wrap: break-word;'>36864</td><td style='text-align: center; word-wrap: break-word;'>9216</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>k</td><td style='text-align: center; word-wrap: break-word;'>16384</td><td style='text-align: center; word-wrap: break-word;'>14336</td><td style='text-align: center; word-wrap: break-word;'>14336</td><td style='text-align: center; word-wrap: break-word;'>14336</td><td style='text-align: center; word-wrap: break-word;'>57344</td><td style='text-align: center; word-wrap: break-word;'>9216</td><td style='text-align: center; word-wrap: break-word;'>9216</td><td style='text-align: center; word-wrap: break-word;'>36864</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>M0</td><td style='text-align: center; word-wrap: break-word;'>M1</td><td style='text-align: center; word-wrap: break-word;'>M2</td><td style='text-align: center; word-wrap: break-word;'>M3</td><td style='text-align: center; word-wrap: break-word;'>M4</td><td style='text-align: center; word-wrap: break-word;'>M5</td><td style='text-align: center; word-wrap: break-word;'>M6</td><td style='text-align: center; word-wrap: break-word;'>M7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>m</td><td style='text-align: center; word-wrap: break-word;'>4096</td><td style='text-align: center; word-wrap: break-word;'>4096</td><td style='text-align: center; word-wrap: break-word;'>4096</td><td style='text-align: center; word-wrap: break-word;'>4096</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>n</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>28672</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>28672</td><td style='text-align: center; word-wrap: break-word;'>8192</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>k</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>28672</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>28672</td></tr></table>
表2. 我们基准测试中的矩阵形状。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>FA0</td><td style='text-align: center; word-wrap: break-word;'>FA1</td><td style='text-align: center; word-wrap: break-word;'>FA2</td><td style='text-align: center; word-wrap: break-word;'>FA3</td><td style='text-align: center; word-wrap: break-word;'>FA4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>batch</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>nheads</td><td style='text-align: center; word-wrap: break-word;'>32</td><td style='text-align: center; word-wrap: break-word;'>32</td><td style='text-align: center; word-wrap: break-word;'>32</td><td style='text-align: center; word-wrap: break-word;'>32</td><td style='text-align: center; word-wrap: break-word;'>32</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>seq_len</td><td style='text-align: center; word-wrap: break-word;'>512</td><td style='text-align: center; word-wrap: break-word;'>512</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>4096</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>head_dim</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>causal</td><td style='text-align: center; word-wrap: break-word;'>true</td><td style='text-align: center; word-wrap: break-word;'>false</td><td style='text-align: center; word-wrap: break-word;'>true</td><td style='text-align: center; word-wrap: break-word;'>false</td><td style='text-align: center; word-wrap: break-word;'>true</td></tr></table>
<div style="text-align: center;">表3. 我们基准测试中的FlashAttention形状。</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>CC0</td><td style='text-align: center; word-wrap: break-word;'>CC1</td><td style='text-align: center; word-wrap: break-word;'>CC2</td><td style='text-align: center; word-wrap: break-word;'>CC3</td><td style='text-align: center; word-wrap: break-word;'>CC4</td><td style='text-align: center; word-wrap: break-word;'>CC5</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>batch</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>nheads</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>seq_len</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>2048</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>2048</td><td style='text-align: center; word-wrap: break-word;'>8192</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>head_dim</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>d_state</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>CT0</td><td style='text-align: center; word-wrap: break-word;'>CT1</td><td style='text-align: center; word-wrap: break-word;'>CT2</td><td style='text-align: center; word-wrap: break-word;'>CT3</td><td style='text-align: center; word-wrap: break-word;'>CT4</td><td style='text-align: center; word-wrap: break-word;'>CT5</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>batch</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>nheads</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>seq_len</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>2048</td><td style='text-align: center; word-wrap: break-word;'>8192</td><td style='text-align: center; word-wrap: break-word;'>1024</td><td style='text-align: center; word-wrap: break-word;'>2048</td><td style='text-align: center; word-wrap: break-word;'>8192</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>head_dim</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>64</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>d_state</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>128</td></tr></table>
<div style="text-align: center;">表4. 我们基准中的线性注意力形状。</div>

第 20 页

核实现

1 @tilelang.jit12         T.copy(B[k * block_K, bx * block_N], B_shared)

图16. 矩阵乘法的核实现。

### B.2 去量化矩阵乘法

@tilelang.jitCt_local = T.alloc_fragment((block_N, block_M), accum_dtype)

T.clear(Ct_local)T.copy(Ct_local, Ct[bx * block_N, by * block_M])

图17. 仅权重量化（$W_{FP4\_E2M1}A_{FP16}$）矩阵乘法的TiLELANG实现，展示了混合精度计算的简单形式支持。

第 21 页

### B.3 FlashMLA实现

def flash_attn(KV_shared = T.alloc_shared([block_N, dim], dtype)

cur_kv_head = by // (kv_group_num // block_H)

T.copy(Q[bx, by * VALID_BLOCK_H: (by + 1) * VALID_BLOCK_H, :], Q_shared)

T.loop_range = T.ceildiv(seqlen_kv, block_N)T.copy(scores_max, scores_max_prev)对于 i, j 在 T.Parallel(block_H, dim) 中：

<div style="text-align: center;">图18. 使用TiLELANG实现FlashMLA。</div>

收到2007年2月20日；修订于2009年3月12日；接受于2009年6月5日