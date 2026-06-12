// frontend/src/ArchitectureGraph.jsx
import React from 'react';

export default function ArchitectureGraph() {
  const cssStyles = `
    .arch-wrapper {
      --font-sans: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --color-background-primary: #ffffff;
      --color-text-primary: #111827;
      --color-text-secondary: #4b5563;
      --color-text-tertiary: #9ca3af;
      --color-border-tertiary: #e5e7eb;
      
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      box-shadow: 0 10px 30px -5px rgba(0,0,0,0.05);
      padding: 32px 24px;
      font-family: var(--font-sans);
      width: 100%;
      max-width: 900px;
      margin: 40px auto;
    }

    .arch-wrapper * { box-sizing: border-box; margin: 0; padding: 0; }

    /* Cards */
    .arch-card {
      border: 1px solid var(--color-border-tertiary);
      border-radius: 10px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      background: var(--color-background-primary);
      transition: transform 0.2s, box-shadow 0.2s;
      position: relative;
    }
    .arch-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    .arch-card-title { font-size: 13px; font-weight: 700; color: var(--color-text-primary); line-height: 1.3; }
    .arch-card-sub { font-size: 11px; color: var(--color-text-secondary); line-height: 1.4; }
    .arch-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: auto; padding-top: 6px;}
    .arch-tag { font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; line-height: 1.4; }

    /* Color ramps */
    .c-gray-card { background: #F8F9FA; border-color: #DEE2E6; }
    .c-gray-card .arch-card-title { color: #212529; }
    .c-gray-card .arch-card-sub { color: #495057; }
    
    .c-purple-card { background: #F3F0FF; border-color: #D0BFFF; }
    .c-purple-card .arch-card-title { color: #5F3DC4; }
    .c-purple-card .arch-card-sub { color: #7950F2; }
    .c-purple-tag { background: #E5DBFF; color: #5F3DC4; }

    .c-teal-card { background: #E6FCF5; border-color: #63E6BE; }
    .c-teal-card .arch-card-title { color: #087F5B; }
    .c-teal-card .arch-card-sub { color: #0CA678; }
    .c-teal-tag { background: #C3FAE8; color: #087F5B; }

    .c-coral-card { background: #FFF0F6; border-color: #FCC2D7; }
    .c-coral-card .arch-card-title { color: #A61E4D; }
    .c-coral-card .arch-card-sub { color: #D6336C; }
    .c-coral-tag { background: #FFDEEB; color: #A61E4D; }

    .c-blue-card { background: #E7F5FF; border-color: #74C0FC; }
    .c-blue-card .arch-card-title { color: #1864AB; }
    .c-blue-card .arch-card-sub { color: #1C7ED6; }
    .c-blue-tag { background: #D0EBFF; color: #1864AB; }

    /* Layout & Lines */
    .arch-grid { display: flex; flex-direction: column; gap: 8px; }
    .arch-row { display: flex; align-items: stretch; gap: 12px; }
    .arch-row-label { width: 96px; flex-shrink: 0; display: flex; flex-direction: column; justify-content: center; gap: 2px; }
    .arch-row-label .rl-num { font-size: 11px; font-weight: 800; color: var(--color-text-tertiary); letter-spacing: .05em; font-family: monospace;}
    .arch-row-label .rl-name { font-size: 12px; font-weight: 700; color: var(--color-text-secondary); line-height: 1.3; }
    .arch-row-body { flex: 1; display: flex; gap: 8px; align-items: stretch; }

    /* Agent Loop Container (The core control loop) */
    .loop-box { 
      border: 2px dashed #AFA9EC; border-radius: 12px; padding: 16px 12px; 
      display: flex; flex-direction: column; gap: 12px; position: relative; flex: 1; 
      background: linear-gradient(to bottom, #faf5ff 0%, #f0fdf4 100%);
    }
    .loop-label { 
      position: absolute; top: -11px; left: 16px; background: #faf5ff; padding: 0 8px; 
      font-size: 12px; font-weight: 700; color: #534AB7; display: flex; align-items: center; gap: 6px; 
    }
    
    /* Internal Calls */
    .internal-call-line {
      display: flex; align-items: center; justify-content: center; gap: 8px;
      font-size: 11px; font-weight: 700; color: #8b5cf6; padding: 2px 0;
    }

    /* Connectors */
    .connector-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; }
    .conn-line { flex: 1; height: 1.5px; background: var(--color-border-tertiary); position: relative; }
    .conn-line::after { content: '▾'; position: absolute; bottom: -10.5px; left: 50%; transform: translateX(-50%); font-size: 14px; color: var(--color-text-tertiary); }
    .conn-label { font-size: 11px; font-weight: 700; color: var(--color-text-tertiary); text-align: center; margin-bottom: 2px; }
  `;

  return (
    <div className="arch-wrapper">
      <style dangerouslySetInnerHTML={{ __html: cssStyles }} />
      
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginBottom: '6px' }}>RWKV-ECRA 智能体控制架构图</h2>
        <p style={{ fontSize: '13px', color: '#64748b' }}>展示 Agent 中枢如何路由、包裹并调度底层工具与工作流</p>
      </div>

      <div className="arch-grid">

        {/* 01: Frontend */}
        <div className="arch-row">
          <div className="arch-row-label">
            <div className="rl-num">01</div>
            <div className="rl-name">前端交互层</div>
          </div>
          <div className="arch-row-body">
            <div className="arch-card c-gray-card" style={{ flex: 1 }}>
              <div className="arch-card-title">用户交互界面 (UI)</div>
              <div className="arch-card-sub">文件上传与删除 / 发送指令</div>
            </div>
            <div className="arch-card c-gray-card" style={{ flex: 1.4 }}>
              <div className="arch-card-title">前端服务代理</div>
              <div className="arch-card-sub">HTTP 转发至后端 API 网关</div>
            </div>
          </div>
        </div>

        <div className="connector-row" style={{ paddingLeft: '108px' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1px' }}>
            <div className="conn-label">任务初始化与文件环境就绪</div>
            <div className="conn-line"></div>
          </div>
        </div>

        {/* 02: Agent Control Loop (The big wrapper) */}
        <div className="arch-row">
          <div className="arch-row-label" style={{ justifyContent: 'flex-start', paddingTop: '12px' }}>
            <div className="rl-num">02 & 03</div>
            <div className="rl-name">智能体中枢<br/><br/>与<br/><br/>工具集</div>
          </div>
          
          <div className="arch-row-body">
            <div className="loop-box">
              <div className="loop-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{marginRight: '2px'}}>
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21v-5h5"/>
                </svg>
                Agent 核心控制闭环 (Control Loop)
              </div>
              
              {/* Top half: Brain (LLM Reasoning) */}
              <div style={{ display: 'flex', gap: '8px', alignItems: 'stretch' }}>
                <div className="arch-card c-purple-card" style={{ flex: 1.2 }}>
                  <div className="arch-card-title">1. Orchestrator (调度器)</div>
                  <div className="arch-card-sub">接收用户指令，更新/挂载全局工作状态与反馈。</div>
                  <div className="arch-card-tags"><span className="arch-tag c-purple-tag">记忆与上下文</span></div>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', color: '#a78bfa', fontWeight: 'bold' }}>→</div>
                
                <div className="arch-card c-purple-card" style={{ flex: 1 }}>
                  <div className="arch-card-title">2. Analyzer (分析器)</div>
                  <div className="arch-card-sub">辨别深研/泛读模式，找出信息缺口。</div>
                  <div className="arch-card-tags"><span className="arch-tag c-purple-tag">内嵌清洗和审计</span></div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', color: '#a78bfa', fontWeight: 'bold' }}>→</div>
                
                <div className="arch-card c-purple-card" style={{ flex: 1 }}>
                  <div className="arch-card-title">3. Planner (规划器)</div>
                  <div className="arch-card-sub">决定下一步动作，生成工具 JSON。</div>
                  <div className="arch-card-tags"><span className="arch-tag c-purple-tag">工具参数生成</span></div>
                </div>
              </div>

              {/* Internal Call Signal */}
              <div className="internal-call-line">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>
                基于当前状态路由，调度目标工具执行 (Tool.execute)
              </div>

              {/* Bottom half: Actuators (Tools/Workflows) */}
              <div style={{ display: 'flex', gap: '8px', padding: '8px', background: 'rgba(255,255,255,0.6)', borderRadius: '10px', border: '1px solid #d1fae5' }}>
                <div className="arch-card c-teal-card" style={{ flex: 1, padding: '10px' }}>
                  <div className="arch-card-title">长文本 MapReduce</div>
                  <div className="arch-card-tags"><span className="arch-tag c-teal-tag">压缩提炼</span></div>
                </div>
                <div className="arch-card c-teal-card" style={{ flex: 1, padding: '10px' }}>
                  <div className="arch-card-title">原生/Tavily 检索</div>
                  <div className="arch-card-tags"><span className="arch-tag c-teal-tag">网络信息获取</span></div>
                </div>
                <div className="arch-card c-teal-card" style={{ flex: 1, padding: '10px' }}>
                  <div className="arch-card-title">局部精准捞针</div>
                  <div className="arch-card-tags"><span className="arch-tag c-teal-tag">细节回溯</span></div>
                </div>
                <div className="arch-card c-teal-card" style={{ flex: 1, padding: '10px' }}>
                  <div className="arch-card-title">研报生成 (结束)</div>
                  <div className="arch-card-tags"><span className="arch-tag c-teal-tag">精细排版和排除幻觉</span></div>
                </div>
              </div>

              {/* Loop Return Signal */}
              <div className="internal-call-line" style={{ color: '#059669', paddingTop: '4px' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                工具执行结果反馈至 Orchestrator 工作记忆中，驱动下一轮循环
              </div>
            </div>
          </div>
        </div>

        <div className="connector-row" style={{ paddingLeft: '108px' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1px' }}>
            <div className="conn-label">工作流与工具底层依赖的基座 API</div>
            <div className="conn-line"></div>
          </div>
        </div>

        {/* 04: Infrastructure (Models & Storage) */}
        <div className="arch-row">
          <div className="arch-row-label">
            <div className="rl-num">04</div>
            <div className="rl-name">外部基建与<br/>存储隔离</div>
          </div>
          <div className="arch-row-body" style={{ alignItems: 'stretch' }}>
            {/* Models */}
            <div style={{ flex: 1.5, display: 'flex', gap: '8px', flexDirection: 'column' }}>
              <div className="arch-card c-blue-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div className="arch-card-title">外部大模型 (LLM API)</div>
                    <div className="arch-card-sub" style={{marginTop:'2px'}}>支撑智能体逻辑推理、骨架生成与结构化排版</div>
                  </div>
                  <span className="arch-tag c-blue-tag">规划</span>
                </div>
              </div>
              <div className="arch-card c-blue-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div className="arch-card-title">专用小模型 (RWKV)</div>
                    <div className="arch-card-sub" style={{marginTop:'2px'}}>支撑长文本的并发降维、阅读和智能检索</div>
                  </div>
                  <span className="arch-tag c-blue-tag">高并发执行</span>
                </div>
              </div>
            </div>
            
            <div style={{ width: '8px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-tertiary)', fontSize: '12px' }}>|</div>
            
            {/* Storage */}
            <div style={{ flex: 2, display: 'flex', gap: '8px' }}>
              <div className="arch-card c-coral-card" style={{ flex: 1, justifyContent: 'center' }}>
                <div className="arch-card-title" style={{textAlign: 'center'}}>Local Workspace</div>
                <div className="arch-card-sub" style={{textAlign: 'center'}}>本地参考文件存放区</div>
              </div>
              <div className="arch-card c-coral-card" style={{ flex: 1, justifyContent: 'center' }}>
                <div className="arch-card-title" style={{textAlign: 'center'}}>Checkpoints</div>
                <div className="arch-card-sub" style={{textAlign: 'center'}}>断点缓存区</div>
              </div>
              <div className="arch-card c-coral-card" style={{ flex: 1, justifyContent: 'center' }}>
                <div className="arch-card-title" style={{textAlign: 'center'}}>Final Outputs</div>
                <div className="arch-card-sub" style={{textAlign: 'center'}}>引用文件溯源</div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Legend / Key */}
      <div style={{ display: 'flex', gap: '20px', marginTop: '28px', paddingTop: '16px', borderTop: '1px solid var(--color-border-tertiary)', flexWrap: 'wrap', justifyContent: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: '#F8F9FA', border: '1px solid #DEE2E6' }}></div>
          <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 600 }}>前端代理</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: '#F3F0FF', border: '1px solid #D0BFFF' }}></div>
          <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 600 }}>智能体中枢</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: '#E6FCF5', border: '1px solid #63E6BE' }}></div>
          <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 600 }}>执行工具组</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: '#E7F5FF', border: '1px solid #74C0FC' }}></div>
          <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 600 }}>外部 API</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: '#FFF0F6', border: '1px solid #FCC2D7' }}></div>
          <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 600 }}>持久化</span>
        </div>
      </div>
    </div>
  );
}