# 2024-10-15-VisualRWKV-HD和UHD推进高分辨率处理视觉语言模型



第 1 页

# VisualRWKV-HD和UHD：推进视觉语言模型的高分辨率处理

李志恒 $ ^{1,2} $, 侯浩文 $ ^{2*} $

$ ^{1} $深圳大学人工智能系，深圳，中国

$ ^{2} $广东人工智能与数字经济实验室（SZ），深圳，中国

2410815011@mails.szu.edu.cn, houhaowen@qml.ac.cn

摘要

准确理解复杂的视觉信息对于视觉语言模型（VLMs）至关重要。提升图像分辨率可以改善视觉感知能力，不仅可以减少幻觉，还能提高在需要高分辨率的任务中的性能，例如文本密集或文档分析。在本文中，我们介绍了VisualRWKV-HD和VisualRWKV-UHD两种进展，这两种模型都是VisualRWKV模型家族的扩展，专门用于处理高分辨率视觉输入。对于VisualRWKV-HD，我们开发了一种无损下采样方法，将高分辨率视觉编码器与低分辨率编码器有效地集成，而不需要延长输入序列。对于VisualRWKV-UHD模型，我们通过将图像分割成四个部分并重新组合，增强了图像表示。这种技术使模型能够整合高分辨率和低分辨率特征，从而平衡粗粒度和细粒度信息。因此，该模型支持分辨率高达4096 x 4096像素，提供了更细致、更全面的视觉处理能力。VisualRWKV-HD和VisualRWKV-UHD不仅在VLM基准测试中取得了优异的结果，而且在文本密集型任务中也显示出了显著的性能提升。

## 1 引言

随着大型语言模型(LLMs)(Akyürek et al., 2024)(LLMs)(Achiam et al., 2023)的最近重大进展，视觉语言模型(VLMs)也迅速发展。处理视觉输入的努力(Peng et al., 2023)通过视觉指令微调(LLMs)持续增长。与此同时，具有线性时间复杂度的视觉语言模型，如VisualRWKV(Hou et al., 2024)和VL-Mamba(Qiao et al., 2024)，也被提出。然而，关于如何高效处理高分辨率视觉输入的线性视觉语言模型的研究仍然缺乏。提高图像分辨率可以提升视觉感知能力，不仅减少幻觉，还能提升对高分辨率任务的性能，如文本密集或文档分析。然而，高分辨率图像的挑战在于，它们往往导致计算需求增加和输入序列更长，这可能会影响模型的效率和性能(Hou等人，2024)。为了解决这些挑战，本文提出了VisualRWKV模型家族中的两个新型进展：VisualRWKV-HD和VisualRWKV-UHD。图1展示了VisualRWKV-HD和UHD的概述。这些模型专门设计用于利用高分辨率视觉输入的好处，同时保持计算效率和性能，这是线性RNN模型解决高分辨率任务的首次进展。本文有四个主要贡献：



1. VisualRWKV-HD with Ensemble of Encoders：我们引入了一个编码器的集合，其中输入图像的大小在SigLip、DINOv2和Segment Anything Model（SAM）的预训练过程中保持固定为1024。作为基础模型，SAM预期在具有不同图像大小的下游任务中表现出泛化能力。这对于高分辨率（HD）数据集尤为重要，这些数据集具有更大的尺寸和更多的细节。当图像分辨率与其训练分辨率1024相匹配时，SAM表现良好。因此，我们使用SAM支持分辨率高达1024 x 1024，在TextVQA等多个基准测试中实现了显著的性能提升。

第 2 页

<div style="text-align: center;"><img src="imgs/img_in_image_box_209_229_2254_999.jpg" alt="Image" width="82%" /></div>

<div style="text-align: center;">图1：VisualRWKV-HD和UHD概览。输入图像通过三个视觉编码器和高分辨率策略处理，然后通过多层感知器（MLP）和上下文门控生成图像特征。</div>

2. VisualRWKV-UHD：在VisualRWKV-UHD中，图像被分成四个部分，然后重新组合，使得图像特征既包含高分辨率也包含低分辨率的信息。这种方法平衡了粗糙和精细的特征，使得模型能够支持高达4096 x 4096的分辨率，同时确保图像标记不超过1024个。

3. MLP with Context Gating：我们发现过多的特征信息导致模型内部存在竞争。为了解决这个问题，我们引入了MLP with Context Gating来替换线性投影层，稳定了训练过程并提高了性能。

4. 高分辨率与低分辨率对齐：为了将高分辨率视觉编码器与低分辨率模块对齐，我们提出了一种替代方法，即将每个 $ 2 \times 2 $ 块（每个块包含四个相邻向量）组合成一个新的通道维度。这种方法无需额外的训练即可保留信息。

总之，本研究提出了VisualRWKV-HD和VisualRWKV-UHD模型。VisualRWKV-HD引入了一个预训练的视觉编码器集合，支持1024 x 1024的更高分辨率。另一方面，VisualRWKV-UHD旨在效率，能够处理更高的分辨率，支持最高4096 x 4096像素的输入。重要的是，它保持了最多1024个图像令牌，而切片方法倾向于使用过多的图像令牌，导致处理时间更长。全面的实验在八个流行的基准测试上进行，证明了这些模型的有效性，特别是在需要高分辨率视觉处理的任务中。此外，还提供了深入的分析，以提供对模型改进和能力的更深入理解。



## 2 相关工作

### 2.1 线性视觉语言模型

在快速发展的视觉语言模型（VLMs）领域（Bai et al., 2023），线性模型引入了融合图像和文本数据的创新策略。这些模型，以其简单的架构而闻名，在图像描述和视觉问答等任务中表现出色。线性视觉语言模型在高效融合视觉和文本信息方面取得了显著进展。VL-Mamba（Qiao et al., 2024）强调视觉和文本模态之间强大的对齐，采用模块化设计，使其能够适应多种应用场景，同时保持高性能。另一方面，VisualRWKV（Hou et al., 2024），包括其高分辨率变体，通过使用无损下采样和图像分割等技术来应对高分辨率图像处理的复杂性。这些方法有助于有效地整合高分辨率和低分辨率特征，确保必要的去噪和增强。

第 3 页

尾部得到保留。这些模型不仅代表了视觉语言模型领域的重大进展，而且还突出了效率、细节保留和多模态对齐方面的创新。随着它们继续发展，这些线性视觉语言模型将推动进一步的研究，特别是在处理复杂视觉信息方面。

### 2.2 高分辨率视觉语言模型

LLaVA-UHD(Xu等人，2024)是一种专门为高分辨率视觉任务设计的模型，它整合了先进的多模态能力，提升了其在图像描述和视觉问答等任务中的应用。其中一个关键优势在于它能够无缝地整合视觉和文本数据，从而根据复杂的视觉输入生成上下文相关的输出。这种整合通过优化模型架构实现，提高了效率和适应性，使其能够在各种任务中表现出色。该模型已经在大规模数据集上进行了训练，这提高了其泛化能力。这种训练使得LLaVA-UHD能够有效地理解细微的视觉细节和细微差别，使其在需要高精度视觉理解的应用中特别适用。

### 2.3 比较分析

为了阐明VisualRWKV-HD和VisualRWKV-UHD的创新，我们将它们与现有的模型如LLAVA-UHD和VisualRWKV进行比较。VisualRWKV结合了视觉编码器和语言模型以实现跨模态理解，但在处理高分辨率图像时会遇到计算瓶颈。LLAVA-UHD通过多尺度特征融合和自适应分辨率机制来处理高分辨率处理，尽管这可能导致计算需求增加。相比之下，VisualRWKV-HD使用预训练的SAM视觉编码器来高效处理高分辨率输入，而不会增加输入序列长度，并优化模型架构以减少复杂性。VisualRWKV-UHD进一步整合了高分辨率和低分辨率特征，通过图像分割实现，并引入了MLPWithContextGating机制以提高细节保留和训练稳定性。总的来说，VisualRWKV-HD和VisualRWKV-UHD在高分辨率图像处理中比LLAVA-UHD和VisualRWKV更高效，并且能够更好地保留细节。

### 3.1 VisualRWKV-HD

3. 方法

#### 3.1.1 编码器集成

在之前的VisualRWKV版本中，我们使用了专注于处理低分辨率图像的SIGLIP和DINO编码器，取得了良好的效果。在VisualRWKV-HD中，我们引入了一个预训练的高分辨率SAM视觉编码器，将支持的分辨率提升至1024 x 1024。这一改进显著提升了模型在多个基准测试中的性能，使其在处理需要丰富细节和视觉复杂性的任务时更加高效和准确。SAM编码器的引入使得模型能够更好地捕捉图像中的关键特征，从而增强了其整体的视觉理解能力。

#### 3.1.2 无损下采样器

SigLip和DINOv2，作为VisualRWKV第一代的编码器，在低分辨率图像任务中表现出了有效性。在这一代中，VisualRWKV-HD引入了SAM编码器。为了解决与SAM编码器对齐的问题，我们设计了一个无损下采样器，它将2x2块（每个块包含四个相邻向量）组合成一个新的通道维度。这种方法使得高分辨率视觉编码器能够有效地与低分辨率模块对齐，同时在训练过程中不丢失信息。实验结果表明，这种方法有效地保留了图像细节，并提高了模型性能。

你可以使用一个公式来表示将 $2 \times 2$ 块组合成新通道维度的过程。这里是一个建议的公式：
 $$ C_{n e w}=\mathbf{C o n c a t}(C_{1},C_{2},C_{3},C_{4}) $$ 
地点：

- $ C_{new} $ 表示由四个块拼接形成的新通道维度。

- $ C_{1}, C_{2}, C_{3}, C_{4} $ 是 2x2 块，每个块包含四个相邻向量。

这个公式说明了新通道维度是如何通过有效地组合较低分辨率的表示来创建的。

### 3.2 VisualRWKV-UHD

在这个模型中，我们进一步将图像分成四部分，然后将它们聚合在一起，确保

第 4 页

<div style="text-align: center;"><img src="imgs/img_in_image_box_206_206_2214_916.jpg" alt="Image" width="80%" /></div>

图2：UHD策略：我们将输入图像分为四个部分，然后分别通过SigLip、DINOv2和SAM编码器处理。从每个部分得到的特征进行拼接，并通过avgpool2d进行池化。这些拼接后的特征与之前步骤中生成的HD特征进行融合，最终生成UHD特征。

图像表示包含高分辨率和低分辨率特征，如图2所示。这种策略平衡了粗糙特征和精细特征，将支持的分辨率提高到4096 x 4096。通过这种创新方法，模型可以更准确地理解和分析输入图像中的不同细节，当处理复杂的视觉信息时。

### 3.3 投影层

在训练过程中，我们发现过多的特征信息导致了模型中的对抗效应。为了解决这个问题，我们引入了MLP With Context Gating来替代传统的线性投影层。

上下文门控(Miech等人，2017年)，一种用于改进神经网络的机制，通过动态调整特征表示来实现。MLP上下文门控增强了多层感知机(MLP)的性能，通过添加一个门控机制来调节输入特征。上下文门控层应用一个非线性变换，使用一个学习的权重矩阵和偏置项，然后通过sigmoid激活。得到的门输出与原始输入逐元素相乘，从而控制哪些特征被传递，这取决于上下文。
 $$ y=\sigma(W_{g}x+b_{g})\odot x $$ 
在这个公式中，$y$表示输出，$W_{g}$是门控权重矩阵，$b_{g}$是偏置项，$x$是输入数据。使用的激活函数是sigmoid函数$\sigma$，$\odot$表示逐元素乘法。这个机制通过动态调整输入特征来优化模型的性能。



这种调整稳定了训练过程，显著提高了模型的性能。通过更有效地管理特征信息，模型可以避免过拟合和不稳定性，从而提高了整体处理效率和准确性。

4实验

在实验部分，我们评估了VisualRWKV-HD和VisualRWKV-UHD模型在各种任务中的性能，重点关注它们处理高分辨率视觉输入的能力。我们在几个流行的视觉语言模型（VLM）基准测试上进行了实验，特别关注需要高分辨率图像处理的文本丰富和文档分析任务。

### 4.1 基线

在基线部分，我们将提出的VisualRWKV-HD和VisualRWKV-UHD模型的性能与标准VisualRWKV模型进行比较，以了解高分辨率处理对模型能力的增强。标准VisualRWKV(Hou et al., 2024)作为基线，代表了我们模型家族的基础架构，但缺乏高分辨率增强。通过比较不同版本的性能指标，我们旨在明确高分辨率处理对文本密集型任务和文档分析的具体影响。

第 5 页


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Vision Encoder</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextVQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B</td><td style='text-align: center; word-wrap: break-word;'>CLIP</td><td style='text-align: center; word-wrap: break-word;'>336</td><td style='text-align: center; word-wrap: break-word;'>59.05</td><td style='text-align: center; word-wrap: break-word;'>43.57</td><td style='text-align: center; word-wrap: break-word;'>55.23</td><td style='text-align: center; word-wrap: break-word;'>29.84</td><td style='text-align: center; word-wrap: break-word;'>1204.90/245.00</td><td style='text-align: center; word-wrap: break-word;'>0.832</td><td style='text-align: center; word-wrap: break-word;'>55.75/53.17</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ SigLIP and DINOv2</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2</td><td style='text-align: center; word-wrap: break-word;'>384</td><td style='text-align: center; word-wrap: break-word;'>53.35</td><td style='text-align: center; word-wrap: break-word;'>41.08</td><td style='text-align: center; word-wrap: break-word;'>56.55</td><td style='text-align: center; word-wrap: break-word;'>31.44</td><td style='text-align: center; word-wrap: break-word;'>1273.67/213.92</td><td style='text-align: center; word-wrap: break-word;'>0.870</td><td style='text-align: center; word-wrap: break-word;'>57.39/51.72</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>384</td><td style='text-align: center; word-wrap: break-word;'>57.02</td><td style='text-align: center; word-wrap: break-word;'>48.70</td><td style='text-align: center; word-wrap: break-word;'>58.23</td><td style='text-align: center; word-wrap: break-word;'>30.46</td><td style='text-align: center; word-wrap: break-word;'>1250.50/213.21</td><td style='text-align: center; word-wrap: break-word;'>0.818</td><td style='text-align: center; word-wrap: break-word;'>58.84/57.13</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ Scale up resolution</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>58.55</td><td style='text-align: center; word-wrap: break-word;'>47.75</td><td style='text-align: center; word-wrap: break-word;'>60.96</td><td style='text-align: center; word-wrap: break-word;'>33.12</td><td style='text-align: center; word-wrap: break-word;'>1305.38/224.64</td><td style='text-align: center; word-wrap: break-word;'>0.855</td><td style='text-align: center; word-wrap: break-word;'>59.45/53.09</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ MLP with Context Gating</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>54.39</td><td style='text-align: center; word-wrap: break-word;'>54.71</td><td style='text-align: center; word-wrap: break-word;'>60.84</td><td style='text-align: center; word-wrap: break-word;'>54.97</td><td style='text-align: center; word-wrap: break-word;'>1378.62/266.07</td><td style='text-align: center; word-wrap: break-word;'>0.860</td><td style='text-align: center; word-wrap: break-word;'>60.31/55.41</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ HD559k dataset</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>58.75</td><td style='text-align: center; word-wrap: break-word;'>55.62</td><td style='text-align: center; word-wrap: break-word;'>60.18</td><td style='text-align: center; word-wrap: break-word;'>51.59</td><td style='text-align: center; word-wrap: break-word;'>1271.03/230.36</td><td style='text-align: center; word-wrap: break-word;'>0.857</td><td style='text-align: center; word-wrap: break-word;'>57.56/51.03</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>+ HD667k dataset</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>56.07</td><td style='text-align: center; word-wrap: break-word;'>56.21</td><td style='text-align: center; word-wrap: break-word;'>50.52</td><td style='text-align: center; word-wrap: break-word;'>40.89</td><td style='text-align: center; word-wrap: break-word;'>1221.22/232.14</td><td style='text-align: center; word-wrap: break-word;'>0.853</td><td style='text-align: center; word-wrap: break-word;'>58.42/52.84</td></tr></table>
<div style="text-align: center;">表1：VisualRWKV-HD/UHD模型的缩放结果及其在不同学术任务上的性能指标。表中加粗的数据表示最佳性能。</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Dataset</td><td style='text-align: center; word-wrap: break-word;'>DocVQA</td><td style='text-align: center; word-wrap: break-word;'>InfographicVQA</td><td style='text-align: center; word-wrap: break-word;'>ChartQA</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B</td><td style='text-align: center; word-wrap: break-word;'>mix665k</td><td style='text-align: center; word-wrap: break-word;'>10.88</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>10.00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B + MLP</td><td style='text-align: center; word-wrap: break-word;'>mix665k</td><td style='text-align: center; word-wrap: break-word;'>11.00</td><td style='text-align: center; word-wrap: break-word;'>11.00</td><td style='text-align: center; word-wrap: break-word;'>8.00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B + MLP (HD)</td><td style='text-align: center; word-wrap: break-word;'>HD559k</td><td style='text-align: center; word-wrap: break-word;'>29.11</td><td style='text-align: center; word-wrap: break-word;'>15.53</td><td style='text-align: center; word-wrap: break-word;'>33.04</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B + MLP (UHD)</td><td style='text-align: center; word-wrap: break-word;'>HD559k</td><td style='text-align: center; word-wrap: break-word;'>35.11</td><td style='text-align: center; word-wrap: break-word;'>16.49</td><td style='text-align: center; word-wrap: break-word;'>39.32</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B + MLP (UHD)</td><td style='text-align: center; word-wrap: break-word;'>HD667k</td><td style='text-align: center; word-wrap: break-word;'>35.37</td><td style='text-align: center; word-wrap: break-word;'>16.82</td><td style='text-align: center; word-wrap: break-word;'>40.28</td></tr></table>
表2：视觉RWKV-HD/UHD模型在文本密集型任务上的缩放结果

这些任务通常需要识别细小的细节，如精细的文本和文档布局，因此高分辨率模型如VisualRWKV-HD和UHD的表现提升尤为重要。我们将基线模型的结果与高分辨率版本进行比较，以量化处理更多像素和更详细输入的好处，从而强调在涉及复杂视觉信息的任务中提高视觉分辨率的重要性。

### 4.2 基准测试

我们对VisualRWKV-HD和VisualRWKV-UHD进行了广泛的评估，使用了八个多样化的基准数据集：SQA(Lu等人，2022年)、TextVQA(Singh等人，2019年)、GQA(Hudson和Manning，2019年)（准确率）、VizWiz(Bigham等人，2010年)、MME(Fu等人，2023年)、POPE(Li等人，2023年)、MMB(Liu等人，2023年)和MMB-CN，如表1所示。这些数据集涵盖了广泛的视觉语言理解任务，每个任务都需要对视觉和语言进行细致的理解。SQA专注于场景化的问答，要求模型理解复杂的视觉和语言语境，以提供准确的回答。TextVQA的图像嵌入了文本，挑战模型从视觉输入中准确提取和解释文本信息。GQA（准确性）评估模型在图像内容推理上的精确性，提出需要深入理解图像的问题。VizWiz测试模型在真实场景中的表现。

在充满噪声和不完整的视觉数据的世界背景下，这是一项特别具有挑战性的任务，旨在帮助视障人士。此外，我们还融入了多模态情感识别（MME），其中模型被要求从视觉和文本输入中识别情感。POPE评估了模型从视觉内容中推断人格特征的能力。最后，我们包括了MMB和MMB-CN基准，用于评估模型在多模态翻译和问答任务中的性能，其中MMB-CN专门用于中文视觉语言理解。我们还在文档基准上进行了测试，包括DocVQA（Mathew等人，2021年）、InfographicVQA（Mathew等人，2022年）和ChartQA（Masry等人，2022年），以评估我们提出的方法的性能，如表2所示。DocVQA关注文档理解，我们的模型在混合文本和图像内容的解释以及回答查询方面表现出色。在InfographicVQA中，我们的方法成功地分析了视觉复杂的信息图，准确地识别了关键元素和关系。最后，ChartQA评估了我们的模型在理解各种图表类型方面的能力，展示了优秀的性能，在理解图表数据和提供洞察力方面。总的来说，这些基准测试突出了我们方法在提高高分辨率图像理解方面的优势，并证明了其在各种视觉语言任务中的适用性。这些数据集为评估模型在处理高分辨率视觉输入方面的能力提供了强大的基准。

第 6 页

多模态和语言。这些基准测试的结果突显了VisualRWKV-HD和VisualRWKV-UHD相对于较低分辨率基线的显著性能提升，证明了它们在处理复杂和高分辨率视觉数据方面的有效性。

### 4.3 定量评估

在定量评估中，我们评估了我们提出的VisualRWKV-HD和VisualRWKV-UHD模型与几个基准模型的性能，以突出它们在处理高分辨率视觉输入方面的进步，如摘要所述。表3展示了我们的模型与其他领先视觉语言模型（VLMs）的比较。在SQA基准中，VisualRWKV-UHD展示了其处理高分辨率图像的卓越能力，得分为56.97，超过了Mobile1.7B的54.7，突显了我们模型分辨率增强的优势。同样，在GQA基准中，Mobile1.7B得分为56.1，而VisualRWKV-HD和UHD分别得到60.84和59.52，这显示了我们创新的无损下采样和分段图像表示技术带来的明显改进。对于POPE等任务，其中精度至关重要，VisualRWKV-HD的表现优于Mobile1.7B，得分为86.0，而UHD也超过了84.5。在MMB基准测试中，我们的模型显著优于Mobile1.7B，HD得分为61.31，UHD为58.42，而Mobile1.7B为53.2。在MME感知任务中，VisualRWKV-HD表现出色，得分为1378.62，明显高于Mobile1.7B的1196.2，UHD也表现良好，得分为1321.33。有趣的是，即使与参数更大的模型（例如Mini-Gemini（2B参数）和VisualRWKV-HD（1.6B参数））相比，我们的模型也取得了更好的结果，特别是在MME感知任务（HD：1378.62，Mini-Gemini：1341）和MMB（HD：60.31，Mini-Gemini：59.8）上。这突显了我们模型在视觉处理方面的高效性。最后，我们的模型在GQA基准测试中优于TinyLLaVa-v1，VisualRWKV-HD得分为60.84，UHD得分为59.52，而TinyLLaVa-v1得分为57.5。总的来说，结果证实了通过无损下采样和分段图像技术增强视觉分辨率处理的改进，使得VisualRWKV-HD和UHD在高分辨率任务中表现出色，在复杂的视觉基准测试中与低分辨率模型和更大参数模型相比具有明显优势。



### 4.4 消融研究

在实验部分，我们评估了VisualRWKV-HD和VisualRWKV-UHD模型在各种任务中的表现，强调它们在处理高分辨率视觉输入方面的有效性。我们的实验针对几个在视觉语言模型（VLMs）领域中已建立的基准，特别是那些文本密集且涉及文档分析的任务，这些任务都能从高级高分辨率图像处理能力中受益。这项评估旨在展示这些模型在现实世界应用中的表现，在这些应用中，细节和清晰度至关重要。

#### 4.4.1 视觉解码器消融实验

在本节中，我们通过384分辨率对Siglip和Siglip + DINOv2视觉编码器进行了比较，如表4所示。结果显示了全面的性能提升。我们进一步通过将SAM集成到Siglip + DINOv2框架中，在SQA、TQA和MMB/MMB $ _{CN} $数据集上提升了模型性能。我们评估了DINOv2和SAM对训练稳定性和计算效率的影响。评估的关键指标包括训练稳定性和总体计算成本，以及各数据集上的性能结果。在引入DINOv2和SAM后，模型在训练过程中表现出更好的稳定性，并在所有数据集上表现出更好的性能。这凸显了SAM和DINOv2视觉编码器在有效处理高分辨率输入方面的重要作用。

#### 4.4.2 分辨率消融实验

在本实验中，我们基于引入siglip、DINOv2和SAM的基础上，通过将分辨率从384提升到448，如表5所示，进行了进一步的研究。这种调整提升了模型在SQA、GQA和VizWiz等数据集上的性能。我们比较了VisualRWKV-HD和VisualRWKV-UHD在不同分辨率设置下的性能，探索了分辨率提升对准确性和处理时间的影响。实验结果表明：高分辨率显著提高了文本密集任务的准确性。尽管推理

第 7 页


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Method</td><td style='text-align: center; word-wrap: break-word;'>LLM</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MobileVLM 1.7B</td><td style='text-align: center; word-wrap: break-word;'>MobileLLaMA-1.4B</td><td style='text-align: center; word-wrap: break-word;'>336</td><td style='text-align: center; word-wrap: break-word;'>54.7</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>56.1</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>1196.2/-</td><td style='text-align: center; word-wrap: break-word;'>84.5</td><td style='text-align: center; word-wrap: break-word;'>53.2/-</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Mini-Gemini</td><td style='text-align: center; word-wrap: break-word;'>Gemma-2B</td><td style='text-align: center; word-wrap: break-word;'>336</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>1341/312</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>59.8/-</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>TinyLLaVa-v1</td><td style='text-align: center; word-wrap: break-word;'>TinyLlama-1.1B</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>59.4</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>57.5</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>-</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV</td><td style='text-align: center; word-wrap: break-word;'>VisualRWKV6-1.6B</td><td style='text-align: center; word-wrap: break-word;'>336</td><td style='text-align: center; word-wrap: break-word;'>59.1</td><td style='text-align: center; word-wrap: break-word;'>43.6</td><td style='text-align: center; word-wrap: break-word;'>55.2</td><td style='text-align: center; word-wrap: break-word;'>-</td><td style='text-align: center; word-wrap: break-word;'>1204.9/-</td><td style='text-align: center; word-wrap: break-word;'>83.2</td><td style='text-align: center; word-wrap: break-word;'>55.8/53.2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-HD</td><td style='text-align: center; word-wrap: break-word;'>VisualRWKV6-1.6B</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>54.39</td><td style='text-align: center; word-wrap: break-word;'>54.71</td><td style='text-align: center; word-wrap: break-word;'>60.84</td><td style='text-align: center; word-wrap: break-word;'>54.97</td><td style='text-align: center; word-wrap: break-word;'>1378.62/266.07</td><td style='text-align: center; word-wrap: break-word;'>86.0</td><td style='text-align: center; word-wrap: break-word;'>60.31/55.41</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-UHD</td><td style='text-align: center; word-wrap: break-word;'>VisualRWKV6-1.6B</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>56.97</td><td style='text-align: center; word-wrap: break-word;'>56.31</td><td style='text-align: center; word-wrap: break-word;'>59.52</td><td style='text-align: center; word-wrap: break-word;'>49.88</td><td style='text-align: center; word-wrap: break-word;'>1321.33/232.14</td><td style='text-align: center; word-wrap: break-word;'>85.3</td><td style='text-align: center; word-wrap: break-word;'>58.42/52.84</td></tr></table>
表3：不同视觉语言模型在各种学术任务上的性能比较。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Vision Encoder</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextVQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B</td><td style='text-align: center; word-wrap: break-word;'>CLIP</td><td style='text-align: center; word-wrap: break-word;'>336</td><td style='text-align: center; word-wrap: break-word;'>59.05</td><td style='text-align: center; word-wrap: break-word;'>43.57</td><td style='text-align: center; word-wrap: break-word;'>55.23</td><td style='text-align: center; word-wrap: break-word;'>29.84</td><td style='text-align: center; word-wrap: break-word;'>1204.90/245.00</td><td style='text-align: center; word-wrap: break-word;'>0.832</td><td style='text-align: center; word-wrap: break-word;'>55.75/53.17</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2</td><td style='text-align: center; word-wrap: break-word;'>384</td><td style='text-align: center; word-wrap: break-word;'>53.35</td><td style='text-align: center; word-wrap: break-word;'>41.08</td><td style='text-align: center; word-wrap: break-word;'>56.55</td><td style='text-align: center; word-wrap: break-word;'>31.44</td><td style='text-align: center; word-wrap: break-word;'>1273.67/213.92</td><td style='text-align: center; word-wrap: break-word;'>0.870</td><td style='text-align: center; word-wrap: break-word;'>57.39/51.72</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV 1.6B</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>384</td><td style='text-align: center; word-wrap: break-word;'>57.02</td><td style='text-align: center; word-wrap: break-word;'>48.70</td><td style='text-align: center; word-wrap: break-word;'>58.23</td><td style='text-align: center; word-wrap: break-word;'>30.46</td><td style='text-align: center; word-wrap: break-word;'>1250.50/213.21</td><td style='text-align: center; word-wrap: break-word;'>0.818</td><td style='text-align: center; word-wrap: break-word;'>58.84/57.13</td></tr></table>
表4：视觉编码器的消融实验

随着时间的推移，分割和下采样等技术有效控制了计算成本，实现了效率和准确性之间的平衡。

#### 4.4.3 投影的消融研究

在这个实验中，我们探索了在448分辨率下使用MLP-WithContextGating替代线性投影方法的影响，如表6所示。目的是比较具有和没有MLP-WithContextGating的模型，以评估其对训练稳定性和计算效率的影响。在添加MLP-WithContextGating后，模型在TQA、GQA和POPE等任务中表现出显著的改进。虽然改进的程度有所不同，但整体性能超过了使用线性投影方法的模型。当移除MLP-WithContextGating时，模型的训练稳定性下降，内存使用量增加，这突显了这种技术在有效处理高分辨率输入方面的重要性。这些发现表明，MLP-WithContextGating在提高计算效率和模型稳定性方面发挥着关键作用，尤其是在处理高分辨率图像时。

#### 4.4.4 数据规模扩展的消融实验

在实验中，我们比较了不同数据集（mix665k、HD559k和HD667k）在VisualRWKV-HD和UHD模型上的性能，重点关注DocVQA、InfographicVQA、ChartQA、TQA、MME和VizWiz等任务，如表7所示。结果显示，随着数据集规模的增加，模型性能显著提升。通过比较mix665k、HD559k和HD667k数据集的使用，我们评估了它们对VisualRWKV-HD和UHD模型训练稳定性和计算效率的影响：VisualRWKV-HD：在引入HD559k数据集后，与mix665k相比，模型在DocVQA、InfographicVQA和ChartQA等任务上表现出显著提升。VizWiz和TQA的性能也有显著增长。这表明数据规模和质量的提高有助于模型处理复杂的视觉语言任务。



VisualRWKV-UHD：随着HD559k数据集的引入，在TQA和SQA任务上的表现进一步提升，这证实了下采样方法在保留数据细节的同时增强模型泛化能力的有效性。通过使用更大的高分辨率数据集，模型能够更好地理解文本丰富的视觉场景，并在多个任务中表现出更强的鲁棒性。此外，在VisualRWKV-UHD中，处理HD559k和HD667k数据集时，将图像分成四部分并聚合，使模型能够整合高分辨率和低分辨率特征。这种方法增强了图像表示，使模型在需要详细视觉分析的任务中表现更佳。

### 4.5 效率分析

本文提出的方法主要在通道维度上拼接特征，并保持图像令牌数量不超过1024，而不增加其数量。与其他方法通过增加图像令牌数量来膨胀输入图像令牌，从而影响视觉语言模型（VLMs）的推理速度不同，本文的方法保持了效率。

在预填充阶段，VisualRWKV-UHD处理的图像数量是VisualRWKV-HD的四倍，这导致效率略有下降，但提高了高分辨率图像的理解能力。

第 8 页


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Vision Encoder</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextVQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-HD</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>384</td><td style='text-align: center; word-wrap: break-word;'>57.02</td><td style='text-align: center; word-wrap: break-word;'>48.70</td><td style='text-align: center; word-wrap: break-word;'>58.23</td><td style='text-align: center; word-wrap: break-word;'>30.46</td><td style='text-align: center; word-wrap: break-word;'>1250.50/213.21</td><td style='text-align: center; word-wrap: break-word;'>0.818</td><td style='text-align: center; word-wrap: break-word;'>58.84/57.13</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-HD</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>58.55</td><td style='text-align: center; word-wrap: break-word;'>47.75</td><td style='text-align: center; word-wrap: break-word;'>60.96</td><td style='text-align: center; word-wrap: break-word;'>33.12</td><td style='text-align: center; word-wrap: break-word;'>1305.38/224.64</td><td style='text-align: center; word-wrap: break-word;'>0.855</td><td style='text-align: center; word-wrap: break-word;'>59.45/53.09</td></tr></table>
表5：在不同分辨率下对VisualRWKV-HD进行的消融实验。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Vision Encoder</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextVQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV + Linear Projection</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>58.55</td><td style='text-align: center; word-wrap: break-word;'>47.75</td><td style='text-align: center; word-wrap: break-word;'>60.96</td><td style='text-align: center; word-wrap: break-word;'>33.12</td><td style='text-align: center; word-wrap: break-word;'>1305.38/224.64</td><td style='text-align: center; word-wrap: break-word;'>0.855</td><td style='text-align: center; word-wrap: break-word;'>59.45/53.09</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV + MLP</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>54.39</td><td style='text-align: center; word-wrap: break-word;'>54.71</td><td style='text-align: center; word-wrap: break-word;'>60.84</td><td style='text-align: center; word-wrap: break-word;'>54.97</td><td style='text-align: center; word-wrap: break-word;'>1378.62/266.07</td><td style='text-align: center; word-wrap: break-word;'>0.860</td><td style='text-align: center; word-wrap: break-word;'>60.31/55.41</td></tr></table>
表6：投影层的消融实验。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Model</td><td style='text-align: center; word-wrap: break-word;'>Dataset</td><td style='text-align: center; word-wrap: break-word;'>Vision Encoder</td><td style='text-align: center; word-wrap: break-word;'>Resolution</td><td style='text-align: center; word-wrap: break-word;'>SQA</td><td style='text-align: center; word-wrap: break-word;'>TextVQA</td><td style='text-align: center; word-wrap: break-word;'>GQA</td><td style='text-align: center; word-wrap: break-word;'>VizWiz</td><td style='text-align: center; word-wrap: break-word;'>MME</td><td style='text-align: center; word-wrap: break-word;'>POPE</td><td style='text-align: center; word-wrap: break-word;'>MMB/MMB-CN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-UHD</td><td style='text-align: center; word-wrap: break-word;'>mix665k</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>54.39</td><td style='text-align: center; word-wrap: break-word;'>54.71</td><td style='text-align: center; word-wrap: break-word;'>60.84</td><td style='text-align: center; word-wrap: break-word;'>54.97</td><td style='text-align: center; word-wrap: break-word;'>1378.62/266.07</td><td style='text-align: center; word-wrap: break-word;'>0.860</td><td style='text-align: center; word-wrap: break-word;'>60.31/55.41</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-UHD</td><td style='text-align: center; word-wrap: break-word;'>HD559k</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>58.75</td><td style='text-align: center; word-wrap: break-word;'>55.62</td><td style='text-align: center; word-wrap: break-word;'>60.18</td><td style='text-align: center; word-wrap: break-word;'>51.59</td><td style='text-align: center; word-wrap: break-word;'>1271.03/230.36</td><td style='text-align: center; word-wrap: break-word;'>0.857</td><td style='text-align: center; word-wrap: break-word;'>57.56/51.03</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>VisualRWKV-UHD</td><td style='text-align: center; word-wrap: break-word;'>HD667k</td><td style='text-align: center; word-wrap: break-word;'>SigLIP + DINOv2 + SAM-b-1024</td><td style='text-align: center; word-wrap: break-word;'>448</td><td style='text-align: center; word-wrap: break-word;'>56.97</td><td style='text-align: center; word-wrap: break-word;'>56.31</td><td style='text-align: center; word-wrap: break-word;'>59.52</td><td style='text-align: center; word-wrap: break-word;'>49.88</td><td style='text-align: center; word-wrap: break-word;'>1321.33/232.14</td><td style='text-align: center; word-wrap: break-word;'>0.853</td><td style='text-align: center; word-wrap: break-word;'>58.42/52.84</td></tr></table>
表7：在不同数据集上对VisualRWKV-UHD进行的消融实验。

在解码阶段，然而，VisualRWKV-UHD和VisualRWKV-HD的速度几乎相同。这使我们能够充分利用RWKV的高效推理能力，从而获得更快的推理速度和更低的内存使用量，相比基于Transformer的视觉语言模型。

第五章：结论

在本文中，我们介绍了VisualRWKV-HD和VisualRWKV-UHD两种先进模型，它们是VisualRWKV家族的一部分，专门设计用于处理高分辨率视觉输入。通过在SQA、GQA和VizWiz等多个基准测试中的全面评估，我们证明了这些模型在文本密集型和文档分析任务中显著优于传统方法。

引入了诸如无损下采样、图像表示分段和稳健的视觉编码器（DI-NOv2和SAM）等技术，不仅提高了模型的准确性和效率，还稳定了训练过程。与LLaVA-UHD的比较分析表明，VisualRWKV模型在计算成本、内存效率和处理速度方面达到了更好的平衡，使其适用于需要高精度的实时应用。

这些发现强调了在复杂的视觉语言任务中进行高分辨率处理的重要性，凸显了VisualRWKV-HD和UHD作为现实世界应用中可能有价值的工具的潜力。我们的结果呼吁继续研究优化模型架构和技术，以进一步提高视觉处理能力，从而增强视觉语言模型的视觉处理能力。



限制条件

尽管VisualRWKV-HD和VisualRWKV-UHD模型在性能上有显著提升，但仍存在一些局限性。首先，其高计算和内存需求可能限制了用户，尤其是在计算资源有限的用户，从而影响了实时应用。其次，模型高度依赖训练数据的质量和数量；高质量标注数据的可用性有限可能会影响其有效性。缺乏决策过程的可解释性仍然是一个挑战，尤其是在医疗保健和金融等关键领域。此外，尽管模型在基准任务上表现出色，但其泛化能力在多样化的新场景中仍需进一步验证。最后，将这些模型与其他模态（如音频或触觉数据）集成的研究仍在探索中，这可能会限制其在多模态学习环境中的应用潜力。解决这些局限性对于提高VisualRWKV模型在实际应用中的实用性至关重要。

## 参考文献

Josh Achiam, Steven Adler, Sandhini Agarwal, Lama Ahmad, Ilge Akkaya, Florencia Leoni Aleman, Diogo Almeida, Janko Altenschmidt, Sam Altman, Shyamal Anadkat, 等。2023. GPT-4技术报告。arXiv预印本 arXiv:2303.08774。

Ekin Akyürek, Bailin Wang, Yoon Kim, 和 Jacob Andreas. 2024. 上下文语言学习：架构和算法。预印本，arXiv:2401.12973。

金泽白、白舒、杨舒颖、王世杰、坦西安、王鹏、林俊林、周昌、周正源。2023. Qwen-vl：一种前沿大规模多模态语言模型。

第 9 页

具有多种能力的视觉语言模型。arXiv预印本 arXiv:2308.12966。

Jeffrey P Bigham, Chandrika Jayant, Hanjie Ji, Greg Little, Andrew Miller, Robert C Miller, Robin Miller, Aubrey Tatarowicz, Brandyn White, Samuel White, et al. 2010. Vizwiz: nearly real-time answers to visual questions. In Proceedings of the 23rd annual ACM symposium on User interface software and technology, pages 333–342.

Chaoyou Fu, Peixian Chen, Yunhang Shen, Yulei Qin, Mengdan Zhang, Xu Lin, Zhenyu Qiu, Wei Lin, Jinrui Yang, Xiawu Zheng, 等。2023. Mme: 一个全面评估多模态大语言模型的基准。arXiv预印本 arXiv:2306.13394。

Haowen Hou, Peigen Zeng, Fei Ma, 和 Fei Richard Yu. 2024. Visualrwkv: 探索循环神经网络在视觉语言模型中的应用. arXiv预印本 arXiv:2406.13362.

Drew A. Hudson 和 Christopher D. Manning. 2019. Gqa: 一个用于真实世界视觉推理和组合问答的新数据集. 2019年计算机视觉与模式识别年会 (CVPR), 页码 6693–6702.

李奕凡，杜一凡，周君，王晋鹏，赵文新，和翁人杰。2023. 评估大型视觉-语言模型中的物体幻觉。arXiv预印本 arXiv:2305.10355。

刘热泰、李春云、李慧、李永哲. 2024. 视觉指令微调提升的基线. 在计算机视觉与模式识别年会上，第26296-26306页。

刘元亮，杜鸿东，刘泽源，李博，张祥璋，赵波，叶元，王强，何鸿，刘威，等。2023. Mmbench：你的多模态模型是全能型选手吗？arXiv预印本 arXiv:2307.06281。

Pan Lu, Swaroop Mishra, Tony Xia, Liang Qiu, Kai-Wei Chang, Song-Chun Zhu, Oyvind Tafjord, Peter Clark, and A. Kalyan. 2022. 学习解释：通过思维链进行科学问答的多模态推理. ArXiv, abs/2209.09513.

Ahmed Masry, Do Xuan Long, Jia Qing Tan, Shafiq Joty, and Enamul Hoque. 2022. Chartqa: 一个用于图表问答的基准，结合视觉和逻辑推理。arXiv预印本：2203.10244。

Minesh Mathew, Viraj Bagal, Rubèn Tito, Dimosthenis Karatzas, Ernest Valveny, 和 CV Jawahar. 2022. 信息图vqa. 在 IEEE/CVF 冬季会议上计算机视觉应用会议上的论文集中，页码 1697–1706。

Minesh Mathew, Dimosthenis Karatzas, 和 CV Jawahar. 2021. Docvqa: 一个用于文档图像VQA的数据集. 在IEEE/CVF冬季计算机视觉应用会议上, 2200–2209页.

Antoine Miech, Ivan Laptev, 和 Josef Sivic. 2017. 用于视频分类的可学习池化与上下文门控. arXiv预印本 arXiv:1706.06905.

Bo Peng, Eric Alcaide, Quentin Anthony, Alon Albalak, Samuel Arcadinho, Stella Biderman, Huanqi Cao, Xin Cheng, Michael Chung, Matteo Grella, Kranthi Kiran GV, Xuzheng He, Haowen Hou, Jiaju Lin, Przemyslaw Kazienko, Jan Kocon, Jiaming Kong, Bartlomiej Koptyra, Hayden Lau, Krishna Sri Ipsit Mantri, Ferdinand Mom, Atsushi Saito, Guangyu Song, Xiangru Tang, Bolun Wang, Johan S. Wind, Stanislaw Wozniak, Ruichong Zhang, Zhenyuan Zhang, Qihang Zhao, Peng Zhou, Qinghua Zhou, Jian Zhu, and Rui-Jie Zhu. 2023. Rwkv: Reinventing rnns for the transformer era. Preprint, arXiv:2305.13048.

Yanyuan Qiao, Zheng Yu, Longteng Guo, Sihan Chen, Zijia Zhao, Mingzhen Sun, Qi Wu, and Jing Liu. 2024. Vl-mamba: 探索状态空间模型在多模态学习中的应用. arXiv预印本 arXiv:2403.13600.

Amanpreet Singh, Vivek Natarajan, Meet Shah, Yu Jiang, Xinlei Chen, Dhruv Batra, Devi Parikh, and Marcus Rohrbach. 2019. Towards vqa models that can read. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, pages 8317–8326.

Ruyi Xu, Yuan Yao, Zonghao Guo, Junbo Cui, Zanlin Ni, Chunjiang Ge, Tat-Seng Chua, Zhiyuan Liu, Maosong Sun, 和 Gao Huang. 2024. Llava-uhd: 一个能够感知任意比例和高分辨率图像的lmm。arXiv预印本 arXiv:2403.11703。

第 10 页

一个模型架构和计算

模型架构：我们实验中使用的视觉RWKV模型是视觉扩展的记忆加权键值（RWKV）架构，旨在处理视觉和文本数据。我们尝试了以下配置：

• VisualRWKV 1.6B：基于1.6亿参数的基线模型。

• VisualRWKV 1.6B + MLP：通过添加多层感知器（MLP）来增强特征提取。

• 视觉RWKV 1.6B + MLP (HD/UHD): 采用高清（HD）和超高清（UHD）策略进行细粒度特征提取的模型。

计算基础设施：计算基础设施：本研究使用了一系列计算资源。标准训练和基准评估使用了8块NVIDIA A100-80GB GPU。由于内存容量不足，VisualRWKV 7B模型使用6块A100 GPU进行训练。为了进行效率分析，我们使用了NVIDIA RTX 3090 GPU。

计算预算：训练一个epoch的VisualRWKV 1.6B模型，使用8块A100 GPU，需要6.7小时，相当于53.6块GPU小时；训练一个epoch的VisualRWKV 3B模型，使用8块A100 GPU，需要11.3小时，相当于90.4块GPU小时；训练一个epoch的VisualRWKV 7B模型，使用6块A100 GPU，需要26.5小时，相当于159块GPU小时

在所有情况下，RWKV的骨干都经过了视觉任务的适配，通过集成视觉编码器并使用上下文门控。这些模型在各种数据集上进行了视觉问答任务的微调。

## B 数据集

我们在以下数据集上训练和评估了模型：

- mix665k：这是LLaVA用于指令微调的数据集，包含665,000张多样化的图像，旨在增强模型适应各种视觉任务和指令的能力，从而提高其整体性能和可用性。

- HD559k：这是我们自定义的高分辨率数据集，包含559,000张高质量图像。它专注于测试模型在处理高质量视觉内容时的性能，特别是在细节、色彩和清晰度方面，确保模型能够准确捕捉复杂的视觉信息。表8和图3提供了HD559k数据集中数据比例的概览。

• HD667k：作为我们团队的另一个重要贡献，HD667k是一个包含667,000张图像的大规模高分辨率数据集。这个数据集不仅丰富了模型的训练数据，还为其在多样化和复杂的视觉场景中的性能提供了额外的支持，有助于提高模型的泛化能力和鲁棒性。表8和图3提供了HD667k数据集中数据比例的概述。

## C 实验设置

预处理：输入图像被分成四个部分，每个部分由三个视觉编码器（SigLIP、DINOv2、SAM）编码。特征被合并并通过一个包含上下文门控的MLP。

训练：使用AdamW优化器训练模型，学习率为X，使用NVIDIA GPU和混合精度。训练持续100个周期，在10个周期内没有改进时应用早停。

评估：模型在DocVQA、InfographicVQA和ChartQA数据集上进行了评估。这些数据集代表了不同的挑战，从文档理解到信息图和图表分析。

第 11 页

<div style="text-align: center;"><img src="imgs/img_in_chart_box_247_186_2412_1405.jpg" alt="Image" width="87%" /></div>

图3：HD559k数据集的分布，展示了不同数据集及其数量。该综合数据集包含多种来源，总计559,494张图像用于训练和评估。

<div style="text-align: center;">HD667k数据集中的数据比例</div>

<div style="text-align: center;"><img src="imgs/img_in_chart_box_613_1967_2335_3031.jpg" alt="Image" width="69%" /></div>

<div style="text-align: center;">图4：HD667k数据集的分布，展示了其组成和数量。总共有667,000张图像，涵盖了多种视觉任务和来源，旨在提高模型性能的训练和评估。</div>

第 12 页


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Dataset Name</td><td style='text-align: center; word-wrap: break-word;'>Quantity</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>textocr</td><td style='text-align: center; word-wrap: break-word;'>21.9k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DocReason25K</td><td style='text-align: center; word-wrap: break-word;'>25k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>sharegpt4v_instruct_61k</td><td style='text-align: center; word-wrap: break-word;'>61k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>monkey_685k_multi_round</td><td style='text-align: center; word-wrap: break-word;'>294k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>llavar_16k</td><td style='text-align: center; word-wrap: break-word;'>16k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>pdfa-eng-50k</td><td style='text-align: center; word-wrap: break-word;'>50k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>pdfa-eng-9k-multi_sft</td><td style='text-align: center; word-wrap: break-word;'>9k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>idl_train-35k</td><td style='text-align: center; word-wrap: break-word;'>35k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>cord-v2-fix2</td><td style='text-align: center; word-wrap: break-word;'>0.8k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>llava_mix50k</td><td style='text-align: center; word-wrap: break-word;'>50k</td></tr></table>
表8：HD559k数据集概览



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Dataset Name</td><td style='text-align: center; word-wrap: break-word;'>Quantity</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>textocr</td><td style='text-align: center; word-wrap: break-word;'>21.9k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DocReason25K</td><td style='text-align: center; word-wrap: break-word;'>25k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>sharegpt4v_instruct_61k</td><td style='text-align: center; word-wrap: break-word;'>61k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>monkey_685k_multi_round</td><td style='text-align: center; word-wrap: break-word;'>294k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>llavar_16k</td><td style='text-align: center; word-wrap: break-word;'>16k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>pdfa-eng-50k</td><td style='text-align: center; word-wrap: break-word;'>50k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>pdfa-eng-9k-multi_sft</td><td style='text-align: center; word-wrap: break-word;'>9k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>idl_train-35k</td><td style='text-align: center; word-wrap: break-word;'>35k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>cord-v2-fix2</td><td style='text-align: center; word-wrap: break-word;'>0.8k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>llava_mix50k</td><td style='text-align: center; word-wrap: break-word;'>50k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>chart2text</td><td style='text-align: center; word-wrap: break-word;'>26.9k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>rendered_text</td><td style='text-align: center; word-wrap: break-word;'>10k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>iam</td><td style='text-align: center; word-wrap: break-word;'>5.66k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>st_vqa</td><td style='text-align: center; word-wrap: break-word;'>17.2k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>tabmwp</td><td style='text-align: center; word-wrap: break-word;'>22.7k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>vistext</td><td style='text-align: center; word-wrap: break-word;'>9.97k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>visualmrc</td><td style='text-align: center; word-wrap: break-word;'>3k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>websight</td><td style='text-align: center; word-wrap: break-word;'>10k</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>infographic_vqa</td><td style='text-align: center; word-wrap: break-word;'>2.1k</td></tr></table>
表9：HD667k数据集概览

## D 数据和超参数

### • A. 训练数据

我们在VisualRWKV的训练过程中采用了两阶段训练方法。在特征对齐阶段，使用了558K来自LAION-CC-SBU的图像，将冻结的视觉编码器与冻结的LLM连接起来。这一阶段为图像-文本对齐奠定了基础。在视觉指令微调阶段，使用了扩展的150K多模态示例，这些示例由GPT生成，以及515K VQA数据集。这些数据集用于增强模型处理多模态任务的能力。本文中使用的所有数据均符合其预期用途。

在数据准备过程中，严格遵循了伦理指南，重点是通过自动化工具和人工审查识别和处理个人身份信息（PII）和敏感内容。采用了匿名化技术，如数据掩码，以确保数据的完整性和隐私。

### • B. 评估基准

我们使用了各种基准来评估模型。VQA-v2和GQA指标基于

第 13 页

测试-开发划分，而TextVQA是在其验证集上评估的。ScienceQA和POPE的指标来自其测试集。MMBench指标基于开发集，而MME在特定测试集上进行评估。

### • C. 数据语言

我们的训练数据覆盖了多个数据集，其中大多数视觉问答（VQA）数据集都是英文的。ShareGPT数据是多语言的，涵盖了多个用户贡献的语言。在评估基准中，MMBench-cn是中文的，其余均为英文。

### • D. 超参数

模型使用1.6B参数进行实验。详细的视觉语言对齐预训练和视觉指令微调阶段的超参数列于表10中。这些包括针对不同数据集上多样化任务的设置，确保模型具有良好的性能。


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Hyperparameter</td><td style='text-align: center; word-wrap: break-word;'>1.6B-Pretrain</td><td style='text-align: center; word-wrap: break-word;'>1.6B-Finetune</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>batch size</td><td style='text-align: center; word-wrap: break-word;'>256</td><td style='text-align: center; word-wrap: break-word;'>128</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>lr init</td><td style='text-align: center; word-wrap: break-word;'>1e-3</td><td style='text-align: center; word-wrap: break-word;'>6e-5</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>lr end</td><td style='text-align: center; word-wrap: break-word;'>1e-5</td><td style='text-align: center; word-wrap: break-word;'>1.5e-5</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>lr schedule</td><td style='text-align: center; word-wrap: break-word;'>cosine decay</td><td style='text-align: center; word-wrap: break-word;'>cosine decay</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>lr warmup ratio</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>weight decay</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>epoch</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>optimizer</td><td style='text-align: center; word-wrap: break-word;'>AdamW</td><td style='text-align: center; word-wrap: break-word;'>AdamW</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DeepSpeed stage</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>
<div style="text-align: center;">表10：1.6B模型预训练和微调的超参数。</div>

## E 限制和未来工作

尽管UHD策略显著提高了模型性能，尤其是在ChartQA上，但文档理解任务仍面临挑战。未来的工作将探索更好的特征提取方法，并进一步优化模型以适应多模态任务。

## F 使用AI助手

在这项研究中，仅使用人工智能写作助手进行重述、拼写检查和增强作者原始内容，并不引入任何新内容。